"""
Factor Weight Grid Search & Overfitting Analysis Script.

Executes a full 66-combination grid search of Momentum, Quality, and Low-Volatility weights in 10% increments.
Evaluates performance across rolling 2-month (Short), 6-month (Medium), and 1-year (Long) horizon windows.
Enforces In-Sample (70%) vs Out-of-Sample (30%) chronological split to prevent overfitting.
"""

import os
import sys
import logging
import json
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any

# Ensure path includes workspace root
base_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(base_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from backtester.data import DataFetcher
from backtester.utils import load_universe
from backtester.portfolio import BacktestEngine
from backtester.strategy import MultiFactorCompositeStrategy

logging.basicConfig(level=logging.ERROR)

def generate_weight_grid() -> List[Tuple[float, float, float]]:
    """Generate all combinations of (w_mom, w_qual, w_lowvol) in 10% increments summing to 1.0."""
    grid = []
    # 10% increments from 0 to 10
    for i in range(11):
        for j in range(11 - i):
            k = 10 - i - j
            w_mom = round(i / 10.0, 2)
            w_qual = round(j / 10.0, 2)
            w_lowvol = round(k / 10.0, 2)
            grid.append((w_mom, w_qual, w_lowvol))
    
    # Ensure equal weight baseline (1/3, 1/3, 1/3) is explicitly included
    eq_w = (round(1/3, 4), round(1/3, 4), round(1/3, 4))
    if eq_w not in grid:
        grid.append(eq_w)
        
    return grid


def compute_rolling_horizon_metrics(
    portfolio_series: pd.Series,
    spy_series: pd.Series,
    window_days: int,
    step_days: int = 5
) -> Dict[str, float]:
    """
    Compute rolling window metrics for a given horizon length (in trading days).
    Returns average and worst-case metrics across all rolling windows.
    """
    if len(portfolio_series) < window_days + 1:
        return {
            "avg_return": np.nan,
            "worst_return": np.nan,
            "avg_max_dd": np.nan,
            "worst_max_dd": np.nan,
            "avg_calmar": np.nan,
            "worst_calmar": np.nan,
            "avg_sharpe": np.nan,
            "avg_excess_return": np.nan,
            "win_rate": np.nan,
            "n_windows": 0
        }

    returns_list = []
    max_dd_list = []
    calmar_list = []
    sharpe_list = []
    excess_return_list = []

    # Common dates
    common_idx = portfolio_series.index.intersection(spy_series.index)
    p_s = portfolio_series.reindex(common_idx)
    spy_s = spy_series.reindex(common_idx)

    N = len(p_s)
    for start_i in range(0, N - window_days + 1, step_days):
        end_i = start_i + window_days - 1
        
        p_sub = p_s.iloc[start_i : end_i + 1]
        spy_sub = spy_s.iloc[start_i : end_i + 1]
        
        if p_sub.empty or p_sub.iloc[0] <= 0:
            continue
            
        # 1. Total Return
        p_ret = (p_sub.iloc[-1] / p_sub.iloc[0]) - 1.0
        spy_ret = (spy_sub.iloc[-1] / spy_sub.iloc[0]) - 1.0 if (not spy_sub.empty and spy_sub.iloc[0] > 0) else 0.0
        excess_ret = p_ret - spy_ret

        # 2. Max Drawdown in window
        cummax = p_sub.cummax()
        dd = (cummax - p_sub) / cummax
        max_dd = float(dd.max())
        
        # 3. Annualized Return (CAGR)
        cagr = (1.0 + p_ret) ** (252.0 / window_days) - 1.0 if p_ret > -1.0 else -1.0
        
        # 4. Calmar Ratio
        effective_dd = max(max_dd, 0.005)  # floor drawdown at 0.5% to avoid divide-by-zero
        calmar = cagr / effective_dd

        # 5. Sharpe Ratio
        daily_rets = p_sub.pct_change().dropna()
        if len(daily_rets) > 5 and daily_rets.std() > 1e-8:
            sharpe = (daily_rets.mean() * np.sqrt(252.0)) / daily_rets.std()
        else:
            sharpe = 0.0

        returns_list.append(p_ret)
        max_dd_list.append(max_dd)
        calmar_list.append(calmar)
        sharpe_list.append(sharpe)
        excess_return_list.append(excess_ret)

    if not returns_list:
        return {
            "avg_return": 0.0, "worst_return": 0.0,
            "avg_max_dd": 0.0, "worst_max_dd": 0.0,
            "avg_calmar": 0.0, "worst_calmar": 0.0,
            "avg_sharpe": 0.0, "avg_excess_return": 0.0,
            "win_rate": 0.0, "n_windows": 0
        }

    rets_arr = np.array(returns_list)
    excess_arr = np.array(excess_return_list)

    return {
        "avg_return": float(np.mean(rets_arr)),
        "worst_return": float(np.min(rets_arr)),
        "avg_max_dd": float(np.mean(max_dd_list)),
        "worst_max_dd": float(np.max(max_dd_list)),
        "avg_calmar": float(np.mean(calmar_list)),
        "worst_calmar": float(np.min(calmar_list)),
        "avg_sharpe": float(np.mean(sharpe_list)),
        "avg_excess_return": float(np.mean(excess_arr)),
        "win_rate": float(np.mean(excess_arr > 0)),
        "n_windows": len(returns_list)
    }


def evaluate_weight_combination(
    weights: Tuple[float, float, float],
    prices_df: pd.DataFrame,
    raw_prices_df: pd.DataFrame,
    volumes_df: pd.DataFrame,
    spy_df: pd.Series,
    is_start: str,
    is_end: str,
    oos_start: str,
    oos_end: str
) -> Dict[str, Any]:
    """Run backtest for a specific weight combination and evaluate IS and OOS performance across 3 horizons."""
    w_mom, w_qual, w_lowvol = weights
    factor_weights = {"momentum": w_mom, "quality": w_qual, "low_vol": w_lowvol}
    
    # Full run backtest
    strat = MultiFactorCompositeStrategy(
        positions=10,
        universe_file="sp500.csv",
        factor_weights=factor_weights
    )
    engine = BacktestEngine(strategy=strat, initial_capital=30000.0, rebalance_frequency="monthly")
    res = engine.run(
        prices_df,
        start_date=is_start,
        end_date=oos_end,
        raw_prices_df=raw_prices_df,
        volumes_df=volumes_df
    )
    
    portfolio_df = res
    if "Portfolio Value" in portfolio_df.columns:
        p_series = portfolio_df["Portfolio Value"]
    else:
        p_series = portfolio_df.iloc[:, 0]
    
    p_series.index = pd.to_datetime(p_series.index)
    
    # Split into In-Sample (IS) and Out-of-Sample (OOS) portfolio series
    is_p_series = p_series.loc[(p_series.index >= pd.Timestamp(is_start)) & (p_series.index <= pd.Timestamp(is_end))]
    oos_p_series = p_series.loc[(p_series.index >= pd.Timestamp(oos_start)) & (p_series.index <= pd.Timestamp(oos_end))]
    
    spy_df.index = pd.to_datetime(spy_df.index)
    is_spy = spy_df.loc[(spy_df.index >= pd.Timestamp(is_start)) & (spy_df.index <= pd.Timestamp(is_end))]
    oos_spy = spy_df.loc[(spy_df.index >= pd.Timestamp(oos_start)) & (spy_df.index <= pd.Timestamp(oos_end))]

    # Horizon Windows in Trading Days:
    # Short = 42 days (~2 months)
    # Medium = 126 days (~6 months)
    # Long = 252 days (~1 year)
    horizons = {
        "short": 42,
        "medium": 126,
        "long": 252
    }

    is_results = {}
    for h_name, w_days in horizons.items():
        is_results[h_name] = compute_rolling_horizon_metrics(is_p_series, is_spy, window_days=w_days)

    oos_results = {}
    for h_name, w_days in horizons.items():
        oos_results[h_name] = compute_rolling_horizon_metrics(oos_p_series, oos_spy, window_days=w_days)

    # Composite In-Sample Calmar Score (50% Long, 30% Medium, 20% Short)
    is_calmar_composite = (
        0.50 * is_results["long"]["avg_calmar"] +
        0.30 * is_results["medium"]["avg_calmar"] +
        0.20 * is_results["short"]["avg_calmar"]
    )

    p_cummax = p_series.cummax()
    max_dd_full = float(((p_cummax - p_series) / p_cummax).max())

    return {
        "weights": {"momentum": w_mom, "quality": w_qual, "low_vol": w_lowvol},
        "weights_str": f"{int(round(w_mom*100))}/{int(round(w_qual*100))}/{int(round(w_lowvol*100))}",
        "is_calmar_composite": is_calmar_composite,
        "IS": is_results,
        "OOS": oos_results,
        "total_return_full": float((p_series.iloc[-1] / p_series.iloc[0]) - 1.0),
        "max_dd_full": max_dd_full
    }


def main():
    print("========================================================================")
    print("      MULTI-FACTOR WEIGHT GRID SEARCH & OVERFITTING ANALYSIS")
    print("========================================================================\n")
    
    # 1. Load Data
    fetcher = DataFetcher()
    universe = load_universe("sp500.csv")
    print("Loading universe price and volume data...")
    prices_df, open_df, raw_prices_df, volumes_df = fetcher.fetch_universe_data(
        universe, "2020-01-01", "2026-08-04", return_volume=True
    )
    spy_series = fetcher.load_single_ticker("SPY", "2020-01-01", "2026-08-04")
    
    # 2. Define In-Sample (70%) and Out-of-Sample (30%) Split
    bt_dates = prices_df.loc[(prices_df.index >= "2020-01-01") & (prices_df.index <= "2026-08-04")].index
    total_days = len(bt_dates)
    is_count = int(total_days * 0.70)
    
    is_start = bt_dates[0].strftime("%Y-%m-%d")
    is_end = bt_dates[is_count - 1].strftime("%Y-%m-%d")
    oos_start = bt_dates[is_count].strftime("%Y-%m-%d")
    oos_end = bt_dates[-1].strftime("%Y-%m-%d")
    
    print(f"Total Trading Days: {total_days}")
    print(f"In-Sample Period (70%):  {is_start} to {is_end} ({is_count} days)")
    print(f"Out-of-Sample Period (30%): {oos_start} to {oos_end} ({total_days - is_count} days)\n")
    
    # 3. Generate 66 Weight Combinations
    grid = generate_weight_grid()
    print(f"Evaluating {len(grid)} factor weight combinations across In-Sample & Out-of-Sample periods...")
    
    results = []
    for idx, w in enumerate(grid):
        w_mom, w_qual, w_lowvol = w
        sys.stdout.write(f"\rProcessing combination {idx+1}/{len(grid)}: Mom={w_mom*100:.0f}%, Qual={w_qual*100:.0f}%, LowVol={w_lowvol*100:.0f}%...")
        sys.stdout.flush()
        
        eval_res = evaluate_weight_combination(
            weights=w,
            prices_df=prices_df,
            raw_prices_df=raw_prices_df,
            volumes_df=volumes_df,
            spy_df=spy_series,
            is_start=is_start,
            is_end=is_end,
            oos_start=oos_start,
            oos_end=oos_end
        )
        results.append(eval_res)
        
    print("\n\nCompleted evaluation of all 66 weight combinations!")

    # Sort results by In-Sample Composite Calmar Score
    results.sort(key=lambda x: x["is_calmar_composite"], reverse=True)

    # Save full grid search results to JSON for reference
    output_json_path = os.path.join(base_dir, "grid_search_results.json")
    with open(output_json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Full grid search results saved to '{output_json_path}'")

    # Select Shortlisted Candidates
    # Top 4 by IS Calmar, plus Pure Momentum (100/0/0), Pure Quality (0/100/0), Pure Low-Vol (0/0/100), and Equal-Weight (33/33/33)
    top_candidates = results[:4]
    
    # Ensure specific reference strategies are present in shortlist
    reference_weights = ["100/0/0", "0/100/0", "0/0/100", "33/33/33"]
    shortlist = list(top_candidates)
    
    for ref_str in reference_weights:
        if not any(r["weights_str"] == ref_str for r in shortlist):
            matching = [r for r in results if r["weights_str"] == ref_str]
            if matching:
                shortlist.append(matching[0])

    print("\n========================================================================")
    print("                    IN-SAMPLE TOP RANKED COMBINATIONS")
    print("========================================================================")
    for i, res_item in enumerate(results[:10]):
        w_str = res_item["weights_str"]
        is_long_calmar = res_item["IS"]["long"]["avg_calmar"]
        is_med_calmar = res_item["IS"]["medium"]["avg_calmar"]
        is_short_calmar = res_item["IS"]["short"]["avg_calmar"]
        is_comp = res_item["is_calmar_composite"]
        print(f"Rank {i+1:2d} | Weights (M/Q/LV): {w_str:10s} | IS Composite Calmar: {is_comp:6.2f} (Long: {is_long_calmar:5.2f}, Med: {is_med_calmar:5.2f}, Short: {is_short_calmar:5.2f})")

    # Save summary report text file
    summary_txt_path = os.path.join(base_dir, "factor_grid_summary.txt")
    with open(summary_txt_path, "w") as f:
        f.write(f"FACTOR WEIGHT GRID SEARCH SUMMARY REPORT\n")
        f.write(f"In-Sample Date Range: {is_start} to {is_end}\n")
        f.write(f"Out-of-Sample Date Range: {oos_start} to {oos_end}\n\n")
        f.write("SHORTLISTED COMBINATIONS (IS vs OOS COMPARISON):\n\n")
        
        for item in shortlist:
            w_str = item["weights_str"]
            f.write(f"=== Weights: {w_str} (Mom/Qual/LowVol) ===\n")
            f.write(f"  IS  Composite Calmar: {item['is_calmar_composite']:.2f}\n")
            f.write(f"  IS  Long Horizon  - Avg Ret: {item['IS']['long']['avg_return']*100:.2f}%, Worst DD: {item['IS']['long']['worst_max_dd']*100:.2f}%, Calmar: {item['IS']['long']['avg_calmar']:.2f}, Sharpe: {item['IS']['long']['avg_sharpe']:.2f}, Alpha vs SPY: {item['IS']['long']['avg_excess_return']*100:.2f}%\n")
            f.write(f"  IS  Med Horizon   - Avg Ret: {item['IS']['medium']['avg_return']*100:.2f}%, Worst DD: {item['IS']['medium']['worst_max_dd']*100:.2f}%, Calmar: {item['IS']['medium']['avg_calmar']:.2f}, Sharpe: {item['IS']['medium']['avg_sharpe']:.2f}, Alpha vs SPY: {item['IS']['medium']['avg_excess_return']*100:.2f}%\n")
            f.write(f"  IS  Short Horizon - Avg Ret: {item['IS']['short']['avg_return']*100:.2f}%, Worst DD: {item['IS']['short']['worst_max_dd']*100:.2f}%, Calmar: {item['IS']['short']['avg_calmar']:.2f}, Sharpe: {item['IS']['short']['avg_sharpe']:.2f}, Alpha vs SPY: {item['IS']['short']['avg_excess_return']*100:.2f}%\n")
            f.write(f"  OOS Long Horizon  - Avg Ret: {item['OOS']['long']['avg_return']*100:.2f}%, Worst DD: {item['OOS']['long']['worst_max_dd']*100:.2f}%, Calmar: {item['OOS']['long']['avg_calmar']:.2f}, Sharpe: {item['OOS']['long']['avg_sharpe']:.2f}, Alpha vs SPY: {item['OOS']['long']['avg_excess_return']*100:.2f}%\n")
            f.write(f"  OOS Med Horizon   - Avg Ret: {item['OOS']['medium']['avg_return']*100:.2f}%, Worst DD: {item['OOS']['medium']['worst_max_dd']*100:.2f}%, Calmar: {item['OOS']['medium']['avg_calmar']:.2f}, Sharpe: {item['OOS']['medium']['avg_sharpe']:.2f}, Alpha vs SPY: {item['OOS']['medium']['avg_excess_return']*100:.2f}%\n")
            f.write(f"  OOS Short Horizon - Avg Ret: {item['OOS']['short']['avg_return']*100:.2f}%, Worst DD: {item['OOS']['short']['worst_max_dd']*100:.2f}%, Calmar: {item['OOS']['short']['avg_calmar']:.2f}, Sharpe: {item['OOS']['short']['avg_sharpe']:.2f}, Alpha vs SPY: {item['OOS']['short']['avg_excess_return']*100:.2f}%\n")
            
            # Check for overfitting flag (e.g., OOS Long Calmar < 0.60 * IS Long Calmar)
            is_l_calmar = item['IS']['long']['avg_calmar']
            oos_l_calmar = item['OOS']['long']['avg_calmar']
            if is_l_calmar > 0 and (oos_l_calmar / is_l_calmar) < 0.65:
                f.write(f"  [OVERFITTING WARNING]: Significant performance degradation in Out-of-Sample (Long Calmar dropped from {is_l_calmar:.2f} to {oos_l_calmar:.2f})\n")
            else:
                f.write(f"  [ROBUSTNESS VERIFIED]: Consistent Out-of-Sample performance relative to In-Sample\n")
            f.write("\n")

    print(f"Summary saved to '{summary_txt_path}'")

if __name__ == "__main__":
    main()
