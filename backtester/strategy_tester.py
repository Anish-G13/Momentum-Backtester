"""
Strategy Tester Runner script.
Automates running backtests across various parameter combinations for robustness testing.
"""

import sys
import os
import json
import pandas as pd
import numpy as np

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtester.config import Config
from backtester.data import DataFetcher
from backtester.utils import load_universe
from backtester.strategy import CrossSectionalMomentumStrategy
from backtester.portfolio import BacktestEngine
from backtester.metrics import compute_performance_summary


def format_pct(val: float) -> str:
    if val is None:
        return "N/A"
    return f"{val * 100:.2f}%"


def format_usd(val: float) -> str:
    if val is None:
        return "N/A"
    return f"${val:,.2f}"


def run_single_test(
    prices_df: pd.DataFrame,
    open_prices_df: pd.DataFrame,
    raw_prices_df: pd.DataFrame,
    spy_df: pd.DataFrame,
    start_date: str = "2020-01-01",
    end_date: str = "2026-08-04",
    initial_capital: float = 30000.0,
    positions: int = 10,
    lookback_months: int = 12,
    skip_last_month: bool = True,
    rebalance_freq: str = "monthly",
    include_shorts: bool = False
) -> dict:
    strategy = CrossSectionalMomentumStrategy(
        positions=positions,
        lookback_months=lookback_months,
        skip_last_month=skip_last_month,
        include_shorts=include_shorts
    )
    engine = BacktestEngine(
        initial_capital=initial_capital,
        strategy=strategy,
        rebalance_frequency=rebalance_freq
    )
    portfolio_history = engine.run(
        prices_df,
        start_date,
        end_date,
        open_prices_df=open_prices_df,
        raw_prices_df=raw_prices_df
    )

    benchmark_history = None
    if spy_df is not None and not spy_df.empty:
        spy_sub = spy_df.iloc[:, 0].loc[(spy_df.index >= pd.Timestamp(start_date)) & (spy_df.index <= pd.Timestamp(end_date))]
        if not spy_sub.empty:
            spy_start_price = float(spy_sub.iloc[0])
            spy_shares = initial_capital / spy_start_price
            benchmark_history = pd.DataFrame({
                "Portfolio Value": spy_sub * spy_shares,
                "Cash": 0.0
            })

    metrics = compute_performance_summary(
        portfolio_history,
        engine.trade_logs,
        benchmark_history=benchmark_history
    )

    strat_ret = metrics.get("Total Return", 0.0)
    spy_ret = metrics.get("Benchmark Total Return", 0.0)
    beat_spy = "Yes" if strat_ret > spy_ret else "No"

    return {
        "start_date": start_date,
        "top_n": positions,
        "rebalance": rebalance_freq.capitalize(),
        "lookback": f"{lookback_months} Months",
        "skip_month": "Enabled" if skip_last_month else "Disabled",
        "final_value_raw": metrics.get("Ending Capital", 0.0),
        "final_value": format_usd(metrics.get("Ending Capital", 0.0)),
        "total_return_raw": strat_ret,
        "total_return": format_pct(strat_ret),
        "spy_return_raw": spy_ret,
        "spy_return": format_pct(spy_ret),
        "beat_spy": beat_spy,
        "sharpe_raw": metrics.get("Sharpe Ratio", 0.0),
        "sharpe": f"{metrics.get('Sharpe Ratio', 0.0):.2f}",
        "max_drawdown_raw": metrics.get("Maximum Drawdown", 0.0),
        "max_drawdown": format_pct(metrics.get("Maximum Drawdown", 0.0))
    }


