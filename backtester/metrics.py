"""
Performance metrics calculation module for backtest results.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional


def calculate_cagr(start_val: float, end_val: float, days: int) -> float:
    """Calculate Compound Annual Growth Rate (CAGR)."""
    if start_val <= 0 or days <= 0:
        return 0.0
    years = days / 365.25
    if years <= 0:
        return 0.0
    return ((end_val / start_val) ** (1.0 / years)) - 1.0


def calculate_drawdowns(equity_series: pd.Series) -> Tuple[pd.Series, float]:
    """
    Calculate daily drawdown series and maximum drawdown percentage.
    
    Returns:
        Tuple of (drawdown_series, max_drawdown_pct)
    """
    if equity_series.empty:
        return pd.Series(dtype=float), 0.0
    
    cum_max = equity_series.cummax()
    drawdown = (equity_series - cum_max) / cum_max
    max_dd = float(drawdown.min())  # Negative value e.g. -0.25 for -25%
    return drawdown, abs(max_dd)


def calculate_volatility(daily_returns: pd.Series, periods_per_year: int = 252) -> float:
    """Calculate annualized volatility from daily returns."""
    if daily_returns.empty or len(daily_returns) < 2:
        return 0.0
    return float(daily_returns.std() * np.sqrt(periods_per_year))


def calculate_sharpe_ratio(
    daily_returns: pd.Series,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252
) -> float:
    """Calculate annualized Sharpe Ratio."""
    if daily_returns.empty or len(daily_returns) < 2:
        return 0.0
    
    mean_ret = daily_returns.mean() * periods_per_year
    ann_vol = calculate_volatility(daily_returns, periods_per_year)
    
    if ann_vol == 0:
        return 0.0
        
    return (mean_ret - risk_free_rate) / ann_vol


def calculate_avg_holding_period(trade_logs: List[Any]) -> float:
    """
    Calculate average holding period in days across completed long (BUY -> SELL) and short (SHORT -> COVER) cycles per ticker.
    """
    if not trade_logs:
        return 0.0

    ticker_buys: Dict[str, List[pd.Timestamp]] = {}
    ticker_shorts: Dict[str, List[pd.Timestamp]] = {}
    holding_periods: List[float] = []

    for trade in trade_logs:
        t_dict = trade.to_dict() if hasattr(trade, "to_dict") else trade
        ticker = t_dict["Ticker"]
        action = t_dict["Action"]
        date_str = t_dict["Date"]
        date = pd.Timestamp(date_str)

        if action == "BUY":
            ticker_buys.setdefault(ticker, []).append(date)
        elif action == "SELL":
            if ticker in ticker_buys and ticker_buys[ticker]:
                buy_date = ticker_buys[ticker].pop(0)
                diff_days = (date - buy_date).days
                if diff_days >= 0:
                    holding_periods.append(float(diff_days))
        elif action == "SHORT":
            ticker_shorts.setdefault(ticker, []).append(date)
        elif action == "COVER":
            if ticker in ticker_shorts and ticker_shorts[ticker]:
                short_date = ticker_shorts[ticker].pop(0)
                diff_days = (date - short_date).days
                if diff_days >= 0:
                    holding_periods.append(float(diff_days))

    if not holding_periods:
        return 30.0  # Default estimate for monthly rebalance if no full roundtrip recorded

    return float(np.mean(holding_periods))


def compute_performance_summary(
    portfolio_history: pd.DataFrame,
    trade_logs: List[Any],
    benchmark_history: Optional[pd.DataFrame] = None,
    risk_free_rate: float = 0.02
) -> Dict[str, Any]:
    """
    Compute comprehensive metrics summary for portfolio and benchmark.
    """
    equity = portfolio_history["Portfolio Value"].copy()
    daily_returns = equity.pct_change().dropna()

    start_val = float(equity.iloc[0]) if not equity.empty else 0.0
    end_val = float(equity.iloc[-1]) if not equity.empty else 0.0
    total_return = ((end_val / start_val) - 1.0) if start_val > 0 else 0.0

    days = (equity.index[-1] - equity.index[0]).days if len(equity.index) > 1 else 1
    cagr = calculate_cagr(start_val, end_val, days)

    drawdown_series, max_dd = calculate_drawdowns(equity)
    volatility = calculate_volatility(daily_returns)
    sharpe = calculate_sharpe_ratio(daily_returns, risk_free_rate)
    calmar = (cagr / max_dd) if max_dd > 1e-6 else 0.0

    num_trades = len(trade_logs)
    avg_holding_days = calculate_avg_holding_period(trade_logs)

    metrics = {
        "Starting Capital": start_val,
        "Ending Capital": end_val,
        "Total Return": total_return,
        "Annualized Return (CAGR)": cagr,
        "Maximum Drawdown": max_dd,
        "Volatility": volatility,
        "Sharpe Ratio": sharpe,
        "Calmar Ratio": calmar,
        "Number of Trades": num_trades,
        "Average Holding Period (Days)": avg_holding_days,
    }

    # Benchmark metrics if benchmark_history is provided
    if benchmark_history is not None and not benchmark_history.empty:
        bm_equity = benchmark_history["Portfolio Value"]
        bm_returns = bm_equity.pct_change().dropna()

        bm_start = float(bm_equity.iloc[0])
        bm_end = float(bm_equity.iloc[-1])
        bm_total_ret = ((bm_end / bm_start) - 1.0) if bm_start > 0 else 0.0
        bm_days = (bm_equity.index[-1] - bm_equity.index[0]).days if len(bm_equity.index) > 1 else 1
        bm_cagr = calculate_cagr(bm_start, bm_end, bm_days)
        _, bm_max_dd = calculate_drawdowns(bm_equity)
        bm_vol = calculate_volatility(bm_returns)
        bm_sharpe = calculate_sharpe_ratio(bm_returns, risk_free_rate)

        metrics["Benchmark Ticker"] = "SPY"
        metrics["Benchmark Total Return"] = bm_total_ret
        metrics["Benchmark CAGR"] = bm_cagr
        metrics["Benchmark Max Drawdown"] = bm_max_dd
        metrics["Benchmark Volatility"] = bm_vol
        metrics["Benchmark Sharpe Ratio"] = bm_sharpe
        metrics["Alpha vs Benchmark"] = cagr - bm_cagr

    return metrics
