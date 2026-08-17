"""
Configuration module for the Stock Momentum Backtester.

Provides default configuration settings and helper methods to override configuration
dynamically from CLI parameters, environment variables, or API payloads.
"""

import os
from typing import Optional, Dict, Any

# Strategy and Backtest Default Settings
START_DATE: str = os.getenv("START_DATE", "2020-01-01")
END_DATE: str = os.getenv("END_DATE", "2026-08-04")
INITIAL_CAPITAL: float = float(os.getenv("INITIAL_CAPITAL", "30000"))
POSITIONS: int = int(os.getenv("POSITIONS", "20"))
LOOKBACK_MONTHS: int = int(os.getenv("LOOKBACK_MONTHS", "12"))
SKIP_LAST_MONTH: bool = os.getenv("SKIP_LAST_MONTH", "True").lower() in ("true", "1", "t", "yes")
INCLUDE_SHORTS: bool = os.getenv("INCLUDE_SHORTS", "False").lower() in ("true", "1", "t", "yes")
REBALANCE_FREQUENCY: str = os.getenv("REBALANCE_FREQUENCY", "monthly")
UNIVERSE_FILE: str = os.getenv("UNIVERSE_FILE", "sp500.csv")
BENCHMARK_TICKER: str = os.getenv("BENCHMARK_TICKER", "SPY")

VERIFY_DATE: Optional[str] = os.getenv("VERIFY_DATE", None)

# Risk Management Parameters
MAX_POSITIONS_PER_SECTOR: int = int(os.getenv("MAX_POSITIONS_PER_SECTOR", "0"))
MIN_AVG_DOLLAR_VOLUME: float = float(os.getenv("MIN_AVG_DOLLAR_VOLUME", "0.0"))
MIN_MARKET_CAP: float = float(os.getenv("MIN_MARKET_CAP", "0.0"))
RANKING_METHOD: str = os.getenv("RANKING_METHOD", "raw_return")
REGIME_FILTER: bool = os.getenv("REGIME_FILTER", "False").lower() in ("true", "1", "t", "yes")
REGIME_REDUCED_EXPOSURE_PCT: float = float(os.getenv("REGIME_REDUCED_EXPOSURE_PCT", "0.5"))
EARNINGS_BLACKOUT_DAYS: int = int(os.getenv("EARNINGS_BLACKOUT_DAYS", "0"))

# Trend-Reversal Protection Parameters (Momentum Factor Crash Protections)
MOMENTUM_REGIME_FILTER: bool = os.getenv("MOMENTUM_REGIME_FILTER", "False").lower() in ("true", "1", "t", "yes")
MOMENTUM_REGIME_LOOKBACK_DAYS: int = int(os.getenv("MOMENTUM_REGIME_LOOKBACK_DAYS", "20"))
MOMENTUM_REGIME_THRESHOLD: float = float(os.getenv("MOMENTUM_REGIME_THRESHOLD", "0.0"))

VOL_SCALING: bool = os.getenv("VOL_SCALING", "False").lower() in ("true", "1", "t", "yes")
VOL_SCALING_LOOKBACK_DAYS: int = int(os.getenv("VOL_SCALING_LOOKBACK_DAYS", "20"))
TARGET_VOLATILITY: float = float(os.getenv("TARGET_VOLATILITY", "0.25"))

STOP_LOSS_PCT: Optional[float] = float(os.getenv("STOP_LOSS_PCT")) if os.getenv("STOP_LOSS_PCT") else None
STOP_LOSS_CASH_PCT: float = float(os.getenv("STOP_LOSS_CASH_PCT", "1.0"))
STOP_LOSS_REENTRY_MODE: str = os.getenv("STOP_LOSS_REENTRY_MODE", "recovery")  # 'recovery' | 'months'
STOP_LOSS_REENTRY_PCT: Optional[float] = float(os.getenv("STOP_LOSS_REENTRY_PCT")) if os.getenv("STOP_LOSS_REENTRY_PCT") else None
STOP_LOSS_REENTRY_MONTHS: int = int(os.getenv("STOP_LOSS_REENTRY_MONTHS", "1"))