def run_all_strategy_tests(end_date: str = "2026-08-04", initial_capital: float = 30000.0) -> dict:
    config = Config()
    fetcher = DataFetcher(cache_dir=config.cache_dir)
    tickers = load_universe(config.universe_file)

    # Fetch data starting 2018-01-01 with lookback buffer
    prices_df, open_prices_df, raw_prices_df = fetcher.fetch_universe_data(
        tickers=tickers,
        start_date="2018-01-01",
        end_date=end_date,
        buffer_months=24,
        return_raw=True
    )
    spy_prices, _, _ = fetcher.fetch_universe_data(
        tickers=["SPY"],
        start_date="2018-01-01",
        end_date=end_date,
        buffer_months=1,
        return_raw=True
    )
    spy_df = pd.DataFrame({"Portfolio Value": spy_prices["SPY"]})

    all_start_dates = [
        "2018-01-01", "2019-01-01", "2020-01-01", "2021-01-01",
        "2022-01-01", "2023-01-01", "2024-01-01", "2025-01-01"
    ]

    def_top_n = 10
    def_rebalance = "monthly"
    def_lookback = 12
    def_skip = True

    # Cache for runs: key = (start_date, positions, rebalance_freq, lookback_months, skip_last_month)
    run_cache = {}

    def get_run(sd, top_n, freq, lookback, skip):
        key = (sd, top_n, freq, lookback, skip)
        if key not in run_cache:
            run_cache[key] = run_single_test(
                prices_df, open_prices_df, raw_prices_df, spy_df,
                start_date=sd, end_date=end_date, initial_capital=initial_capital,
                positions=top_n, lookback_months=lookback,
                skip_last_month=skip, rebalance_freq=freq
            )
        return run_cache[key]

    # TEST 1: Baseline across Start Dates
    test1_results = []
    for sd in all_start_dates:
        res = get_run(sd, def_top_n, def_rebalance, def_lookback, def_skip)
        test1_results.append(res)

    # TEST 2: Top N Positions across ALL Start Dates
    top_n_options = [5, 10, 20, 30]
    test2_matrix = []
    top_n_wins = {f"Top {n}": 0 for n in top_n_options}

    for sd in all_start_dates:
        year_str = sd.split("-")[0]
        row_cols = {}
        best_ret = -999999.0
        best_opt = None
        for n in top_n_options:
            res = get_run(sd, n, def_rebalance, def_lookback, def_skip)
            opt_key = f"Top {n}"
            row_cols[opt_key] = res
            if res["total_return_raw"] > best_ret:
                best_ret = res["total_return_raw"]
                best_opt = opt_key
        if best_opt:
            top_n_wins[best_opt] += 1
        
        test2_matrix.append({
            "start_date": year_str,
            "full_start_date": sd,
            "options": row_cols,
            "winner": best_opt
        })

    # TEST 3: Rebalance Frequency across ALL Start Dates
    rebalance_options = ["weekly", "monthly", "quarterly"]
    test3_matrix = []
    rebalance_wins = {f.capitalize(): 0 for f in rebalance_options}

    for sd in all_start_dates:
        year_str = sd.split("-")[0]
        row_cols = {}
        best_ret = -999999.0
        best_opt = None
        for freq in rebalance_options:
            res = get_run(sd, def_top_n, freq, def_lookback, def_skip)
            opt_key = freq.capitalize()
            row_cols[opt_key] = res
            if res["total_return_raw"] > best_ret:
                best_ret = res["total_return_raw"]
                best_opt = opt_key
        if best_opt:
            rebalance_wins[best_opt] += 1
        
        test3_matrix.append({
            "start_date": year_str,
            "full_start_date": sd,
            "options": row_cols,
            "winner": best_opt
        })

    # TEST 4: Lookback Period across ALL Start Dates
    lookback_options = [6, 9, 12, 18]
    test4_matrix = []
    lookback_wins = {f"{lb} Months": 0 for lb in lookback_options}

    for sd in all_start_dates:
        year_str = sd.split("-")[0]
        row_cols = {}
        best_ret = -999999.0
        best_opt = None
        for lb in lookback_options:
            res = get_run(sd, def_top_n, def_rebalance, lb, def_skip)
            opt_key = f"{lb} Months"
            row_cols[opt_key] = res
            if res["total_return_raw"] > best_ret:
                best_ret = res["total_return_raw"]
                best_opt = opt_key
        if best_opt:
            lookback_wins[best_opt] += 1
        
        test4_matrix.append({
            "start_date": year_str,
            "full_start_date": sd,
            "options": row_cols,
            "winner": best_opt
        })

    # TEST 5: Skip Last Month across ALL Start Dates
    test5_matrix = []
    skip_wins = {"Enabled": 0, "Disabled": 0}

    for sd in all_start_dates:
        year_str = sd.split("-")[0]
        row_cols = {}
        best_ret = -999999.0
        best_opt = None
        for skip_val in [True, False]:
            label = "Enabled" if skip_val else "Disabled"
            res = get_run(sd, def_top_n, def_rebalance, def_lookback, skip_val)
            row_cols[label] = res
            if res["total_return_raw"] > best_ret:
                best_ret = res["total_return_raw"]
                best_opt = label
        if best_opt:
            skip_wins[best_opt] += 1
        
        test5_matrix.append({
            "start_date": year_str,
            "full_start_date": sd,
            "options": row_cols,
            "winner": best_opt
        })

    # Compute SPY beating consistency
    beat_spy_count = sum(1 for res in test1_results if res["beat_spy"] == "Yes")

    return {
        "test1_start_dates": test1_results,
        "test2_top_n_matrix": {
            "rows": test2_matrix,
            "wins": top_n_wins
        },
        "test3_rebalance_matrix": {
            "rows": test3_matrix,
            "wins": rebalance_wins
        },
        "test4_lookback_matrix": {
            "rows": test4_matrix,
            "wins": lookback_wins
        },
        "test5_skip_matrix": {
            "rows": test5_matrix,
            "wins": skip_wins
        },
        "summary_metrics": {
            "total_start_dates": len(all_start_dates),
            "beat_spy_count": beat_spy_count,
            "beat_spy_pct": f"{(beat_spy_count / len(all_start_dates)) * 100:.1f}%"
        }
    }


if __name__ == "__main__":
    out = run_all_strategy_tests()
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy_tester_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))

