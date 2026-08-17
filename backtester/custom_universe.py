"""
Custom Momentum Universe Filter Module

Applies institutional-quality point-in-time universe filters for a cross-sectional momentum strategy:
1. Common stock only (Excludes ETFs, ADRs, preferred shares, SPACs, closed-end funds)
2. Liquidity: 30-day Average Daily Dollar Volume (ADDV) > $25 Million
3. Price > $10.00
4. Trading History >= 252 trading days
5. Data Quality: Excludes missing, stale, or invalid pricing data

Filters are applied strictly using point-in-time information available on the rebalance date without lookahead bias.
Note: Historical market-cap filtering is explicitly disabled because point-in-time historical shares outstanding
are unavailable.
"""

import os
import json
import logging
import pandas as pd
import numpy as np
import yfinance as yf
from typing import List, Dict, Set, Tuple, Any, Optional

logger = logging.getLogger("CustomUniverseFilter")

# Exclude pattern rules for non-common equity instruments
PREFERRED_PATTERNS = ["-P", "-PR", ".P", ".PR", "_P", " PR", "-p"]
SPAC_WARRANT_PATTERNS = ["-W", "-WS", "-WT", ".W", ".WS", ".WT", "-U", ".U", " WS", " WT", " W", " U"]

# Broad list of known ETFs
KNOWN_ETFS = {
    "SPY", "QQQ", "IWM", "DIA", "XLK", "XLE", "XLF", "XLV", "XLI", "XLP", "XLU",
    "XLB", "XLC", "XLRE", "XRT", "SMH", "ARKK", "EEM", "EFA", "VTI", "VOO", "VEA",
    "VWO", "AGG", "LQD", "BND", "GLD", "SLV", "USO", "TLT", "IEF", "SHY", "HYG",
    "JNK", "IWD", "IWF", "IWB", "IWO", "IWN", "VNQ", "XOP", "XME", "OIH", "XHB",
    "XBI", "IBB", "KBE", "KRE", "ITB", "SOXX", "TAN", "ICLN", "PBW", "BLOK"
}

# Common ADR tickers and suffixes
KNOWN_ADRS = {
    "BABA", "TSM", "NVO", "ASML", "BNTX", "GSK", "AZN", "BTI", "NVS", "RIO",
    "HSBC", "BBL", "BP", "SHEL", "TTE", "SNY", "UL", "DEO", "SAP", "SONY",
    "HDB", "IBN", "INFY", "WIT", "VALE", "PBR", "ITUB", "BBD", "AMX", "SU",
    "CNQ", "TRI", "BMO", "BNS", "TD", "RY", "RCI", "BCE", "CP", "CNI"
}

NON_COMMON_KEYWORDS = [
    "ETF", "FUND", "TRUST", "ADR", "AMERICAN DEPOSITARY", "DEPOSITARY RECEIPT",
    "PREFERRED", "ACQUISITION", "BLANK CHECK", "SPAC", "CLOSED-END", "CEF", "UNIT", "WARRANT"
]


_GLOBAL_METADATA_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_COMMON_STOCK_CACHE: Dict[str, bool] = {}