# Multi-Factor Strategy Parameters
STRATEGY_MODE: str = os.getenv("STRATEGY_MODE", "momentum_only")  # 'momentum_only' | 'multi_factor_composite'
FACTOR_WEIGHTS: Dict[str, float] = {
    "momentum": float(os.getenv("WEIGHT_MOMENTUM", "0.3333333333333333")),
    "quality": float(os.getenv("WEIGHT_QUALITY", "0.3333333333333333")),
    "low_vol": float(os.getenv("WEIGHT_LOW_VOL", "0.3333333333333333"))
}

# File paths
BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR: str = os.path.join(BASE_DIR, "cache")
OUTPUT_DIR: str = BASE_DIR

# Ensure cache and output directories exist
os.makedirs(CACHE_DIR, exist_ok=True)


class Config:
    """Config container class allowing dynamic override of backtest parameters."""
    def __init__(
        self,
        start_date: str = START_DATE,
        end_date: str = END_DATE,
        initial_capital: float = INITIAL_CAPITAL,
        positions: int = POSITIONS,
        lookback_months: int = LOOKBACK_MONTHS,
        skip_last_month: bool = SKIP_LAST_MONTH,
        include_shorts: bool = INCLUDE_SHORTS,
        rebalance_frequency: str = REBALANCE_FREQUENCY,
        universe_file: str = UNIVERSE_FILE,
        benchmark_ticker: str = BENCHMARK_TICKER,
        verify_date: Optional[str] = VERIFY_DATE,
        max_positions_per_sector: int = MAX_POSITIONS_PER_SECTOR,
        min_avg_dollar_volume: float = MIN_AVG_DOLLAR_VOLUME,
        min_market_cap: float = MIN_MARKET_CAP,
        ranking_method: str = RANKING_METHOD,
        regime_filter: bool = REGIME_FILTER,
        regime_reduced_exposure_pct: float = REGIME_REDUCED_EXPOSURE_PCT,
        earnings_blackout_days: int = EARNINGS_BLACKOUT_DAYS,
        momentum_regime_filter: bool = MOMENTUM_REGIME_FILTER,
        momentum_regime_lookback_days: int = MOMENTUM_REGIME_LOOKBACK_DAYS,
        momentum_regime_threshold: float = MOMENTUM_REGIME_THRESHOLD,
        vol_scaling: bool = VOL_SCALING,
        vol_scaling_lookback_days: int = VOL_SCALING_LOOKBACK_DAYS,
        target_volatility: float = TARGET_VOLATILITY,
        stop_loss_pct: Optional[float] = STOP_LOSS_PCT,
        stop_loss_cash_pct: float = STOP_LOSS_CASH_PCT,
        stop_loss_reentry_mode: str = STOP_LOSS_REENTRY_MODE,
        stop_loss_reentry_pct: Optional[float] = STOP_LOSS_REENTRY_PCT,
        stop_loss_reentry_months: int = STOP_LOSS_REENTRY_MONTHS,
        strategy_mode: str = STRATEGY_MODE,
        factor_weights: Optional[Dict[str, float]] = None,
        cache_dir: str = CACHE_DIR,
        output_dir: str = OUTPUT_DIR
    ):
        self.start_date: str = start_date
        self.end_date: str = end_date
        self.initial_capital: float = initial_capital
        self.positions: int = positions
        self.lookback_months: int = lookback_months
        self.skip_last_month: bool = skip_last_month
        self.include_shorts: bool = include_shorts
        self.rebalance_frequency: str = rebalance_frequency
        self.universe_file: str = universe_file
        self.benchmark_ticker: str = benchmark_ticker
        self.verify_date: Optional[str] = verify_date
        self.max_positions_per_sector: int = max_positions_per_sector
        self.min_avg_dollar_volume: float = min_avg_dollar_volume
        self.min_market_cap: float = min_market_cap
        self.ranking_method: str = ranking_method
        self.regime_filter: bool = regime_filter
        self.regime_reduced_exposure_pct: float = regime_reduced_exposure_pct
        self.earnings_blackout_days: int = earnings_blackout_days
        self.momentum_regime_filter: bool = momentum_regime_filter
        self.momentum_regime_lookback_days: int = momentum_regime_lookback_days
        self.momentum_regime_threshold: float = momentum_regime_threshold
        self.vol_scaling: bool = vol_scaling
        self.vol_scaling_lookback_days: int = vol_scaling_lookback_days
        self.target_volatility: float = target_volatility
        self.stop_loss_pct: Optional[float] = stop_loss_pct
        self.stop_loss_cash_pct: float = stop_loss_cash_pct
        self.stop_loss_reentry_mode: str = stop_loss_reentry_mode
        self.stop_loss_reentry_pct: Optional[float] = stop_loss_reentry_pct if stop_loss_reentry_pct is not None else stop_loss_pct
        self.stop_loss_reentry_months: int = stop_loss_reentry_months
        self.strategy_mode: str = strategy_mode
        self.factor_weights: Dict[str, float] = factor_weights if factor_weights is not None else FACTOR_WEIGHTS.copy()
        self.cache_dir: str = cache_dir
        self.output_dir: str = output_dir

    def to_dict(self) -> Dict[str, Any]:
        """Return configuration as a dictionary."""
        return {
            "START_DATE": self.start_date,
            "END_DATE": self.end_date,
            "INITIAL_CAPITAL": self.initial_capital,
            "POSITIONS": self.positions,
            "LOOKBACK_MONTHS": self.lookback_months,
            "SKIP_LAST_MONTH": self.skip_last_month,
            "INCLUDE_SHORTS": self.include_shorts,
            "REBALANCE_FREQUENCY": self.rebalance_frequency,
            "UNIVERSE_FILE": self.universe_file,
            "BENCHMARK_TICKER": self.benchmark_ticker,
            "VERIFY_DATE": self.verify_date,
            "MAX_POSITIONS_PER_SECTOR": self.max_positions_per_sector,
            "MIN_AVG_DOLLAR_VOLUME": self.min_avg_dollar_volume,
            "MIN_MARKET_CAP": self.min_market_cap,
            "RANKING_METHOD": self.ranking_method,
            "REGIME_FILTER": self.regime_filter,
            "REGIME_REDUCED_EXPOSURE_PCT": self.regime_reduced_exposure_pct,
            "EARNINGS_BLACKOUT_DAYS": self.earnings_blackout_days,
            "MOMENTUM_REGIME_FILTER": self.momentum_regime_filter,
            "MOMENTUM_REGIME_LOOKBACK_DAYS": self.momentum_regime_lookback_days,
            "MOMENTUM_REGIME_THRESHOLD": self.momentum_regime_threshold,
            "VOL_SCALING": self.vol_scaling,
            "VOL_SCALING_LOOKBACK_DAYS": self.vol_scaling_lookback_days,
            "TARGET_VOLATILITY": self.target_volatility,
            "STOP_LOSS_PCT": self.stop_loss_pct,
            "STOP_LOSS_CASH_PCT": self.stop_loss_cash_pct,
            "STOP_LOSS_REENTRY_MODE": self.stop_loss_reentry_mode,
            "STOP_LOSS_REENTRY_PCT": self.stop_loss_reentry_pct,
            "STOP_LOSS_REENTRY_MONTHS": self.stop_loss_reentry_months,
            "STRATEGY_MODE": self.strategy_mode,
            "FACTOR_WEIGHTS": self.factor_weights,
        }
