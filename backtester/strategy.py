"""
Strategy module defining trading strategy interfaces and momentum implementation.

Designed for modularity and extensibility: any new strategy class inheriting from BaseStrategy
can be plugged directly into the BacktestEngine without changing engine logic.
"""

from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
import logging
import os
import json
from typing import Dict, List, Optional, Tuple
try:
    from backtester.utils import load_universe
    from backtester.custom_universe import CustomUniverseFilter
except ImportError:
    from utils import load_universe
    from custom_universe import CustomUniverseFilter

logger = logging.getLogger("Strategy")

_PRICE_SERIES_CACHE: Dict[Tuple[int, str], Optional[pd.Series]] = {}
_TICKER_METADATA_CACHE: Optional[Dict[str, dict]] = None

def clear_strategy_cache():
    global _PRICE_SERIES_CACHE
    _PRICE_SERIES_CACHE.clear()


def _get_ticker_metadata() -> Dict[str, dict]:
    global _TICKER_METADATA_CACHE
    if _TICKER_METADATA_CACHE is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        metadata_path = os.path.join(base_dir, "cache", "ticker_metadata.json")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, "r") as f:
                    _TICKER_METADATA_CACHE = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load ticker metadata: {e}")
                _TICKER_METADATA_CACHE = {}
        else:
            _TICKER_METADATA_CACHE = {}
    return _TICKER_METADATA_CACHE


import re

KNOWN_ISSUER_MAP: Dict[str, str] = {
    "GOOG": "Alphabet Inc.",
    "GOOGL": "Alphabet Inc.",
    "BRK-A": "Berkshire Hathaway Inc.",
    "BRK-B": "Berkshire Hathaway Inc.",
    "BRK.A": "Berkshire Hathaway Inc.",
    "BRK.B": "Berkshire Hathaway Inc.",
    "FOX": "Fox Corporation",
    "FOXA": "Fox Corporation",
    "NWS": "News Corporation",
    "NWSA": "News Corporation",
    "BF-A": "Brown-Forman Corporation",
    "BF-B": "Brown-Forman Corporation",
    "LEN": "Lennar Corporation",
    "LEN-B": "Lennar Corporation",
    "UA": "Under Armour, Inc.",
    "UAA": "Under Armour, Inc.",
    "UHAL": "U-Haul Holding Company",
    "UHAL-B": "U-Haul Holding Company",
    "FWONA": "Formula One Group",
    "FWONK": "Formula One Group",
    "LBRDA": "Liberty Broadband Corporation",
    "LBRDK": "Liberty Broadband Corporation",
    "LBTYA": "Liberty Global Ltd.",
    "LBTYK": "Liberty Global Ltd.",
    "LLYVA": "Liberty Live Holdings, Inc.",
    "LLYVK": "Liberty Live Holdings, Inc.",
    "GLIBA": "Liberty Capital Corporation",
    "GLIBK": "Liberty Capital Corporation",
    "HEI": "HEICO Corporation",
    "HEI-A": "HEICO Corporation",
    "CWEN": "Clearway Energy, Inc.",
    "CWEN-A": "Clearway Energy, Inc.",
    "MOG-A": "Moog Inc.",
    "MOG-B": "Moog Inc.",
    "GEF": "Greif, Inc.",
    "GEF-B": "Greif, Inc.",
    "BIO": "Bio-Rad Laboratories, Inc.",
    "BIO-B": "Bio-Rad Laboratories, Inc.",
    "BATRA": "Atlanta Braves Holdings",
    "BATRK": "Atlanta Braves Holdings",
    "LSXMA": "Liberty SiriusXM Group",
    "LSXMK": "Liberty SiriusXM Group",
}


def get_parent_issuer(ticker: str, metadata: Optional[Dict[str, dict]] = None) -> str:
    """
    Identify parent company / issuer for a ticker symbol to enforce one share class per issuer limit.
    Checks explicit mapping table, metadata CIK, metadata longName, or ticker symbol base.
    """
    ticker_upper = ticker.upper()
    if ticker_upper in KNOWN_ISSUER_MAP:
        return KNOWN_ISSUER_MAP[ticker_upper]

    if metadata and ticker in metadata:
        m = metadata[ticker]
        cik = m.get("cik") or m.get("CIK")
        if cik:
            return f"CIK:{cik}"
        long_name = m.get("longName") or m.get("shortName") or m.get("name")
        if long_name:
            cleaned = re.sub(r'(?i)\b(class|series)\s+[a-z0-9]+\b', '', long_name)
            cleaned = re.sub(r'[\s,\.-]+', ' ', cleaned).strip().lower()
            if cleaned:
                return cleaned

    base = re.sub(r'[\.-][A-Z]$', '', ticker_upper)
    return base


def _get_valid_series(prices_df: pd.DataFrame, ticker: str) -> Optional[pd.Series]:
    cache_key = (id(prices_df), ticker)
    if cache_key in _PRICE_SERIES_CACHE:
        return _PRICE_SERIES_CACHE[cache_key]
    if ticker not in prices_df.columns:
        _PRICE_SERIES_CACHE[cache_key] = None
        return None
    s = prices_df[ticker].dropna()
    _PRICE_SERIES_CACHE[cache_key] = s
    return s


def _get_last_price_before(prices_df: pd.DataFrame, ticker: str, target_date: pd.Timestamp) -> Tuple[Optional[pd.Timestamp], Optional[float]]:
    s = _get_valid_series(prices_df, ticker)
    if s is None or s.empty:
        return None, None
    idx = s.index.searchsorted(target_date, side='right') - 1
    if idx < 0:
        return None, None
    return s.index[idx], float(s.iloc[idx])


class BaseStrategy(ABC):
    """
    Abstract Base Class for all trading strategies.
    """

    @abstractmethod
    def generate_target_weights(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame,
        raw_prices_df: Optional[pd.DataFrame] = None
    ) -> Dict[str, float]:
        """
        Calculate target portfolio weights for tickers on a given rebalance date.

        Args:
            current_date: The timestamp of the current rebalance date.
            prices_df: DataFrame containing all historical price data up to current_date.
            raw_prices_df: Optional DataFrame with unadjusted/raw price history for delisting checks.

        Returns:
            Dictionary mapping ticker symbol to target weight (e.g., {'AAPL': 0.05, 'MSFT': -0.05}).
            Positive weights represent long positions, negative weights represent short positions.
            Unallocated weight remains in cash.
        """
        pass


