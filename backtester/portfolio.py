"""
Portfolio and Backtest Engine module.

Manages cash, shares, portfolio valuation, trade log execution, and rebalance execution.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple, Optional
try:
    from backtester.strategy import BaseStrategy
    from backtester.utils import get_rebalance_dates
except ImportError:
    from strategy import BaseStrategy
    from utils import get_rebalance_dates


class TradeRecord:
    """Represents an executed trade transaction."""
    def __init__(
        self,
        date: pd.Timestamp,
        ticker: str,
        action: str,
        price: float,
        shares: float,
        portfolio_value: float
    ):
        self.date = date
        self.ticker = ticker
        self.action = action.upper()  # 'BUY' or 'SELL'
        self.price = price
        self.shares = shares
        self.portfolio_value = portfolio_value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Date": self.date.strftime("%Y-%m-%d"),
            "Ticker": self.ticker,
            "Action": self.action,
            "Price": round(self.price, 2),
            "Shares": round(self.shares, 6),
            "Portfolio Value": round(self.portfolio_value, 2)
        }


class PortfolioHistoryRecord:
    """Represents a daily snapshot of portfolio state."""
    def __init__(self, date: pd.Timestamp, portfolio_value: float, cash: float):
        self.date = date
        self.portfolio_value = portfolio_value
        self.cash = cash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Date": self.date.strftime("%Y-%m-%d"),
            "Portfolio Value": round(self.portfolio_value, 2),
            "Cash": round(self.cash, 2)
        }


class RebalanceSnapshotRecord:
    """Represents an exact snapshot of portfolio holdings immediately following a rebalance."""
    def __init__(
        self,
        date: pd.Timestamp,
        signal_date: pd.Timestamp,
        portfolio_value: float,
        cash: float,
        holdings: List[Dict[str, Any]],
        exited_tickers: List[str]
    ):
        self.date = date
        self.signal_date = signal_date
        self.portfolio_value = portfolio_value
        self.cash = cash
        self.holdings = holdings
        self.exited_tickers = exited_tickers

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date.strftime("%Y-%m-%d"),
            "signalDate": self.signal_date.strftime("%Y-%m-%d"),
            "portfolioValue": round(self.portfolio_value, 2),
            "cash": round(self.cash, 2),
            "count": len(self.holdings),
            "tickers": [h["ticker"] for h in self.holdings],
            "details": self.holdings,
            "exitedTickers": sorted(self.exited_tickers)
        }


# Default known delisting metadata map
DEFAULT_DELISTING_METADATA: Dict[str, Dict[str, Any]] = {
    # Bankruptcy / Liquidation (worthless equity -> $0 write-down)
    "SIVB": {"reason": "bankruptcy", "final_price": 0.0},
    "FRC": {"reason": "bankruptcy", "final_price": 0.0},
    "SBNY": {"reason": "bankruptcy", "final_price": 0.0},
    "BBBY": {"reason": "bankruptcy", "final_price": 0.0},
    "ENRN": {"reason": "bankruptcy", "final_price": 0.0},
    "LEH": {"reason": "bankruptcy", "final_price": 0.0},
    # Acquisition / Buyout
    "TWTR": {"reason": "acquisition", "final_price": 54.20},
    "ATVI": {"reason": "acquisition", "final_price": 95.00},
    "ALXN": {"reason": "acquisition"},
    "CELG": {"reason": "acquisition"},
    "MON": {"reason": "acquisition"},
    "DRE": {"reason": "acquisition"},
    "PXD": {"reason": "acquisition"},
}


_PORTFOLIO_SERIES_CACHE: Dict[Tuple[int, str], Optional[pd.Series]] = {}

def clear_portfolio_cache():
    global _PORTFOLIO_SERIES_CACHE
    _PORTFOLIO_SERIES_CACHE.clear()


def _get_portfolio_valid_series(df: pd.DataFrame, ticker: str) -> Optional[pd.Series]:
    cache_key = (id(df), ticker)
    if cache_key in _PORTFOLIO_SERIES_CACHE:
        return _PORTFOLIO_SERIES_CACHE[cache_key]
    if ticker not in df.columns:
        _PORTFOLIO_SERIES_CACHE[cache_key] = None
        return None
    s = df[ticker].dropna()
    _PORTFOLIO_SERIES_CACHE[cache_key] = s
    return s


def _get_portfolio_last_price(df: pd.DataFrame, ticker: str, target_date: pd.Timestamp) -> float:
    s = _get_portfolio_valid_series(df, ticker)
    if s is None or s.empty:
        return 0.0
    idx = s.index.searchsorted(target_date, side='right') - 1
    if idx < 0:
        return 0.0
    p = float(s.iloc[idx])
    return p if p > 0 else 0.0


class BacktestEngine:
    """
    Simulates portfolio execution and rebalancing over time using historical price data.
    Supports both long-only and long-short portfolios with proper cash, short liabilities, and trade logging.
    """

    def __init__(
        self,
        initial_capital: float,
        strategy: BaseStrategy,
        rebalance_frequency: str = "monthly",
        delisting_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
        stop_loss_pct: Optional[float] = None,
        stop_loss_cash_pct: float = 1.0,
        stop_loss_reentry_mode: str = "recovery",
        stop_loss_reentry_pct: Optional[float] = None,
        stop_loss_reentry_months: int = 1
    ):
        """
        Initialize Engine.

        Args:
            initial_capital: Initial portfolio cash in USD ($).
            strategy: Strategy object implementing BaseStrategy interface.
            rebalance_frequency: Rebalance frequency ('monthly', 'weekly', 'quarterly').
            delisting_metadata: Optional custom dict mapping ticker -> {"reason": str, "final_price": float}.
            stop_loss_pct: Maximum allowable trailing drawdown from peak before de-risking (e.g. 0.15 for 15%).
            stop_loss_cash_pct: Percentage of portfolio converted to cash when stop loss triggers (default: 1.0 = 100%).
            stop_loss_reentry_mode: Re-entry trigger mode ('recovery' or 'months').
            stop_loss_reentry_pct: Re-entry recovery percentage threshold (defaults to stop_loss_pct if None).
            stop_loss_reentry_months: Number of rebalance periods in cash before auto re-entering if mode=='months'.
        """
        self.initial_capital: float = initial_capital
        self.strategy: BaseStrategy = strategy
        self.rebalance_frequency: str = rebalance_frequency

        # Stop-loss parameters
        self.stop_loss_pct: Optional[float] = stop_loss_pct
        self.stop_loss_cash_pct: float = stop_loss_cash_pct
        self.stop_loss_reentry_mode: str = stop_loss_reentry_mode
        self.stop_loss_reentry_pct: Optional[float] = stop_loss_reentry_pct if stop_loss_reentry_pct is not None else stop_loss_pct
        self.stop_loss_reentry_months: int = stop_loss_reentry_months

        # Stop-loss state tracking
        self.running_peak_value: float = initial_capital
        self.in_stop_loss: bool = False
        self.stop_loss_trigger_date: Optional[pd.Timestamp] = None
        self.stop_loss_trough_value: float = initial_capital
        self.stop_loss_trigger_peak: float = initial_capital
        self.stop_loss_rebalance_count_in_cash: int = 0
        self.stop_loss_trigger_count: int = 0
        self.whipsaw_count: int = 0

        # Delisting metadata registry
        self.delisting_metadata: Dict[str, Dict[str, Any]] = DEFAULT_DELISTING_METADATA.copy()
        if delisting_metadata:
            for k, v in delisting_metadata.items():
                self.delisting_metadata[k.upper()] = v
        self.delisted_records: List[Dict[str, Any]] = []

        # State variables
        self.cash: float = initial_capital
        self.long_positions: Dict[str, float] = {}   # ticker -> long shares count
        self.short_positions: Dict[str, float] = {}  # ticker -> short shares count
        self.positions: Dict[str, float] = {}        # ticker -> signed shares (positive long, negative short)
        self._ticker_last_valid_dates: Optional[Dict[str, pd.Timestamp]] = None
        self.trade_logs: List[TradeRecord] = []
        self.portfolio_logs: List[PortfolioHistoryRecord] = []
        self.rebalance_snapshots: List[RebalanceSnapshotRecord] = []

    def register_delisting_metadata(
        self,
        ticker: str,
        reason: str,
        final_price: Optional[float] = None
    ) -> None:
        """Register or override delisting metadata for a specific ticker."""
        meta = {"reason": reason.lower()}
        if final_price is not None:
            meta["final_price"] = float(final_price)
        self.delisting_metadata[ticker.upper()] = meta

    def _init_delisting_cache(self, raw_prices_df: pd.DataFrame) -> None:
        if self._ticker_last_valid_dates is not None:
            return
        cache: Dict[str, pd.Timestamp] = {}
        for col in raw_prices_df.columns:
            valid_series = raw_prices_df[col].dropna()
            if not valid_series.empty:
                cache[col] = valid_series.index[-1]
        self._ticker_last_valid_dates = cache

    def is_ticker_permanently_delisted(
        self,
        ticker: str,
        current_date: pd.Timestamp,
        raw_prices_df: Optional[pd.DataFrame] = None
    ) -> bool:
        """
        Check if a ticker has permanently stopped trading on or before current_date.
        Returns True if ticker has no valid raw price on current_date AND no valid raw prices
        on any date after current_date in raw_prices_df.
        """
        if raw_prices_df is None or ticker not in raw_prices_df.columns or current_date not in raw_prices_df.index:
            return False

        val = raw_prices_df.at[current_date, ticker]
        if not pd.isna(val) and float(val) > 0:
            return False

        self._init_delisting_cache(raw_prices_df)
        last_valid = self._ticker_last_valid_dates.get(ticker) if self._ticker_last_valid_dates else None
        if last_valid is None:
            return False

        return current_date > last_valid

    def process_delistings(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame,
        raw_prices_df: Optional[pd.DataFrame] = None
    ) -> List[Dict[str, Any]]:
        """
        Detects and realizes positions in securities that have permanently stopped trading.
        - Bankruptcy: Realized price = $0.00 (position written down to $0).
        - Acquisition / Delisted: Realized price = final available trading price or specified buyout price.
        - Temporary halt: Retained at last available price.
        """
        if raw_prices_df is None:
            raw_prices_df = prices_df

        active_tickers = list(set(self.long_positions.keys()) | set(self.short_positions.keys()))
        if not active_tickers or current_date not in raw_prices_df.index:
            return []

        import logging
        engine_logger = logging.getLogger("BacktestEngine")
        processed = []

        for ticker in active_tickers:
            if not self.is_ticker_permanently_delisted(ticker, current_date, raw_prices_df):
                continue

            # Last available trading price prior to current_date
            last_avail_price = _get_portfolio_last_price(raw_prices_df, ticker, current_date)

            meta = self.delisting_metadata.get(ticker.upper(), {})
            reason = meta.get("reason", "delisted").lower()

            if last_avail_price <= 0:
                reason = "bankruptcy"

            if reason == "bankruptcy":
                realized_price = 0.0
            elif "final_price" in meta:
                realized_price = float(meta["final_price"])
            else:
                realized_price = last_avail_price

            total_value = self.get_portfolio_value(current_date, prices_df)

            # Realize long position if held
            if ticker in self.long_positions:
                shares = self.long_positions.pop(ticker)
                proceeds = shares * realized_price
                self.cash += proceeds
                self.trade_logs.append(
                    TradeRecord(current_date, ticker, "SELL", realized_price, shares, total_value)
                )
                engine_logger.info(
                    f"[DELISTING] Realized LONG position in '{ticker}' on {current_date.strftime('%Y-%m-%d')}: "
                    f"Reason={reason.upper()}, Realized Price=${realized_price:.2f}, Shares={shares:.4f}, Proceeds=${proceeds:.2f}"
                )

            # Realize short position if held
            if ticker in self.short_positions:
                shares = self.short_positions.pop(ticker)
                cover_cost = shares * realized_price
                self.cash -= cover_cost
                self.trade_logs.append(
                    TradeRecord(current_date, ticker, "COVER", realized_price, shares, total_value)
                )
                engine_logger.info(
                    f"[DELISTING] Realized SHORT position in '{ticker}' on {current_date.strftime('%Y-%m-%d')}: "
                    f"Reason={reason.upper()}, Realized Price=${realized_price:.2f}, Shares={shares:.4f}, Cost=${cover_cost:.2f}"
                )

            self.positions.pop(ticker, None)

            record = {
                "date": current_date.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "reason": reason,
                "realized_price": realized_price,
                "last_avail_price": last_avail_price
            }
            self.delisted_records.append(record)
            processed.append(record)

        return processed

    def get_portfolio_value(self, current_date: pd.Timestamp, prices_df: pd.DataFrame) -> float:
        """
        Calculate total current portfolio value: Cash + Market Value of Longs - Market Value of Short Liabilities.
        Uses get_ticker_price for robust historical fallback if a single-day price is NaN.
        """
        long_value = 0.0
        short_value = 0.0

        for ticker, shares in self.long_positions.items():
            if shares > 0:
                p = self.get_ticker_price(ticker, current_date, prices_df)
                long_value += shares * p

        for ticker, shares in self.short_positions.items():
            if shares > 0:
                p = self.get_ticker_price(ticker, current_date, prices_df)
                short_value += shares * p

        return self.cash + long_value - short_value

    def get_ticker_price(
        self,
        ticker: str,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame
    ) -> float:
        """
        Get reliable price for a ticker on current_date, falling back to latest available historical price.
        """
        if current_date in prices_df.index and ticker in prices_df.columns:
            p = prices_df.at[current_date, ticker]
            if not np.isnan(p) and float(p) > 0:
                return float(p)
        return _get_portfolio_last_price(prices_df, ticker, current_date)

    def execute_rebalance(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame,
        target_weights: Dict[str, float],
        signal_date: Optional[pd.Timestamp] = None,
        raw_prices_df: Optional[pd.DataFrame] = None
    ) -> None:
        """
        Execute rebalance across both Long and Short legs:
        - Step 1: Compute set differences (to_sell = current - target, to_buy = target - current, to_rebalance = current ∩ target).
        - Step 2: Sell 100% of dropped long positions (to_sell) and cover 100% of dropped short positions (to_cover).
        - Step 3: Resize overweight continuing positions (to_rebalance) to target weight = total_value / N (liberates cash).
        - Step 4: Resize underweight continuing positions & open brand new entries (to_buy) to target weight = total_value / N.
        - Step 5: Clean up zero holdings & update position state.
        - Step 6: Hard assertions for Cash Reconciliation, Pre-buy Liquidation, and Exact Set Equality.
        """
        if current_date not in prices_df.index:
            return

        if signal_date is None:
            signal_date = current_date

        # If any target ticker is delisted/non-trading on current_date (execution date), backfill from strategy ranking
        invalid_targets = [
            t for t in target_weights
            if self.get_ticker_price(t, current_date, prices_df) <= 0 or self.is_ticker_permanently_delisted(t, current_date, raw_prices_df)
        ]
        if invalid_targets and hasattr(self.strategy, "calculate_momentum_returns"):
            mom_series = self.strategy.calculate_momentum_returns(signal_date, prices_df)
            if not mom_series.empty:
                df_mom = pd.DataFrame({'Momentum': mom_series}).dropna()
                df_mom['Ticker'] = df_mom.index
                df_sorted = df_mom.sort_values(by=['Momentum', 'Ticker'], ascending=[False, True])

                valid_longs = []
                for t in df_sorted['Ticker']:
                    if self.get_ticker_price(t, current_date, prices_df) > 0 and not self.is_ticker_permanently_delisted(t, current_date, raw_prices_df):
                        valid_longs.append(t)
                        if len(valid_longs) == getattr(self.strategy, "positions", 20):
                            break
                if valid_longs:
                    w = 1.0 / len(valid_longs)
                    target_weights = {t: w for t in valid_longs}

        total_value = self.get_portfolio_value(current_date, prices_df)
        if total_value <= 0:
            return

        cash_before = self.cash
        start_trade_count = len(self.trade_logs)
        prev_holdings_set = set(self.positions.keys())

        target_longs = {t: w for t, w in target_weights.items() if w > 0}
        target_shorts = {t: abs(w) for t, w in target_weights.items() if w < 0}

        current_long_set = set(self.long_positions.keys())
        target_long_set = set(target_longs.keys())
        to_sell_longs = current_long_set - target_long_set

        current_short_set = set(self.short_positions.keys())
        target_short_set = set(target_shorts.keys())
        to_cover_shorts = current_short_set - target_short_set

        # 1. PHASE 1: SELL 100% OF DROPPED LONGS (current_holdings - new_top_n)
        for ticker in list(to_sell_longs):
            current_shares = self.long_positions[ticker]
            if current_shares <= 0.0001:
                self.long_positions.pop(ticker, None)
                continue

            price = self.get_ticker_price(ticker, current_date, prices_df)
            if price <= 0:
                import logging
                logging.getLogger("BacktestEngine").error(
                    f"HARD WARNING/ERROR: Missing or invalid price ({price}) for '{ticker}' on {current_date.strftime('%Y-%m-%d')}. Cannot execute sell!"
                )
                continue

            sale_amount = current_shares * price
            self.cash += sale_amount
            self.long_positions[ticker] = 0.0
            self.trade_logs.append(
                TradeRecord(current_date, ticker, "SELL", price, current_shares, total_value)
            )

        # 2. PHASE 2: COVER 100% OF DROPPED SHORTS
        for ticker in list(to_cover_shorts):
            current_shares = self.short_positions[ticker]
            if current_shares <= 0.0001:
                self.short_positions.pop(ticker, None)
                continue

            price = self.get_ticker_price(ticker, current_date, prices_df)
            if price <= 0:
                import logging
                logging.getLogger("BacktestEngine").error(
                    f"HARD WARNING/ERROR: Missing or invalid price ({price}) for '{ticker}' on {current_date.strftime('%Y-%m-%d')}. Cannot execute cover!"
                )
                continue

            cover_cost = current_shares * price
            self.cash -= cover_cost
            self.short_positions[ticker] = 0.0
            self.trade_logs.append(
                TradeRecord(current_date, ticker, "COVER", price, current_shares, total_value)
            )

        # Clean up zero holdings after dropped sells
        self.long_positions = {t: s for t, s in self.long_positions.items() if s > 0.0001}
        self.short_positions = {t: s for t, s in self.short_positions.items() if s > 0.0001}

        # PRE-BUY LIQUIDATION ASSERTION: Assert every ticker in to_sell_longs/to_cover_shorts is fully liquidated
        still_held_longs = to_sell_longs & set(self.long_positions.keys())
        still_held_shorts = to_cover_shorts & set(self.short_positions.keys())
        assert not still_held_longs, (
            f"Pre-buy liquidation assertion failed on {current_date.strftime('%Y-%m-%d')}: "
            f"Tickers {still_held_longs} were scheduled to be sold but remain in long_positions!"
        )
        assert not still_held_shorts, (
            f"Pre-buy liquidation assertion failed on {current_date.strftime('%Y-%m-%d')}: "
            f"Tickers {still_held_shorts} were scheduled to be covered but remain in short_positions!"
        )

        # 3. PHASE 3: RESIZE OVERWEIGHT CONTINUING POSITIONS (SELL EXCESS FIRST TO GENERATE CASH)
        for ticker, weight in target_longs.items():
            if ticker in self.long_positions:
                current_shares = self.long_positions[ticker]
                price = self.get_ticker_price(ticker, current_date, prices_df)
                if price <= 0 or self.is_ticker_permanently_delisted(ticker, current_date, raw_prices_df):
                    import logging
                    logging.getLogger("BacktestEngine").error(
                        f"HARD WARNING/ERROR: Missing or delisted price for '{ticker}' on {current_date.strftime('%Y-%m-%d')}. Cannot resize long!"
                    )
                    continue
                target_dollars = total_value * weight
                target_shares = target_dollars / price

                if current_shares > target_shares + 0.0001:
                    shares_to_sell = current_shares - target_shares
                    sale_amount = shares_to_sell * price
                    self.cash += sale_amount
                    self.long_positions[ticker] = target_shares
                    self.trade_logs.append(
                        TradeRecord(current_date, ticker, "SELL", price, shares_to_sell, total_value)
                    )

        for ticker, weight in target_shorts.items():
            if ticker in self.short_positions:
                current_shares = self.short_positions[ticker]
                price = self.get_ticker_price(ticker, current_date, prices_df)
                if price <= 0 or self.is_ticker_permanently_delisted(ticker, current_date, raw_prices_df):
                    import logging
                    logging.getLogger("BacktestEngine").error(
                        f"HARD WARNING/ERROR: Missing or delisted price for '{ticker}' on {current_date.strftime('%Y-%m-%d')}. Cannot resize short!"
                    )
                    continue
                target_dollars = total_value * weight
                target_shares = target_dollars / price

                if current_shares > target_shares + 0.0001:
                    shares_to_cover = current_shares - target_shares
                    cover_cost = shares_to_cover * price
                    self.cash -= cover_cost
                    self.short_positions[ticker] = target_shares
                    self.trade_logs.append(
                        TradeRecord(current_date, ticker, "COVER", price, shares_to_cover, total_value)
                    )

        # Clean up zero positions before opening new positions
        self.long_positions = {t: s for t, s in self.long_positions.items() if s > 0.0001}
        self.short_positions = {t: s for t, s in self.short_positions.items() if s > 0.0001}

        # 4. PHASE 4: OPEN BRAND NEW ENTRIES & RESIZE UNDERWEIGHT CONTINUING POSITIONS
        for ticker, weight in target_shorts.items():
            price = self.get_ticker_price(ticker, current_date, prices_df)
            if price <= 0 or self.is_ticker_permanently_delisted(ticker, current_date, raw_prices_df):
                import logging
                logging.getLogger("BacktestEngine").warning(
                    f"Skipping short position for delisted or non-trading ticker '{ticker}' on {current_date.strftime('%Y-%m-%d')}."
                )
                continue
            target_dollars = total_value * weight
            target_shares = target_dollars / price
            current_shares = self.short_positions.get(ticker, 0.0)

            if target_shares > current_shares + 0.0001:
                shares_to_short = target_shares - current_shares
                proceeds = shares_to_short * price
                self.cash += proceeds
                self.short_positions[ticker] = current_shares + shares_to_short
                self.trade_logs.append(
                    TradeRecord(current_date, ticker, "SHORT", price, shares_to_short, total_value)
                )

        for ticker, weight in target_longs.items():
            price = self.get_ticker_price(ticker, current_date, prices_df)
            if price <= 0 or self.is_ticker_permanently_delisted(ticker, current_date, raw_prices_df):
                import logging
                logging.getLogger("BacktestEngine").warning(
                    f"Skipping buy position for delisted or non-trading ticker '{ticker}' on {current_date.strftime('%Y-%m-%d')}."
                )
                continue
            target_dollars = total_value * weight
            target_shares = target_dollars / price
            current_shares = self.long_positions.get(ticker, 0.0)

            if target_shares > current_shares + 0.0001:
                shares_to_buy = target_shares - current_shares
                cost = shares_to_buy * price

                # Handle floating point precision rounding near exact cash balance
                if cost > self.cash:
                    if cost <= self.cash + 1e-4:
                        cost = self.cash
                        shares_to_buy = target_shares - current_shares
                    else:
                        shares_to_buy = max(0.0, self.cash / price)
                        cost = min(shares_to_buy * price, self.cash)

                if shares_to_buy > 0.0001:
                    cost = min(cost, self.cash)
                    self.cash = max(0.0, self.cash - cost)
                    self.long_positions[ticker] = current_shares + shares_to_buy
                    self.trade_logs.append(
                        TradeRecord(current_date, ticker, "BUY", price, shares_to_buy, total_value)
                    )

        # 5. PHASE 5: FINAL CLEANUP & POSITIONS UPDATE
        self.long_positions = {t: s for t, s in self.long_positions.items() if s > 0.0001}
        self.short_positions = {t: s for t, s in self.short_positions.items() if s > 0.0001}

        self.positions = {}
        for t, s in self.long_positions.items():
            self.positions[t] = s
        for t, s in self.short_positions.items():
            self.positions[t] = -s

        # 6. PHASE 6: HARD RECONCILIATION & POSITION EXACT SET EQUALITY ASSERTIONS
        cash_after = self.cash
        net_cash_change = cash_after - cash_before
        new_trades = self.trade_logs[start_trade_count:]

        total_sell_dollars = sum(t.shares * t.price for t in new_trades if t.action == "SELL")
        total_short_dollars = sum(t.shares * t.price for t in new_trades if t.action == "SHORT")
        total_buy_dollars = sum(t.shares * t.price for t in new_trades if t.action == "BUY")
        total_cover_dollars = sum(t.shares * t.price for t in new_trades if t.action == "COVER")

        trade_cash_delta = (total_sell_dollars + total_short_dollars) - (total_buy_dollars + total_cover_dollars)

        # Cash reconciliation assertion: net cash change must match logged trade dollar flow
        reconcile_diff = abs(net_cash_change - trade_cash_delta)
        assert reconcile_diff < 1.0, (
            f"Cash reconciliation assertion failed on {current_date.strftime('%Y-%m-%d')}: "
            f"net_cash_change=${net_cash_change:.2f}, trade_cash_delta=${trade_cash_delta:.2f}, "
            f"diff=${reconcile_diff:.2f}"
        )

        valid_target_longs = {
            t for t in target_longs 
            if self.get_ticker_price(t, current_date, prices_df) > 0 and not self.is_ticker_permanently_delisted(t, current_date, raw_prices_df)
        }
        valid_target_shorts = {
            t for t in target_shorts 
            if self.get_ticker_price(t, current_date, prices_df) > 0 and not self.is_ticker_permanently_delisted(t, current_date, raw_prices_df)
        }

        actual_longs = set(self.long_positions.keys())
        actual_shorts = set(self.short_positions.keys())

        # Exact set equality assertions for post-rebalance positions
        assert actual_longs == valid_target_longs, (
            f"Post-rebalance long set equality assertion failed on {current_date.strftime('%Y-%m-%d')}: "
            f"actual={sorted(actual_longs)}, expected={sorted(valid_target_longs)}, "
            f"missing={sorted(valid_target_longs - actual_longs)}, extra={sorted(actual_longs - valid_target_longs)}"
        )
        assert actual_shorts == valid_target_shorts, (
            f"Post-rebalance short set equality assertion failed on {current_date.strftime('%Y-%m-%d')}: "
            f"actual={sorted(actual_shorts)}, expected={sorted(valid_target_shorts)}, "
            f"missing={sorted(valid_target_shorts - actual_shorts)}, extra={sorted(actual_shorts - valid_target_shorts)}"
        )
        assert set(self.positions.keys()) == (valid_target_longs | valid_target_shorts), (
            f"Post-rebalance exact set equality assertion failed on {current_date.strftime('%Y-%m-%d')}!"
        )

        # Build rebalance snapshot record immediately following rebalance
        exited_tickers = sorted(list((to_sell_longs | to_cover_shorts)))
        holdings_details = []
        for ticker in sorted(self.positions.keys()):
            signed_shares = self.positions[ticker]
            shares = abs(signed_shares)
            price = self.get_ticker_price(ticker, current_date, prices_df)
            val = shares * price
            weight = (val / total_value * 100.0) if total_value > 0 else 0.0
            is_new = ticker not in prev_holdings_set
            holdings_details.append({
                "ticker": ticker,
                "action": "NEW" if is_new else "RETAINED",
                "shares": round(shares, 6),
                "price": round(price, 2),
                "value": round(val, 2),
                "weight": round(weight, 2)
            })

        snapshot = RebalanceSnapshotRecord(
            date=current_date,
            signal_date=signal_date,
            portfolio_value=total_value,
            cash=self.cash,
            holdings=holdings_details,
            exited_tickers=exited_tickers
        )
        self.rebalance_snapshots.append(snapshot)

    def run(
        self,
        prices_df: pd.DataFrame,
        start_date: str,
        end_date: str,
        open_prices_df: Optional[pd.DataFrame] = None,
        raw_prices_df: Optional[pd.DataFrame] = None,
        volumes_df: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Run backtest over price history DataFrame.

        Signals are generated on rebalance dates using closing prices up to the rebalance date.
        Trades are executed on the NEXT trading day using the opening price (eliminating look-ahead bias).

        Returns:
            DataFrame containing daily portfolio value and cash balance.
        """
        if open_prices_df is None:
            open_prices_df = prices_df

        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)

        # Filter price history within backtest date range for execution days
        available_dates = prices_df.index[prices_df.index <= end_ts]
        bt_trading_days = available_dates[available_dates >= start_ts]

        if bt_trading_days.empty:
            raise ValueError("No price data available within specified date range!")

        start_exec_date = bt_trading_days[0]

        # Determine rebalance signal dates for all available trading days up to end_ts
        all_rebalance_signal_dates = get_rebalance_dates(prices_df.loc[prices_df.index <= end_ts], self.rebalance_frequency)

        # Map execution date (NEXT trading day) to (signal_date, target_weights)
        pending_rebalances: Dict[pd.Timestamp, Tuple[pd.Timestamp, Dict[str, float]]] = {}

        # 1. Initial rebalance for cold-start on start_exec_date:
        # To enter initial positions at market Open on start_exec_date, the signal MUST be computed using trailing prices up to the prior trading day.
        prior_days = available_dates[available_dates < start_exec_date]
        if not prior_days.empty:
            first_signal_date = prior_days[-1]
            first_target_weights = self.strategy.generate_target_weights(
                first_signal_date, prices_df, raw_prices_df=raw_prices_df, volumes_df=volumes_df
            )
            pending_rebalances[start_exec_date] = (first_signal_date, first_target_weights)
        else:
            raise ValueError(
                f"Insufficient historical price data prior to backtest start date {start_date}! "
                f"At least trailing historical data prior to {start_exec_date.strftime('%Y-%m-%d')} is required to compute point-in-time momentum signals."
            )

        # 2. Schedule subsequent rebalances within the backtest date range:
        for signal_date in all_rebalance_signal_dates:
            if signal_date >= start_exec_date:
                future_dates = available_dates[available_dates > signal_date]
                if not future_dates.empty:
                    exec_date = future_dates[0]
                    if exec_date <= end_ts and exec_date not in pending_rebalances:
                        target_weights = self.strategy.generate_target_weights(
                            signal_date, prices_df, raw_prices_df=raw_prices_df, volumes_df=volumes_df
                        )
                        pending_rebalances[exec_date] = (signal_date, target_weights)

        # Reset state
        self.cash = self.initial_capital
        self.long_positions = {}
        self.short_positions = {}
        self.positions = {}
        self.trade_logs = []
        self.portfolio_logs = []
        self.rebalance_snapshots = []
        self.delisted_records = []

        # Reset stop loss tracking state
        self.running_peak_value = self.initial_capital
        self.in_stop_loss = False
        self.stop_loss_trigger_date = None
        self.stop_loss_trough_value = self.initial_capital
        self.stop_loss_trigger_peak = self.initial_capital
        self.stop_loss_rebalance_count_in_cash = 0
        self.stop_loss_trigger_count = 0
        self.whipsaw_count = 0

        import logging
        logger = logging.getLogger("BacktestEngine")

        # Day-by-day simulation loop
        for date in bt_trading_days:
            # Process any permanent trading stops / delistings as of today
            self.process_delistings(date, prices_df, raw_prices_df)

            curr_val = self.get_portfolio_value(date, prices_df)
            if curr_val > self.running_peak_value:
                self.running_peak_value = curr_val

            # Process stop-loss logic on rebalance execution dates
            if date in pending_rebalances and self.stop_loss_pct is not None:
                dd_from_peak = (self.running_peak_value - curr_val) / self.running_peak_value if self.running_peak_value > 0 else 0.0

                if not self.in_stop_loss:
                    if dd_from_peak >= self.stop_loss_pct:
                        self.in_stop_loss = True
                        self.stop_loss_trigger_date = date
                        self.stop_loss_trough_value = curr_val
                        self.stop_loss_trigger_peak = self.running_peak_value
                        self.stop_loss_rebalance_count_in_cash = 0
                        self.stop_loss_trigger_count += 1
                        logger.info(
                            f"[Stop Loss Audit] Triggered on {date.strftime('%Y-%m-%d')}: "
                            f"Drawdown {dd_from_peak*100:.2f}% >= Threshold {self.stop_loss_pct*100:.2f}%. "
                            f"Peak=${self.running_peak_value:,.2f}, Current Value=${curr_val:,.2f}"
                        )
                else:
                    self.stop_loss_rebalance_count_in_cash += 1
                    if curr_val < self.stop_loss_trough_value:
                        self.stop_loss_trough_value = curr_val

                    reentry_thresh_pct = self.stop_loss_reentry_pct if self.stop_loss_reentry_pct is not None else self.stop_loss_pct
                    should_reenter = False

                    if self.stop_loss_reentry_mode == "recovery":
                        rec_peak = self.stop_loss_trigger_peak * (1.0 - reentry_thresh_pct)
                        rec_trough = self.stop_loss_trough_value * (1.0 + reentry_thresh_pct)
                        if curr_val >= rec_peak or curr_val >= rec_trough:
                            should_reenter = True
                    elif self.stop_loss_reentry_mode == "months":
                        if self.stop_loss_rebalance_count_in_cash >= self.stop_loss_reentry_months:
                            should_reenter = True

                    if should_reenter:
                        is_whipsaw = (self.stop_loss_rebalance_count_in_cash <= 1) or (curr_val <= self.stop_loss_trough_value * 1.03)
                        if is_whipsaw:
                            self.whipsaw_count += 1

                        logger.info(
                            f"[Stop Loss Audit] Re-entered on {date.strftime('%Y-%m-%d')} (Mode={self.stop_loss_reentry_mode}): "
                            f"Value=${curr_val:,.2f}, Peak=${self.stop_loss_trigger_peak:,.2f}, Trough=${self.stop_loss_trough_value:,.2f}, "
                            f"Rebalances in Cash={self.stop_loss_rebalance_count_in_cash}, Whipsaw={is_whipsaw}"
                        )
                        self.in_stop_loss = False
                        self.stop_loss_rebalance_count_in_cash = 0

            # Execute pending trades on NEXT trading day at Open
            rebal_exec_val = None
            if date in pending_rebalances:
                sig_date, target_weights = pending_rebalances[date]
                if self.in_stop_loss:
                    stop_scale = max(0.0, 1.0 - self.stop_loss_cash_pct)
                    target_weights = {t: w * stop_scale for t, w in target_weights.items()}

                self.execute_rebalance(date, open_prices_df, target_weights, signal_date=sig_date, raw_prices_df=raw_prices_df)
                if self.rebalance_snapshots:
                    rebal_exec_val = self.rebalance_snapshots[-1].portfolio_value

            # Record daily snapshot. On rebalance execution dates, use the exact rebalance portfolio value for trade log consistency.
            if rebal_exec_val is not None:
                total_val = rebal_exec_val
            else:
                total_val = self.get_portfolio_value(date, prices_df)

            self.portfolio_logs.append(PortfolioHistoryRecord(date, total_val, self.cash))

        # Build daily history DataFrame
        history_df = pd.DataFrame([p.to_dict() for p in self.portfolio_logs])
        history_df["Date"] = pd.to_datetime(history_df["Date"])
        history_df = history_df.set_index("Date").sort_index()

        return history_df