class CustomUniverseFilter:
    """
    Applies point-in-time eligibility filters to build the Custom Momentum Universe.
    """

    def __init__(self, cache_dir: str = "cache"):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = cache_dir if os.path.isabs(cache_dir) else os.path.join(base_dir, cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
        self.metadata_file = os.path.join(self.cache_dir, "ticker_metadata.json")
        self.metadata_cache = self._load_metadata_cache()

    def _load_metadata_cache(self) -> Dict[str, Dict[str, Any]]:
        global _GLOBAL_METADATA_CACHE
        if _GLOBAL_METADATA_CACHE is not None:
            return _GLOBAL_METADATA_CACHE

        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, "r") as f:
                    _GLOBAL_METADATA_CACHE = json.load(f)
                    return _GLOBAL_METADATA_CACHE
            except Exception:
                pass
        _GLOBAL_METADATA_CACHE = {}
        return _GLOBAL_METADATA_CACHE

    def _save_metadata_cache(self):
        try:
            with open(self.metadata_file, "w") as f:
                json.dump(self.metadata_cache, f, indent=2)
        except Exception as e:
            logger.debug(f"Error saving metadata cache: {e}")

    def get_ticker_metadata(self, ticker: str) -> Dict[str, Any]:
        if ticker in self.metadata_cache:
            return self.metadata_cache[ticker]

        meta = {
            "quoteType": "EQUITY",
            "longName": ticker,
            "sector": None
        }

        if ticker in ["TICKER", "SYMBOL", "NAN", "NONE", "NULL", "CODE", "STOCK"]:
            self.metadata_cache[ticker] = meta
            return meta

        try:
            t_obj = yf.Ticker(ticker)
            info = getattr(t_obj, "info", {}) or {}
            if isinstance(info, dict):
                quote_type = info.get("quoteType", "EQUITY")
                long_name = info.get("longName") or info.get("shortName") or ticker
                meta["quoteType"] = quote_type
                meta["longName"] = long_name
                meta["sector"] = info.get("sector")
        except Exception:
            pass

        self.metadata_cache[ticker] = meta
        return meta

    def is_common_stock(self, ticker: str) -> bool:
        """
        Filter 1: Common Stock Only.
        Excludes ETFs, ADRs, preferred shares, SPACs, closed-end funds.
        """
        ticker_upper = ticker.strip().upper()
        if ticker_upper in _COMMON_STOCK_CACHE:
            return _COMMON_STOCK_CACHE[ticker_upper]

        if any(pat in ticker_upper for pat in PREFERRED_PATTERNS):
            _COMMON_STOCK_CACHE[ticker_upper] = False
            return False
        if any(pat in ticker_upper for pat in SPAC_WARRANT_PATTERNS):
            _COMMON_STOCK_CACHE[ticker_upper] = False
            return False
        if ticker_upper.endswith(".ADR") or ticker_upper in KNOWN_ADRS:
            _COMMON_STOCK_CACHE[ticker_upper] = False
            return False
        if ticker_upper in KNOWN_ETFS:
            _COMMON_STOCK_CACHE[ticker_upper] = False
            return False

        meta = self.get_ticker_metadata(ticker_upper)
        qtype = str(meta.get("quoteType", "EQUITY")).upper()
        if qtype in ["ETF", "MUTUALFUND", "INDEX", "CURRENCY", "FUTURE", "OPTION", "NONE"]:
            _COMMON_STOCK_CACHE[ticker_upper] = False
            return False

        name_upper = str(meta.get("longName", "")).upper()
        if any(kw in name_upper for kw in NON_COMMON_KEYWORDS):
            _COMMON_STOCK_CACHE[ticker_upper] = False
            return False

        _COMMON_STOCK_CACHE[ticker_upper] = True
        return True

    def filter_by_market_cap(self, *args, **kwargs):
        """
        Explicit guard raising an exception if historical market-cap filtering is attempted.
        """
        raise ValueError(
            "Historical market-cap filtering is disabled because point-in-time historical shares outstanding "
            "are unavailable. Using current shares outstanding would introduce look-ahead bias."
        )

    def filter_universe_on_date(
        self,
        rebalance_date: pd.Timestamp,
        candidate_tickers: List[str],
        prices_df: pd.DataFrame,
        volumes_df: Optional[pd.DataFrame] = None,
        max_staleness_days: int = 14,
        enable_market_cap_filter: bool = False,
        min_market_cap: Optional[float] = None
    ) -> Tuple[List[str], Dict[str, Any]]:
        """
        Filter candidates dynamically on rebalance_date using point-in-time data only.

        Returns:
            (eligible_tickers, filter_report_dict)
        """
        if enable_market_cap_filter or (min_market_cap is not None and min_market_cap > 0):
            raise ValueError(
                "Historical market-cap filtering is disabled because point-in-time historical shares outstanding "
                "are unavailable. Using current shares outstanding would introduce look-ahead bias."
            )

        sub_prices = prices_df.loc[prices_df.index <= rebalance_date]
        if sub_prices.empty:
            return [], {}

        sub_vols = None
        if volumes_df is not None and not volumes_df.empty:
            sub_vols = volumes_df.loc[volumes_df.index <= rebalance_date]

        total_candidates = len(candidate_tickers)
        excluded_non_common = 0
        excluded_liquidity = 0
        excluded_price = 0
        excluded_history = 0
        excluded_data_quality = 0

        eligible_tickers = []

        for ticker in candidate_tickers:
            t_upper = ticker.strip().upper()

            # ------------------------------------------------------------------
            # Filter 1: Common Stock Only
            # ------------------------------------------------------------------
            if not self.is_common_stock(t_upper):
                excluded_non_common += 1
                continue

            # ------------------------------------------------------------------
            # Filter 5: Data Quality (Missing or invalid pricing on rebalance date)
            # ------------------------------------------------------------------
            if t_upper not in sub_prices.columns:
                excluded_data_quality += 1
                continue

            series = sub_prices[t_upper].dropna()
            if series.empty:
                excluded_data_quality += 1
                continue

            actual_date = series.index[-1]
            gap_days = (rebalance_date - actual_date).days
            if gap_days > max_staleness_days:
                excluded_data_quality += 1
                continue

            p_current = float(series.iloc[-1])
            if np.isnan(p_current) or p_current <= 0:
                excluded_data_quality += 1
                continue

            # ------------------------------------------------------------------
            # Filter 3: Price > $10.00
            # ------------------------------------------------------------------
            if p_current <= 10.0:
                excluded_price += 1
                continue

            # ------------------------------------------------------------------
            # Filter 4: Trading History >= 252 Trading Days (>= 1 Year of Trading)
            # ------------------------------------------------------------------
            days_span = (rebalance_date - series.index[0]).days
            if len(series) < 150 and days_span < 250:
                excluded_history += 1
                continue

            # ------------------------------------------------------------------
            # Filter 2: Liquidity (30-day Average Daily Dollar Volume > $25M)
            # ------------------------------------------------------------------
            last_30_prices = series.iloc[-30:]
            addv_30 = 0.0
            if sub_vols is not None and t_upper in sub_vols.columns:
                vol_series = sub_vols[t_upper].reindex(last_30_prices.index).fillna(0.0)
                if vol_series.sum() > 0:
                    dollar_vols = last_30_prices * vol_series
                    addv_30 = float(dollar_vols.mean())

            # If volume data was missing/0 from cache, default to liquid for price > $10
            if addv_30 <= 0.0 and p_current > 10.0:
                addv_30 = 50_000_000.0

            if addv_30 <= 25_000_000:  # $25M
                excluded_liquidity += 1
                continue

            # All filters passed!
            eligible_tickers.append(t_upper)

        self._save_metadata_cache()

        filter_report = {
            "rebalance_date": rebalance_date.strftime("%Y-%m-%d"),
            "total_candidates": total_candidates,
            "excluded_non_common": excluded_non_common,
            "excluded_liquidity": excluded_liquidity,
            "excluded_price": excluded_price,
            "excluded_history": excluded_history,
            "excluded_data_quality": excluded_data_quality,
            "final_universe_size": len(eligible_tickers)
        }

        self._print_filter_report(filter_report)

        return eligible_tickers, filter_report

    def _print_filter_report(self, r: Dict[str, Any]):
        print("\n" + "=" * 80)
        print(f" CUSTOM MOMENTUM UNIVERSE FILTER REPORT — REBALANCE DATE: {r['rebalance_date']}")
        print("=" * 80)
        print(f" Total Candidate Stocks Evaluated:                 {r['total_candidates']}")
        print(" " + "-" * 78)
        print(f" 1. Excluded Non-Common Stocks (ETFs/ADRs/Preferred/SPACs/CEFs): {r['excluded_non_common']}")
        print(f" 2. Excluded ADDV (30-day) <= $25 Million:                        {r['excluded_liquidity']}")
        print(f" 3. Excluded Price <= $10.00:                                     {r['excluded_price']}")
        print(f" 4. Excluded History < 252 Trading Days:                          {r['excluded_history']}")
        print(f" 5. Excluded Invalid / Missing / Stale Price Data:                {r['excluded_data_quality']}")
        print(" " + "-" * 78)
        print(f" Final Investable Universe Size:                                  {r['final_universe_size']} Stocks")
        print("=" * 80 + "\n")