class CrossSectionalMomentumStrategy(BaseStrategy):
    """
    Academic Cross-Sectional Momentum Strategy.

    Ranks stocks based on total return over a lookback window (e.g., 12 months).
    Optionally skips the most recent month (SKIP_LAST_MONTH=True) to avoid 1-month
    short-term reversal effects (Jegadeesh & Titman, 1993).

    NOTE: By default, this implementation operates in a Long-Only mode (holding the top N stocks).
    The original Jegadeesh & Titman (1993) paper implements a long-short (dollar-neutral) strategy,
    buying the top momentum decile/quantile (+1/N) and shorting the bottom momentum decile/quantile (-1/N).
    Set `include_shorts=True` to enable the long-short dollar-neutral momentum mode.
    """

    def __init__(
        self,
        positions: int = 20,
        lookback_months: int = 12,
        skip_last_month: bool = True,
        include_shorts: bool = False,
        max_staleness_days: int = 14,
        universe_file: Optional[str] = None,
        max_positions_per_sector: int = 0,
        min_avg_dollar_volume: float = 0.0,
        min_market_cap: float = 0.0,
        ranking_method: str = "raw_return",
        regime_filter: bool = False,
        regime_reduced_exposure_pct: float = 0.5,
        earnings_blackout_days: int = 0,
        earnings_calendar: Optional[Dict[str, List[str]]] = None,
        momentum_regime_filter: bool = False,
        momentum_regime_lookback_days: int = 20,
        momentum_regime_threshold: float = 0.0,
        vol_scaling: bool = False,
        vol_scaling_lookback_days: int = 20,
        target_volatility: float = 0.25
    ):
        """
        Initialize Momentum Strategy with optional risk-management filters.

        Args:
            positions: Number of top/bottom stocks to hold in each leg (N).
            lookback_months: Total lookback period in months (e.g., 12).
            skip_last_month: Whether to exclude the most recent month from calculation (12-1 momentum).
            include_shorts: Whether to include a short leg (bottom N stocks with -1/N weights).
            max_staleness_days: Maximum allowed days between target lookback date and actual price date.
            universe_file: Optional path to universe CSV file (supports point-in-time constituent filtering).
            max_positions_per_sector: Sector concentration cap (default: 0 = disabled, e.g. 3).
            min_avg_dollar_volume: Liquidity floor trailing 20d avg dollar volume (e.g. $30M/day).
            min_market_cap: Liquidity floor minimum market cap (e.g. $2B).
            ranking_method: 'raw_return' or 'risk_adjusted' (return / trailing volatility).
            regime_filter: Whether to apply SPY 200d SMA regime filter.
            regime_reduced_exposure_pct: Exposure percentage when in bearish market regime (default: 0.5).
            earnings_blackout_days: Earnings blackout window in trading days (default: 0 = disabled).
            earnings_calendar: Optional dictionary mapping ticker to list of earnings announcement date strings.
            momentum_regime_filter: Separate momentum factor crash filter based on sleeve trailing returns.
            momentum_regime_lookback_days: Lookback in trading days for momentum sleeve return (default: 20).
            momentum_regime_threshold: Return threshold below which momentum regime filter fires (default: 0.0).
            vol_scaling: Whether to enable volatility-scaled position sizing.
            vol_scaling_lookback_days: Lookback in trading days for trailing realized volatility (default: 20).
            target_volatility: Annualized target volatility for continuous position scaling (default: 0.25).
        """
        self.positions: int = positions
        self.lookback_months: int = lookback_months
        self.skip_last_month: bool = skip_last_month
        self.include_shorts: bool = include_shorts
        self.max_staleness_days: int = max_staleness_days
        self.universe_file: Optional[str] = universe_file
        self.max_positions_per_sector: int = max_positions_per_sector
        self.min_avg_dollar_volume: float = min_avg_dollar_volume
        self.min_market_cap: float = min_market_cap
        self.ranking_method: str = ranking_method
        self.regime_filter: bool = regime_filter
        self.regime_reduced_exposure_pct: float = regime_reduced_exposure_pct
        self.earnings_blackout_days: int = earnings_blackout_days
        self.earnings_calendar: Optional[Dict[str, List[str]]] = earnings_calendar
        self.momentum_regime_filter: bool = momentum_regime_filter
        self.momentum_regime_lookback_days: int = momentum_regime_lookback_days
        self.momentum_regime_threshold: float = momentum_regime_threshold
        self.vol_scaling: bool = vol_scaling
        self.vol_scaling_lookback_days: int = vol_scaling_lookback_days
        self.target_volatility: float = target_volatility
        self._warned_no_earnings: bool = False

    def calculate_momentum_sleeve_trailing_return(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame,
        volumes_df: Optional[pd.DataFrame] = None,
        lookback_days: int = 20
    ) -> Optional[float]:
        """
        Computes trailing equal-weighted return of the top-N momentum sleeve over lookback_days trading days up to current_date.
        """
        available_dates = prices_df.index[prices_df.index <= current_date]
        if len(available_dates) <= lookback_days:
            return None

        lookback_date = available_dates[-lookback_days - 1]

        mom_series = self.calculate_momentum_returns(lookback_date, prices_df, volumes_df=volumes_df)
        if mom_series.empty:
            return None

        df_mom = pd.DataFrame({'Momentum': mom_series}).dropna()
        df_mom['Ticker'] = df_mom.index
        df_sorted = df_mom.sort_values(by=['Momentum', 'Ticker'], ascending=[False, True])

        sleeve_returns = []
        for ticker in df_sorted['Ticker']:
            if ticker == "SPY":
                continue
            p_lookback_date, p_lookback = _get_last_price_before(prices_df, ticker, lookback_date)
            p_curr_date, p_curr = _get_last_price_before(prices_df, ticker, current_date)
            if p_lookback is not None and p_curr is not None and p_lookback > 0 and p_curr > 0:
                sleeve_returns.append((p_curr / p_lookback) - 1.0)
                if len(sleeve_returns) == self.positions:
                    break

        if not sleeve_returns:
            return None

        return float(np.mean(sleeve_returns))

    def calculate_realized_volatility(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame,
        lookback_days: int = 20,
        selected_tickers: Optional[List[str]] = None
    ) -> float:
        """
        Computes trailing realized annualized volatility over lookback_days trading days.
        """
        available_dates = prices_df.index[prices_df.index <= current_date]
        if len(available_dates) < lookback_days + 1:
            return 0.0

        sub_dates = available_dates[-(lookback_days + 1):]
        sub_prices = prices_df.loc[sub_dates]

        if selected_tickers:
            valid_cols = [t for t in selected_tickers if t in sub_prices.columns]
        else:
            valid_cols = [c for c in sub_prices.columns if c != "SPY"]

        if not valid_cols:
            return 0.0

        pct_changes = sub_prices[valid_cols].pct_change().dropna(how="all")
        daily_returns = pct_changes.mean(axis=1).dropna()

        if len(daily_returns) < 2:
            return 0.0

        return float(daily_returns.std(ddof=1) * np.sqrt(252))

    def calculate_momentum_returns(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame,
        volumes_df: Optional[pd.DataFrame] = None
    ) -> pd.Series:
        """
        Calculate cumulative return over lookback window for each stock using standard 12-1 academic math,
        applying pre-ranking liquidity floor filters and risk-adjusted volatility weighting if configured.

        Returns:
            Series indexed by Ticker with calculated momentum returns.
        """
        # Determine target lookback dates (Standard 12-1 academic convention: t-12 to t-1 when skip_last_month=True)
        if self.skip_last_month:
            # Lookback start: t-12 (current_date - lookback_months)
            # Lookback end: t-1 (current_date - 1 month, removing t-1 skip month)
            start_lookback = current_date - pd.DateOffset(months=self.lookback_months)
            end_lookback = current_date - pd.DateOffset(months=1)
        else:
            # Lookback start: current_date - lookback_months
            # Lookback end: current_date
            start_lookback = current_date - pd.DateOffset(months=self.lookback_months)
            end_lookback = current_date

        # Filter price history up to current_date
        sub_df = prices_df.loc[prices_df.index <= current_date]
        if sub_df.empty:
            return pd.Series(dtype=float)

        # Point-in-time constituent filtering (prevents survivorship bias)
        if self.universe_file and "custom_momentum" in str(self.universe_file).lower():
            candidate_list = load_universe(self.universe_file, date=current_date)
            if not hasattr(self, "_filter_engine"):
                self._filter_engine = CustomUniverseFilter()
            active_list, _ = self._filter_engine.filter_universe_on_date(
                rebalance_date=current_date,
                candidate_tickers=candidate_list,
                prices_df=prices_df,
                volumes_df=volumes_df,
                max_staleness_days=self.max_staleness_days
            )
            active_tickers = set(active_list)
            eligible_columns = [t for t in sub_df.columns if t in active_tickers]
        elif self.universe_file:
            active_tickers = set(load_universe(self.universe_file, date=current_date))
            eligible_columns = [t for t in sub_df.columns if t in active_tickers]
        else:
            eligible_columns = list(sub_df.columns)

        momentum_scores = {}
        metadata = _get_ticker_metadata()

        for ticker in eligible_columns:
            actual_curr_date, p_curr = _get_last_price_before(prices_df, ticker, current_date)
            if actual_curr_date is None:
                continue

            # --- FILTER 2: Liquidity Floor (Pre-Ranking Filter) ---
            if self.min_avg_dollar_volume > 0 and volumes_df is not None and ticker in volumes_df.columns:
                p_sub = prices_df[ticker].loc[:current_date].dropna().tail(20)
                if not p_sub.empty:
                    v_sub = volumes_df[ticker].reindex(p_sub.index).fillna(0)
                    if v_sub.sum() > 0:
                        avg_dollar_vol = float((p_sub * v_sub).mean())
                        if avg_dollar_vol < self.min_avg_dollar_volume:
                            logger.debug(
                                f"Liquidity Filter: Skipping {ticker} on {current_date.strftime('%Y-%m-%d')}: "
                                f"20d avg dollar volume ${avg_dollar_vol:,.0f} < min ${self.min_avg_dollar_volume:,.0f}"
                            )
                            continue

            if self.min_market_cap > 0:
                meta = metadata.get(ticker, {})
                shares = meta.get("sharesOutstanding")
                if shares and shares > 0 and p_curr is not None:
                    mcap = float(p_curr) * float(shares)
                    if mcap < self.min_market_cap:
                        logger.debug(
                            f"Liquidity Filter: Skipping {ticker} on {current_date.strftime('%Y-%m-%d')}: "
                            f"market cap ${mcap:,.0f} < min ${self.min_market_cap:,.0f}"
                        )
                        continue

            actual_start_date, p_start = _get_last_price_before(prices_df, ticker, start_lookback)
            actual_end_date, p_end = _get_last_price_before(prices_df, ticker, end_lookback)

            if actual_start_date is None or actual_end_date is None or p_start is None or p_end is None:
                continue

            # Ensure actual_start_date is on or before target start_lookback (cannot be after start_lookback)
            if actual_start_date > start_lookback or actual_end_date > end_lookback:
                logger.warning(
                    f"Skipping ticker {ticker} on {current_date.strftime('%Y-%m-%d')}: "
                    f"insufficient trailing price data for lookback (actual start: {actual_start_date.strftime('%Y-%m-%d')} > target start {start_lookback.strftime('%Y-%m-%d')})"
                )
                continue

            # Staleness check: measure gap between target lookback date and actual price date
            start_gap_days = (start_lookback - actual_start_date).days
            end_gap_days = (end_lookback - actual_end_date).days

            if start_gap_days > self.max_staleness_days or end_gap_days > self.max_staleness_days or start_gap_days < 0 or end_gap_days < 0:
                logger.warning(
                    f"Skipping ticker {ticker} on {current_date.strftime('%Y-%m-%d')}: "
                    f"stale price data (start gap: {start_gap_days}d, end gap: {end_gap_days}d > max {self.max_staleness_days}d)"
                )
                continue

            if p_start > 0:
                ret = (p_end / p_start) - 1.0

                # --- FILTER 3: Risk-Adjusted Momentum Ranking ---
                if self.ranking_method == "risk_adjusted":
                    s = _get_valid_series(prices_df, ticker)
                    if s is not None:
                        lookback_prices = s.loc[(s.index >= actual_start_date) & (s.index <= actual_end_date)]
                        daily_returns = lookback_prices.pct_change().dropna()
                        if len(daily_returns) > 10:
                            vol_daily = float(daily_returns.std(ddof=1))
                            vol_annualized = vol_daily * np.sqrt(252)
                            if vol_annualized > 0.0001:
                                momentum_scores[ticker] = ret / vol_annualized
                            else:
                                momentum_scores[ticker] = ret
                        else:
                            momentum_scores[ticker] = ret
                    else:
                        momentum_scores[ticker] = ret
                else:
                    momentum_scores[ticker] = ret

        return pd.Series(momentum_scores, dtype=float)

    def get_detailed_verification(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Generate detailed momentum breakdown for every stock evaluated on current_date.
        
        Returns DataFrame with columns:
        [Ticker, Rank, MomentumScore, Selected, Start_Date, Start_Price, End_Date, End_Price, Status]
        """
        if self.skip_last_month:
            start_lookback = current_date - pd.DateOffset(months=self.lookback_months)
            end_lookback = current_date - pd.DateOffset(months=1)
        else:
            start_lookback = current_date - pd.DateOffset(months=self.lookback_months)
            end_lookback = current_date

        sub_df = prices_df.loc[prices_df.index <= current_date]
        if sub_df.empty:
            return pd.DataFrame()

        if self.universe_file:
            active_tickers = set(load_universe(self.universe_file, date=current_date))
            eligible_columns = [t for t in sub_df.columns if t in active_tickers]
        else:
            eligible_columns = list(sub_df.columns)

        records = []
        for ticker in eligible_columns:
            actual_curr_date, p_curr = _get_last_price_before(prices_df, ticker, current_date)
            if actual_curr_date is None:
                records.append({
                    "Ticker": ticker,
                    "MomentumScore": np.nan,
                    "Start_Date": None,
                    "Start_Price": np.nan,
                    "End_Date": None,
                    "End_Price": np.nan,
                    "Status": "NO_DATA"
                })
                continue

            actual_start_date, p_start = _get_last_price_before(prices_df, ticker, start_lookback)
            actual_end_date, p_end = _get_last_price_before(prices_df, ticker, end_lookback)

            if actual_start_date is None or actual_end_date is None or p_start is None or p_end is None:
                records.append({
                    "Ticker": ticker,
                    "MomentumScore": np.nan,
                    "Start_Date": actual_start_date.strftime("%Y-%m-%d") if actual_start_date is not None else None,
                    "Start_Price": float(p_start) if p_start is not None else np.nan,
                    "End_Date": actual_end_date.strftime("%Y-%m-%d") if actual_end_date is not None else None,
                    "End_Price": float(p_end) if p_end is not None else np.nan,
                    "Status": "INSUFFICIENT_HISTORY"
                })
                continue

            start_gap_days = (start_lookback - actual_start_date).days
            end_gap_days = (end_lookback - actual_end_date).days

            if start_gap_days > self.max_staleness_days or end_gap_days > self.max_staleness_days:
                records.append({
                    "Ticker": ticker,
                    "MomentumScore": np.nan,
                    "Start_Date": actual_start_date.strftime("%Y-%m-%d"),
                    "Start_Price": p_start,
                    "End_Date": actual_end_date.strftime("%Y-%m-%d"),
                    "End_Price": p_end,
                    "Status": "STALE_DATA"
                })
                continue

            if p_start <= 0:
                records.append({
                    "Ticker": ticker,
                    "MomentumScore": np.nan,
                    "Start_Date": actual_start_date.strftime("%Y-%m-%d"),
                    "Start_Price": p_start,
                    "End_Date": actual_end_date.strftime("%Y-%m-%d"),
                    "End_Price": p_end,
                    "Status": "INVALID_PRICE"
                })
                continue

            ret = (p_end / p_start) - 1.0
            records.append({
                "Ticker": ticker,
                "MomentumScore": ret,
                "Start_Date": actual_start_date.strftime("%Y-%m-%d"),
                "Start_Price": p_start,
                "End_Date": actual_end_date.strftime("%Y-%m-%d"),
                "End_Price": p_end,
                "Status": "VALID"
            })

        df_res = pd.DataFrame(records)
        if df_res.empty:
            return df_res

        valid_df = df_res[df_res["Status"] == "VALID"].copy()
        invalid_df = df_res[df_res["Status"] != "VALID"].copy()

        valid_df = valid_df.sort_values(by=["MomentumScore", "Ticker"], ascending=[False, True]).reset_index(drop=True)
        valid_df["Rank"] = valid_df.index + 1

        target_weights = self.generate_target_weights(current_date, prices_df)
        long_selected = {t for t, w in target_weights.items() if w > 0}
        short_selected = {t for t, w in target_weights.items() if w < 0}

        selected_list = []
        for ticker in valid_df["Ticker"]:
            if ticker in long_selected:
                selected_list.append("LONG")
            elif ticker in short_selected:
                selected_list.append("SHORT")
            else:
                selected_list.append("NO")
        valid_df["Selected"] = selected_list

        if not invalid_df.empty:
            invalid_df["Rank"] = np.nan
            invalid_df["Selected"] = "NO"
            final_df = pd.concat([valid_df, invalid_df], ignore_index=True)
        else:
            final_df = valid_df

        cols = ["Ticker", "Rank", "MomentumScore", "Selected", "Start_Date", "Start_Price", "End_Date", "End_Price", "Status"]
        return final_df[cols]

    def _is_ticker_valid_for_rebalance(
        self,
        ticker: str,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame,
        raw_prices_df: Optional[pd.DataFrame] = None
    ) -> bool:
        """
        Check if a ticker is in point-in-time universe, actively trading on current_date, and not delisted.
        """
        if self.universe_file:
            active_tickers = set(load_universe(self.universe_file, date=current_date))
            if ticker not in active_tickers:
                return False

        ref_df = raw_prices_df if raw_prices_df is not None else prices_df
        actual_date, _ = _get_last_price_before(ref_df, ticker, current_date)
        if actual_date is None:
            return False
        series = _get_valid_series(ref_df, ticker)
        if series is None or current_date > series.index[-1]:
            return False
        if (current_date - actual_date).days > self.max_staleness_days:
            return False
        return True

    def generate_target_weights(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame,
        raw_prices_df: Optional[pd.DataFrame] = None,
        volumes_df: Optional[pd.DataFrame] = None
    ) -> Dict[str, float]:
        """
        Select top N momentum stocks (+1/N long weight) and optionally bottom N stocks (-1/N short weight).
        Backfills from next-highest-ranked eligible tickers (rank N+1, N+2...) if top-N tickers are delisted or non-trading.
        """
        momentum_series = self.calculate_momentum_returns(current_date, prices_df, volumes_df=volumes_df)

        if momentum_series.empty:
            return {}

        # Sort momentum returns descending with deterministic secondary sort (ticker alphabetically)
        df_mom = pd.DataFrame({'Momentum': momentum_series}).dropna()
        df_mom['Ticker'] = df_mom.index
        df_sorted = df_mom.sort_values(by=['Momentum', 'Ticker'], ascending=[False, True])

        # Backfill long candidates: iterate down ranked momentum list and select first N valid, actively-trading tickers
        from collections import defaultdict
        sector_counts = defaultdict(int)
        seen_issuers = {}
        metadata = _get_ticker_metadata()

        selected_long_tickers = []
        for ticker in df_sorted['Ticker']:
            if not self._is_ticker_valid_for_rebalance(ticker, current_date, prices_df, raw_prices_df):
                continue

            # --- FILTER 5: Earnings-Proximity Exclusion ---
            if self.earnings_blackout_days > 0:
                if not self.earnings_calendar:
                    if not self._warned_no_earnings:
                        logger.info(
                            f"[Filter Audit] Earnings calendar data source is required as a dependency for earnings blackout filtering ({self.earnings_blackout_days} blackout days). No earnings calendar source available; earnings blackout filter skipped."
                        )
                        self._warned_no_earnings = True
                else:
                    earnings_dates = self.earnings_calendar.get(ticker, [])
                    in_blackout = False
                    for ed_str in earnings_dates:
                        ed_ts = pd.Timestamp(ed_str)
                        if abs((current_date - ed_ts).days) <= int(self.earnings_blackout_days * 1.5):
                            in_blackout = True
                            break
                    if in_blackout:
                        logger.info(
                            f"[Earnings Blackout Audit] Skipping candidate {ticker} on {current_date.strftime('%Y-%m-%d')}: "
                            f"scheduled earnings report within {self.earnings_blackout_days}-day blackout window."
                        )
                        continue

            # --- ISSUER DEDUPLICATION (One share class per parent issuer) ---
            issuer = get_parent_issuer(ticker, metadata)
            if issuer in seen_issuers:
                existing_ticker = seen_issuers[issuer]
                logger.info(
                    f"[Issuer Dedupe Audit] Skipping candidate {ticker} on {current_date.strftime('%Y-%m-%d')}: "
                    f"parent issuer '{issuer}' already represented by higher-ranked position ({existing_ticker})."
                )
                continue

            # --- FILTER 1: Sector Concentration Cap ---
            sec = metadata.get(ticker, {}).get("sector") or "Unknown"
            if self.max_positions_per_sector > 0 and sector_counts[sec] >= self.max_positions_per_sector:
                logger.info(
                    f"[Sector Cap Audit] Skipping candidate {ticker} on {current_date.strftime('%Y-%m-%d')}: "
                    f"sector '{sec}' already reached limit of {sector_counts[sec]} positions (max: {self.max_positions_per_sector})."
                )
                continue

            selected_long_tickers.append(ticker)
            seen_issuers[issuer] = ticker
            sector_counts[sec] += 1
            if len(selected_long_tickers) == self.positions:
                break

        if not selected_long_tickers:
            return {}

        # Pre-trade candidate set assertion: assert candidate set is exactly N elements when enough valid tickers exist
        if len(df_sorted) >= self.positions and self.max_positions_per_sector == 0 and self.earnings_blackout_days == 0:
            assert len(selected_long_tickers) == self.positions, (
                f"Candidate set selection failed: got {len(selected_long_tickers)} candidates, expected exactly {self.positions}"
            )

        # --- REGIME FILTERS & VOLATILITY SCALING ---
        exposure_scale = 1.0
        spy_regime_triggered = False
        mom_regime_triggered = False
        mom_sleeve_ret = None

        # 1. SPY 200d SMA Market Regime Filter
        if self.regime_filter:
            spy_s = None
            if "SPY" in prices_df.columns:
                spy_s = prices_df["SPY"].dropna()
            else:
                spy_s = _get_valid_series(prices_df, "SPY")

            if spy_s is not None and not spy_s.empty:
                spy_sub = spy_s.loc[spy_s.index <= current_date]
                if len(spy_sub) >= 200:
                    sma200 = spy_sub.tail(200).mean()
                    current_spy = spy_sub.iloc[-1]
                    if current_spy < sma200:
                        spy_regime_triggered = True

        # 2. Momentum-Factor-Specific Regime Filter
        if self.momentum_regime_filter:
            mom_sleeve_ret = self.calculate_momentum_sleeve_trailing_return(
                current_date, prices_df, volumes_df=volumes_df, lookback_days=self.momentum_regime_lookback_days
            )
            if mom_sleeve_ret is not None and mom_sleeve_ret < self.momentum_regime_threshold:
                mom_regime_triggered = True

        if spy_regime_triggered or mom_regime_triggered:
            exposure_scale = self.regime_reduced_exposure_pct

        is_independent_mom = mom_regime_triggered and not spy_regime_triggered
        if spy_regime_triggered or mom_regime_triggered:
            logger.info(
                f"[Regime Filter Audit] {current_date.strftime('%Y-%m-%d')}: "
                f"SPY Triggered={spy_regime_triggered}, Mom Factor Triggered={mom_regime_triggered} "
                f"(Sleeve 20d Ret={f'{mom_sleeve_ret*100:.2f}%' if mom_sleeve_ret is not None else 'N/A'}), "
                f"Independent Mom Filter={is_independent_mom}. Exposure Scale={exposure_scale*100:.0f}%"
            )

        # 3. Volatility-Scaled Position Sizing
        if self.vol_scaling:
            realized_vol = self.calculate_realized_volatility(
                current_date, prices_df, lookback_days=self.vol_scaling_lookback_days, selected_tickers=selected_long_tickers
            )
            vol_scale = 1.0
            if realized_vol > 1e-6:
                vol_scale = min(1.0, self.target_volatility / realized_vol)
            exposure_scale *= vol_scale
            logger.info(
                f"[Vol Scaling Audit] {current_date.strftime('%Y-%m-%d')}: "
                f"Realized Vol={realized_vol*100:.2f}%, Target Vol={self.target_volatility*100:.2f}%, "
                f"Vol Scale={vol_scale*100:.1f}%, Total Exposure Scale={exposure_scale*100:.1f}%"
            )

        target_weights: Dict[str, float] = {}

        # Long weights (+1 / N * exposure_scale)
        long_weight_per_stock = (1.0 * exposure_scale) / len(selected_long_tickers)
        for ticker in selected_long_tickers:
            target_weights[ticker] = long_weight_per_stock

        # Short weights (-1 / N) if include_shorts is True
        if self.include_shorts:
            # Bottom N tickers sorted ascending momentum, then Ticker ascending
            df_short_sorted = df_mom.sort_values(by=['Momentum', 'Ticker'], ascending=[True, True])
            long_set = set(selected_long_tickers)
            long_issuers = set(seen_issuers.keys())

            short_seen_issuers = {}
            selected_short_tickers = []
            for ticker in df_short_sorted['Ticker']:
                if ticker in long_set:
                    continue
                issuer = get_parent_issuer(ticker, metadata)
                if issuer in long_issuers:
                    logger.info(
                        f"[Issuer Dedupe Audit] Skipping short candidate {ticker} on {current_date.strftime('%Y-%m-%d')}: "
                        f"parent issuer '{issuer}' already held in long portfolio."
                    )
                    continue
                if issuer in short_seen_issuers:
                    existing_ticker = short_seen_issuers[issuer]
                    logger.info(
                        f"[Issuer Dedupe Audit] Skipping short candidate {ticker} on {current_date.strftime('%Y-%m-%d')}: "
                        f"parent issuer '{issuer}' already represented by higher-ranked short position ({existing_ticker})."
                    )
                    continue
                if self._is_ticker_valid_for_rebalance(ticker, current_date, prices_df, raw_prices_df):
                    selected_short_tickers.append(ticker)
                    short_seen_issuers[issuer] = ticker
                    if len(selected_short_tickers) == self.positions:
                        break

            if len(df_sorted) >= self.positions * 2:
                assert len(selected_short_tickers) == self.positions, "Short candidate set selection failed!"

            if selected_short_tickers:
                short_weight_per_stock = -1.0 / len(selected_short_tickers)
                for ticker in selected_short_tickers:
                    target_weights[ticker] = short_weight_per_stock

            # Assert no stock appears in both legs simultaneously
            final_longs = {t for t, w in target_weights.items() if w > 0}
            final_shorts = {t for t, w in target_weights.items() if w < 0}
            assert final_longs.isdisjoint(final_shorts), "Stock cannot appear in both long and short legs simultaneously!"

        return target_weights


class DualMomentumStrategy(BaseStrategy):
    """
    Example Extension: Absolute + Relative Dual Momentum.
    Ranks stocks by relative momentum, but requires positive absolute return.
    If fewer than N stocks have positive returns, remaining cash is held in risk-free asset / cash.
    """

    def __init__(
        self,
        positions: int = 20,
        lookback_months: int = 12,
        skip_last_month: bool = True,
        universe_file: Optional[str] = None
    ):
        self.positions = positions
        self.lookback_months = lookback_months
        self.skip_last_month = skip_last_month
        self.universe_file = universe_file

    def generate_target_weights(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame
    ) -> Dict[str, float]:
        base_momentum = CrossSectionalMomentumStrategy(
            positions=self.positions,
            lookback_months=self.lookback_months,
            skip_last_month=self.skip_last_month,
            universe_file=self.universe_file
        )
        returns = base_momentum.calculate_momentum_returns(current_date, prices_df)
        if returns.empty:
            return {}

        # Filter only positive return stocks (Absolute momentum filter)
        positive_returns = returns[returns > 0].sort_values(ascending=False)
        selected = positive_returns.head(self.positions).index.tolist()

        if not selected:
            return {}

        weight_per_stock = 1.0 / self.positions  # Keep 1/N weight, remaining in cash if < N
        return {ticker: weight_per_stock for ticker in selected}


_MULTI_FACTOR_CACHE: Dict[Tuple, Tuple[pd.DataFrame, pd.DataFrame]] = {}


class MultiFactorCompositeStrategy(BaseStrategy):
    """
    Multi-Factor Composite Strategy.

    Blends trailing 12-1 Momentum, Quality, and Low-Volatility factor signals into a
    single composite score per stock using cross-sectional Z-score normalization on
    each rebalance date. Reuses existing universe filtering, point-in-time membership,
    sector cap, liquidity floor, earnings blackout, and market regime filters.
    """

    def __init__(
        self,
        positions: int = 20,
        lookback_months: int = 12,
        skip_last_month: bool = True,
        include_shorts: bool = False,
        max_staleness_days: int = 14,
        universe_file: Optional[str] = None,
        max_positions_per_sector: int = 0,
        min_avg_dollar_volume: float = 0.0,
        min_market_cap: float = 0.0,
        ranking_method: str = "raw_return",
        regime_filter: bool = False,
        regime_reduced_exposure_pct: float = 0.5,
        earnings_blackout_days: int = 0,
        earnings_calendar: Optional[Dict[str, List[str]]] = None,
        factor_weights: Optional[Dict[str, float]] = None,
        momentum_regime_filter: bool = False,
        momentum_regime_lookback_days: int = 20,
        momentum_regime_threshold: float = 0.0,
        vol_scaling: bool = False,
        vol_scaling_lookback_days: int = 20,
        target_volatility: float = 0.25
    ):
        self.positions: int = positions
        self.lookback_months: int = lookback_months
        self.skip_last_month: bool = skip_last_month
        self.include_shorts: bool = include_shorts
        self.max_staleness_days: int = max_staleness_days
        self.universe_file: Optional[str] = universe_file
        self.max_positions_per_sector: int = max_positions_per_sector
        self.min_avg_dollar_volume: float = min_avg_dollar_volume
        self.min_market_cap: float = min_market_cap
        self.ranking_method: str = ranking_method
        self.regime_filter: bool = regime_filter
        self.regime_reduced_exposure_pct: float = regime_reduced_exposure_pct
        self.earnings_blackout_days: int = earnings_blackout_days
        self.earnings_calendar: Optional[Dict[str, List[str]]] = earnings_calendar
        self.momentum_regime_filter: bool = momentum_regime_filter
        self.momentum_regime_lookback_days: int = momentum_regime_lookback_days
        self.momentum_regime_threshold: float = momentum_regime_threshold
        self.vol_scaling: bool = vol_scaling
        self.vol_scaling_lookback_days: int = vol_scaling_lookback_days
        self.target_volatility: float = target_volatility
        self._warned_no_earnings: bool = False
        self._warned_fundamental_data: bool = False

        # Configurable factor weights (default: equal weights 1/3 each)
        default_weights = {"momentum": 1.0 / 3.0, "quality": 1.0 / 3.0, "low_vol": 1.0 / 3.0}
        if factor_weights:
            weights = factor_weights.copy()
            total_w = sum(weights.values())
            if total_w > 0:
                self.factor_weights = {k: v / total_w for k, v in weights.items()}
            else:
                self.factor_weights = default_weights
        else:
            self.factor_weights = default_weights

    def calculate_momentum_sleeve_trailing_return(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame,
        volumes_df: Optional[pd.DataFrame] = None,
        lookback_days: int = 20
    ) -> Optional[float]:
        """
        Computes trailing equal-weighted return of the top-N momentum sleeve over lookback_days trading days up to current_date.
        """
        available_dates = prices_df.index[prices_df.index <= current_date]
        if len(available_dates) <= lookback_days:
            return None

        lookback_date = available_dates[-lookback_days - 1]

        mom_series = self.calculate_momentum_returns(lookback_date, prices_df, volumes_df=volumes_df)
        if mom_series.empty:
            return None

        df_mom = pd.DataFrame({'Momentum': mom_series}).dropna()
        df_mom['Ticker'] = df_mom.index
        df_sorted = df_mom.sort_values(by=['Momentum', 'Ticker'], ascending=[False, True])

        sleeve_returns = []
        for ticker in df_sorted['Ticker']:
            if ticker == "SPY":
                continue
            p_lookback_date, p_lookback = _get_last_price_before(prices_df, ticker, lookback_date)
            p_curr_date, p_curr = _get_last_price_before(prices_df, ticker, current_date)
            if p_lookback is not None and p_curr is not None and p_lookback > 0 and p_curr > 0:
                sleeve_returns.append((p_curr / p_lookback) - 1.0)
                if len(sleeve_returns) == self.positions:
                    break

        if not sleeve_returns:
            return None

        return float(np.mean(sleeve_returns))

    def calculate_realized_volatility(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame,
        lookback_days: int = 20,
        selected_tickers: Optional[List[str]] = None
    ) -> float:
        """
        Computes trailing realized annualized volatility over lookback_days trading days.
        """
        available_dates = prices_df.index[prices_df.index <= current_date]
        if len(available_dates) < lookback_days + 1:
            return 0.0

        sub_dates = available_dates[-(lookback_days + 1):]
        sub_prices = prices_df.loc[sub_dates]

        if selected_tickers:
            valid_cols = [t for t in selected_tickers if t in sub_prices.columns]
        else:
            valid_cols = [c for c in sub_prices.columns if c != "SPY"]

        if not valid_cols:
            return 0.0

        pct_changes = sub_prices[valid_cols].pct_change().dropna(how="all")
        daily_returns = pct_changes.mean(axis=1).dropna()

        if len(daily_returns) < 2:
            return 0.0

        return float(daily_returns.std(ddof=1) * np.sqrt(252))

    def _calculate_quality_score(self, ticker: str, metadata: Dict[str, dict]) -> float:
        """
        Calculate raw quality factor score for a stock.
        Quality composite components:
          (a) Trailing ROIC or ROE
          (b) Free cash flow margin (FCF / Revenue)
          (c) Trailing change in Debt/Equity ratio (favor decreasing leverage)

        NOTE ON FUNDAMENTAL DATA DEPENDENCY:
        Point-in-time historical quarterly financial statements (ROIC/ROE, FCF, Revenue, Debt, Equity)
        for 1000 stocks are required as a data dependency. Recommended sources/APIs:
          - Financial Modeling Prep (FMP) API (`/key-metrics-ttm/`, `/financial-growth/`)
          - SEC EDGAR point-in-time filing feeds / FactSet / Alpha Vantage.
        In absence of live point-in-time historical fundamental API feeds, this function checks
        available ticker metadata or fundamental cache files, defaulting gracefully to 0.0 (neutral)
        so cross-sectional z-scoring operates safely.
        """
        if not self._warned_fundamental_data:
            logger.info(
                "[Fundamental Data Dependency Flagged] Point-in-time historical financial statements "
                "(quarterly ROIC/ROE, FCF Margin, Debt/Equity changes) require a fundamental data feed "
                "(recommended: Financial Modeling Prep API, FactSet, or SEC EDGAR filings). "
                "Evaluating Quality Score from available ticker metadata/fundamental cache where present, "
                "defaulting to neutral cross-sectional score (0.0) when data unavailable."
            )
            self._warned_fundamental_data = True

        meta = metadata.get(ticker, {})
        sub_scores = []

        # (a) ROE or ROIC
        roe = meta.get("returnOnEquity") or meta.get("returnOnAssets")
        if roe is not None:
            sub_scores.append(float(roe))

        # (b) Free cash flow margin (FCF / Revenue)
        fcf = meta.get("freeCashflow")
        rev = meta.get("totalRevenue")
        if fcf is not None and rev is not None and float(rev) > 0:
            sub_scores.append(float(fcf) / float(rev))

        # (c) Trailing change in Debt/Equity ratio (favor decreasing leverage)
        de_change = meta.get("debtToEquityChange")
        if de_change is not None:
            sub_scores.append(-float(de_change))  # Negative change means decreasing leverage -> positive quality

        if sub_scores:
            return float(np.mean(sub_scores))
        return 0.0

    def calculate_multi_factor_table(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame,
        volumes_df: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Calculate raw factor scores (Momentum, Quality, Low-Vol) for eligible candidates,
        and perform cross-sectional Z-score normalization fresh for current_date.

        Returns DataFrame with columns:
        [Ticker, Raw_Mom, Raw_Qual, Raw_Vol, Raw_LowVol, Z_Mom, Z_Qual, Z_LowVol, CompositeScore, Start_Date, Start_Price, End_Date, End_Price, Status]
        """
        cache_key = (
            pd.Timestamp(current_date),
            str(self.universe_file),
            self.lookback_months,
            self.skip_last_month,
            self.ranking_method,
            self.min_avg_dollar_volume,
            self.min_market_cap
        )

        w_mom = self.factor_weights.get("momentum", 1/3)
        w_qual = self.factor_weights.get("quality", 1/3)
        w_lowvol = self.factor_weights.get("low_vol", 1/3)

        if cache_key in _MULTI_FACTOR_CACHE:
            valid_df, invalid_df = _MULTI_FACTOR_CACHE[cache_key]
            valid_df = valid_df.copy()
            invalid_df = invalid_df.copy()
            
            valid_df["CompositeScore"] = (
                w_mom * valid_df["Z_Mom"] +
                w_qual * valid_df["Z_Qual"] +
                w_lowvol * valid_df["Z_LowVol"]
            )
            if not invalid_df.empty:
                for c in ["Z_Mom", "Z_Qual", "Z_LowVol", "CompositeScore"]:
                    invalid_df[c] = np.nan
                return pd.concat([valid_df, invalid_df], ignore_index=True)
            return valid_df

        if self.skip_last_month:
            start_lookback = current_date - pd.DateOffset(months=self.lookback_months)
            end_lookback = current_date - pd.DateOffset(months=1)
        else:
            start_lookback = current_date - pd.DateOffset(months=self.lookback_months)
            end_lookback = current_date

        sub_df = prices_df.loc[prices_df.index <= current_date]
        if sub_df.empty:
            return pd.DataFrame()

        # Point-in-time constituent filtering
        if self.universe_file and "custom_momentum" in str(self.universe_file).lower():
            candidate_list = load_universe(self.universe_file, date=current_date)
            if not hasattr(self, "_filter_engine"):
                self._filter_engine = CustomUniverseFilter()
            active_list, _ = self._filter_engine.filter_universe_on_date(
                rebalance_date=current_date,
                candidate_tickers=candidate_list,
                prices_df=prices_df,
                volumes_df=volumes_df,
                max_staleness_days=self.max_staleness_days
            )
            active_tickers = set(active_list)
            eligible_columns = [t for t in sub_df.columns if t in active_tickers]
        elif self.universe_file:
            active_tickers = set(load_universe(self.universe_file, date=current_date))
            eligible_columns = [t for t in sub_df.columns if t in active_tickers]
        else:
            eligible_columns = list(sub_df.columns)

        metadata = _get_ticker_metadata()
        records = []

        for ticker in eligible_columns:
            actual_curr_date, p_curr = _get_last_price_before(prices_df, ticker, current_date)
            if actual_curr_date is None:
                records.append({
                    "Ticker": ticker,
                    "Raw_Mom": np.nan,
                    "Raw_Qual": np.nan,
                    "Raw_Vol": np.nan,
                    "Raw_LowVol": np.nan,
                    "Start_Date": None,
                    "Start_Price": np.nan,
                    "End_Date": None,
                    "End_Price": np.nan,
                    "Status": "NO_DATA"
                })
                continue

            # Liquidity Floor Filter
            if self.min_avg_dollar_volume > 0 and volumes_df is not None and ticker in volumes_df.columns:
                p_sub = prices_df[ticker].loc[:current_date].dropna().tail(20)
                if not p_sub.empty:
                    v_sub = volumes_df[ticker].reindex(p_sub.index).fillna(0)
                    if v_sub.sum() > 0:
                        avg_dollar_vol = float((p_sub * v_sub).mean())
                        if avg_dollar_vol < self.min_avg_dollar_volume:
                            records.append({
                                "Ticker": ticker,
                                "Raw_Mom": np.nan,
                                "Raw_Qual": np.nan,
                                "Raw_Vol": np.nan,
                                "Raw_LowVol": np.nan,
                                "Start_Date": None,
                                "Start_Price": np.nan,
                                "End_Date": None,
                                "End_Price": np.nan,
                                "Status": "BELOW_LIQUIDITY_FLOOR"
                            })
                            continue

            if self.min_market_cap > 0:
                meta = metadata.get(ticker, {})
                shares = meta.get("sharesOutstanding")
                if shares and shares > 0 and p_curr is not None:
                    mcap = float(p_curr) * float(shares)
                    if mcap < self.min_market_cap:
                        records.append({
                            "Ticker": ticker,
                            "Raw_Mom": np.nan,
                            "Raw_Qual": np.nan,
                            "Raw_Vol": np.nan,
                            "Raw_LowVol": np.nan,
                            "Start_Date": None,
                            "Start_Price": np.nan,
                            "End_Date": None,
                            "End_Price": np.nan,
                            "Status": "BELOW_MARKET_CAP_FLOOR"
                        })
                        continue

            actual_start_date, p_start = _get_last_price_before(prices_df, ticker, start_lookback)
            actual_end_date, p_end = _get_last_price_before(prices_df, ticker, end_lookback)

            if actual_start_date is None or actual_end_date is None or p_start is None or p_end is None:
                records.append({
                    "Ticker": ticker,
                    "Raw_Mom": np.nan,
                    "Raw_Qual": np.nan,
                    "Raw_Vol": np.nan,
                    "Raw_LowVol": np.nan,
                    "Start_Date": actual_start_date.strftime("%Y-%m-%d") if actual_start_date is not None else None,
                    "Start_Price": float(p_start) if p_start is not None else np.nan,
                    "End_Date": actual_end_date.strftime("%Y-%m-%d") if actual_end_date is not None else None,
                    "End_Price": float(p_end) if p_end is not None else np.nan,
                    "Status": "INSUFFICIENT_HISTORY"
                })
                continue

            start_gap_days = (start_lookback - actual_start_date).days
            end_gap_days = (end_lookback - actual_end_date).days

            if start_gap_days > self.max_staleness_days or end_gap_days > self.max_staleness_days:
                records.append({
                    "Ticker": ticker,
                    "Raw_Mom": np.nan,
                    "Raw_Qual": np.nan,
                    "Raw_Vol": np.nan,
                    "Raw_LowVol": np.nan,
                    "Start_Date": actual_start_date.strftime("%Y-%m-%d"),
                    "Start_Price": p_start,
                    "End_Date": actual_end_date.strftime("%Y-%m-%d"),
                    "End_Price": p_end,
                    "Status": "STALE_DATA"
                })
                continue

            if p_start <= 0:
                records.append({
                    "Ticker": ticker,
                    "Raw_Mom": np.nan,
                    "Raw_Qual": np.nan,
                    "Raw_Vol": np.nan,
                    "Raw_LowVol": np.nan,
                    "Start_Date": actual_start_date.strftime("%Y-%m-%d"),
                    "Start_Price": p_start,
                    "End_Date": actual_end_date.strftime("%Y-%m-%d"),
                    "End_Price": p_end,
                    "Status": "INVALID_PRICE"
                })
                continue

            # 1. Raw Momentum
            raw_mom = (p_end / p_start) - 1.0

            # 2. Raw Volatility & Low-Volatility Signal
            s = _get_valid_series(prices_df, ticker)
            vol_annualized = np.nan
            if s is not None:
                lookback_prices = s.loc[(s.index >= actual_start_date) & (s.index <= actual_end_date)]
                daily_returns = lookback_prices.pct_change().dropna()
                if len(daily_returns) > 10:
                    vol_daily = float(daily_returns.std(ddof=1))
                    vol_annualized = vol_daily * np.sqrt(252)

            if self.ranking_method == "risk_adjusted" and not np.isnan(vol_annualized) and vol_annualized > 0.0001:
                raw_mom = raw_mom / vol_annualized

            raw_vol = vol_annualized if not np.isnan(vol_annualized) else 0.30
            raw_low_vol = -raw_vol  # Inverse of realized volatility (higher raw_low_vol = lower volatility)

            # 3. Raw Quality
            raw_qual = self._calculate_quality_score(ticker, metadata)

            records.append({
                "Ticker": ticker,
                "Raw_Mom": raw_mom,
                "Raw_Qual": raw_qual,
                "Raw_Vol": raw_vol,
                "Raw_LowVol": raw_low_vol,
                "Start_Date": actual_start_date.strftime("%Y-%m-%d"),
                "Start_Price": p_start,
                "End_Date": actual_end_date.strftime("%Y-%m-%d"),
                "End_Price": p_end,
                "Status": "VALID"
            })

        df_res = pd.DataFrame(records)
        if df_res.empty:
            return df_res

        valid_df = df_res[df_res["Status"] == "VALID"].copy()
        invalid_df = df_res[df_res["Status"] != "VALID"].copy()

        if valid_df.empty:
            return df_res

        # --- CROSS-SECTIONAL Z-SCORE NORMALIZATION ON CURRENT REBALANCE DATE ---
        w_mom = self.factor_weights.get("momentum", 1/3)
        w_qual = self.factor_weights.get("quality", 1/3)
        w_lowvol = self.factor_weights.get("low_vol", 1/3)

        # Z-score Momentum
        mom_mean = valid_df["Raw_Mom"].mean()
        mom_std = valid_df["Raw_Mom"].std(ddof=1)
        valid_df["Z_Mom"] = (valid_df["Raw_Mom"] - mom_mean) / mom_std if (not np.isnan(mom_std) and mom_std > 1e-8) else 0.0

        # Z-score Quality
        qual_mean = valid_df["Raw_Qual"].mean()
        qual_std = valid_df["Raw_Qual"].std(ddof=1)
        valid_df["Z_Qual"] = (valid_df["Raw_Qual"] - qual_mean) / qual_std if (not np.isnan(qual_std) and qual_std > 1e-8) else 0.0

        # Z-score Low Volatility
        lowvol_mean = valid_df["Raw_LowVol"].mean()
        lowvol_std = valid_df["Raw_LowVol"].std(ddof=1)
        valid_df["Z_LowVol"] = (valid_df["Raw_LowVol"] - lowvol_mean) / lowvol_std if (not np.isnan(lowvol_std) and lowvol_std > 1e-8) else 0.0

        # Store computed Z-scores in cache for fast re-use across weight combinations
        _MULTI_FACTOR_CACHE[cache_key] = (valid_df.copy(), invalid_df.copy())

        # Weighted Composite Score
        valid_df["CompositeScore"] = (
            w_mom * valid_df["Z_Mom"] +
            w_qual * valid_df["Z_Qual"] +
            w_lowvol * valid_df["Z_LowVol"]
        )

        if not invalid_df.empty:
            for c in ["Z_Mom", "Z_Qual", "Z_LowVol", "CompositeScore"]:
                invalid_df[c] = np.nan
            final_df = pd.concat([valid_df, invalid_df], ignore_index=True)
        else:
            final_df = valid_df

        return final_df

    def _is_ticker_valid_for_rebalance(
        self,
        ticker: str,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame,
        raw_prices_df: Optional[pd.DataFrame] = None
    ) -> bool:
        if self.universe_file:
            active_tickers = set(load_universe(self.universe_file, date=current_date))
            if ticker not in active_tickers:
                return False

        ref_df = raw_prices_df if raw_prices_df is not None else prices_df
        actual_date, _ = _get_last_price_before(ref_df, ticker, current_date)
        if actual_date is None:
            return False
        series = _get_valid_series(ref_df, ticker)
        if series is None or current_date > series.index[-1]:
            return False
        if (current_date - actual_date).days > self.max_staleness_days:
            return False
        return True

    def generate_target_weights(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame,
        raw_prices_df: Optional[pd.DataFrame] = None,
        volumes_df: Optional[pd.DataFrame] = None
    ) -> Dict[str, float]:
        """
        Generate target weights based on Multi-Factor Composite ranking with existing risk filters.
        """
        df_factors = self.calculate_multi_factor_table(current_date, prices_df, volumes_df=volumes_df)

        if df_factors.empty or "CompositeScore" not in df_factors.columns:
            return {}

        valid_df = df_factors[df_factors["Status"] == "VALID"].copy()
        if valid_df.empty:
            return {}

        # Sort descending by CompositeScore, deterministic secondary sort by Ticker
        df_sorted = valid_df.sort_values(by=["CompositeScore", "Ticker"], ascending=[False, True])

        from collections import defaultdict
        sector_counts = defaultdict(int)
        seen_issuers = {}
        metadata = _get_ticker_metadata()

        selected_long_tickers = []
        for ticker in df_sorted["Ticker"]:
            if not self._is_ticker_valid_for_rebalance(ticker, current_date, prices_df, raw_prices_df):
                continue

            # Earnings blackout filter
            if self.earnings_blackout_days > 0:
                if not self.earnings_calendar:
                    if not self._warned_no_earnings:
                        logger.info(
                            f"[Filter Audit] Earnings calendar data source is required as a dependency for earnings blackout filtering ({self.earnings_blackout_days} blackout days). No earnings calendar source available; earnings blackout filter skipped."
                        )
                        self._warned_no_earnings = True
                else:
                    earnings_dates = self.earnings_calendar.get(ticker, [])
                    in_blackout = False
                    for ed_str in earnings_dates:
                        ed_ts = pd.Timestamp(ed_str)
                        if abs((current_date - ed_ts).days) <= int(self.earnings_blackout_days * 1.5):
                            in_blackout = True
                            break
                    if in_blackout:
                        logger.info(
                            f"[Earnings Blackout Audit] Skipping candidate {ticker} on {current_date.strftime('%Y-%m-%d')}: "
                            f"scheduled earnings report within {self.earnings_blackout_days}-day blackout window."
                        )
                        continue

            # Issuer deduplication
            issuer = get_parent_issuer(ticker, metadata)
            if issuer in seen_issuers:
                existing_ticker = seen_issuers[issuer]
                logger.info(
                    f"[Issuer Dedupe Audit] Skipping candidate {ticker} on {current_date.strftime('%Y-%m-%d')}: "
                    f"parent issuer '{issuer}' already represented by higher-ranked position ({existing_ticker})."
                )
                continue

            # Sector cap filter
            sec = metadata.get(ticker, {}).get("sector") or "Unknown"
            if self.max_positions_per_sector > 0 and sector_counts[sec] >= self.max_positions_per_sector:
                logger.info(
                    f"[Sector Cap Audit] Skipping candidate {ticker} on {current_date.strftime('%Y-%m-%d')}: "
                    f"sector '{sec}' already reached limit of {sector_counts[sec]} positions (max: {self.max_positions_per_sector})."
                )
                continue

            selected_long_tickers.append(ticker)
            seen_issuers[issuer] = ticker
            sector_counts[sec] += 1
            if len(selected_long_tickers) == self.positions:
                break

        if not selected_long_tickers:
            return {}

        # --- REGIME FILTERS & VOLATILITY SCALING ---
        exposure_scale = 1.0
        spy_regime_triggered = False
        mom_regime_triggered = False
        mom_sleeve_ret = None

        # 1. SPY 200d SMA Market Regime Filter
        if self.regime_filter:
            spy_s = None
            if "SPY" in prices_df.columns:
                spy_s = prices_df["SPY"].dropna()
            else:
                spy_s = _get_valid_series(prices_df, "SPY")

            if spy_s is not None and not spy_s.empty:
                spy_sub = spy_s.loc[spy_s.index <= current_date]
                if len(spy_sub) >= 200:
                    sma200 = spy_sub.tail(200).mean()
                    current_spy = spy_sub.iloc[-1]
                    if current_spy < sma200:
                        spy_regime_triggered = True

        # 2. Momentum-Factor-Specific Regime Filter
        if self.momentum_regime_filter:
            mom_sleeve_ret = self.calculate_momentum_sleeve_trailing_return(
                current_date, prices_df, volumes_df=volumes_df, lookback_days=self.momentum_regime_lookback_days
            )
            if mom_sleeve_ret is not None and mom_sleeve_ret < self.momentum_regime_threshold:
                mom_regime_triggered = True

        if spy_regime_triggered or mom_regime_triggered:
            exposure_scale = self.regime_reduced_exposure_pct

        is_independent_mom = mom_regime_triggered and not spy_regime_triggered
        if spy_regime_triggered or mom_regime_triggered:
            logger.info(
                f"[Regime Filter Audit] {current_date.strftime('%Y-%m-%d')}: "
                f"SPY Triggered={spy_regime_triggered}, Mom Factor Triggered={mom_regime_triggered} "
                f"(Sleeve 20d Ret={f'{mom_sleeve_ret*100:.2f}%' if mom_sleeve_ret is not None else 'N/A'}), "
                f"Independent Mom Filter={is_independent_mom}. Exposure Scale={exposure_scale*100:.0f}%"
            )

        # 3. Volatility-Scaled Position Sizing
        if self.vol_scaling:
            realized_vol = self.calculate_realized_volatility(
                current_date, prices_df, lookback_days=self.vol_scaling_lookback_days, selected_tickers=selected_long_tickers
            )
            vol_scale = 1.0
            if realized_vol > 1e-6:
                vol_scale = min(1.0, self.target_volatility / realized_vol)
            exposure_scale *= vol_scale
            logger.info(
                f"[Vol Scaling Audit] {current_date.strftime('%Y-%m-%d')}: "
                f"Realized Vol={realized_vol*100:.2f}%, Target Vol={self.target_volatility*100:.2f}%, "
                f"Vol Scale={vol_scale*100:.1f}%, Total Exposure Scale={exposure_scale*100:.1f}%"
            )

        target_weights: Dict[str, float] = {}
        long_weight_per_stock = (1.0 * exposure_scale) / len(selected_long_tickers)
        for ticker in selected_long_tickers:
            target_weights[ticker] = long_weight_per_stock

        if self.include_shorts:
            df_short_sorted = valid_df.sort_values(by=["CompositeScore", "Ticker"], ascending=[True, True])
            long_set = set(selected_long_tickers)
            long_issuers = set(seen_issuers.keys())

            short_seen_issuers = {}
            selected_short_tickers = []
            for ticker in df_short_sorted["Ticker"]:
                if ticker in long_set:
                    continue
                issuer = get_parent_issuer(ticker, metadata)
                if issuer in long_issuers or issuer in short_seen_issuers:
                    continue
                if self._is_ticker_valid_for_rebalance(ticker, current_date, prices_df, raw_prices_df):
                    selected_short_tickers.append(ticker)
                    short_seen_issuers[issuer] = ticker
                    if len(selected_short_tickers) == self.positions:
                        break

            if selected_short_tickers:
                short_weight_per_stock = -1.0 / len(selected_short_tickers)
                for ticker in selected_short_tickers:
                    target_weights[ticker] = short_weight_per_stock

        return target_weights

    def get_detailed_verification(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Generate detailed composite score breakdown for current_date.
        """
        df_factors = self.calculate_multi_factor_table(current_date, prices_df)
        if df_factors.empty:
            return df_factors

        valid_df = df_factors[df_factors["Status"] == "VALID"].copy()
        invalid_df = df_factors[df_factors["Status"] != "VALID"].copy()

        if not valid_df.empty:
            valid_df = valid_df.sort_values(by=["CompositeScore", "Ticker"], ascending=[False, True]).reset_index(drop=True)
            valid_df["Rank"] = valid_df.index + 1

            target_weights = self.generate_target_weights(current_date, prices_df)
            long_selected = {t for t, w in target_weights.items() if w > 0}
            short_selected = {t for t, w in target_weights.items() if w < 0}

            selected_list = []
            for ticker in valid_df["Ticker"]:
                if ticker in long_selected:
                    selected_list.append("LONG")
                elif ticker in short_selected:
                    selected_list.append("SHORT")
                else:
                    selected_list.append("NO")
            valid_df["Selected"] = selected_list

        if not invalid_df.empty:
            invalid_df["Rank"] = np.nan
            invalid_df["Selected"] = "NO"
            final_df = pd.concat([valid_df, invalid_df], ignore_index=True)
        else:
            final_df = valid_df

        cols = [
            "Ticker", "Rank", "CompositeScore", "Raw_Mom", "Raw_Qual", "Raw_LowVol",
            "Z_Mom", "Z_Qual", "Z_LowVol", "Selected", "Start_Date", "Start_Price", "End_Date", "End_Price", "Status"
        ]
        return final_df[[c for c in cols if c in final_df.columns]]

