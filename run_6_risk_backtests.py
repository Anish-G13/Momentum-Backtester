import sys
import os
import json
import argparse
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtester.config import Config
from backtester.main import run_backtest

scenarios = [
    {
        "name": "1. Baseline (All 5 Filters Off)",
        "config": Config(
            start_date="2025-07-31",
            end_date="2026-08-04",
            initial_capital=30000.0,
            universe_file="russell1000.csv",
            positions=10,
            rebalance_frequency="monthly",
            skip_last_month=True,
            max_positions_per_sector=0,
            min_avg_dollar_volume=0.0,
            min_market_cap=0.0,
            ranking_method="raw_return",
            regime_filter=False,
            earnings_blackout_days=0
        )
    },
    {
        "name": "2. Sector Cap Only (Max 3/Sector, Issuer-Deduped)",
        "config": Config(
            start_date="2025-07-31",
            end_date="2026-08-04",
            initial_capital=30000.0,
            universe_file="russell1000.csv",
            positions=10,
            rebalance_frequency="monthly",
            skip_last_month=True,
            max_positions_per_sector=3,
            min_avg_dollar_volume=0.0,
            min_market_cap=0.0,
            ranking_method="raw_return",
            regime_filter=False,
            earnings_blackout_days=0
        )
    },
    {
        "name": "3. Liquidity Floor Only ($30M Vol, $2B MktCap)",
        "config": Config(
            start_date="2025-07-31",
            end_date="2026-08-04",
            initial_capital=30000.0,
            universe_file="russell1000.csv",
            positions=10,
            rebalance_frequency="monthly",
            skip_last_month=True,
            max_positions_per_sector=0,
            min_avg_dollar_volume=30_000_000.0,
            min_market_cap=2_000_000_000.0,
            ranking_method="raw_return",
            regime_filter=False,
            earnings_blackout_days=0
        )
    },
    {
        "name": "4. Risk-Adjusted Ranking Only (Sharpe Ranking)",
        "config": Config(
            start_date="2025-07-31",
            end_date="2026-08-04",
            initial_capital=30000.0,
            universe_file="russell1000.csv",
            positions=10,
            rebalance_frequency="monthly",
            skip_last_month=True,
            max_positions_per_sector=0,
            min_avg_dollar_volume=0.0,
            min_market_cap=0.0,
            ranking_method="risk_adjusted",
            regime_filter=False,
            earnings_blackout_days=0
        )
    },
    {
        "name": "5. Market Regime Filter Only (SPY 200d SMA)",
        "config": Config(
            start_date="2025-07-31",
            end_date="2026-08-04",
            initial_capital=30000.0,
            universe_file="russell1000.csv",
            positions=10,
            rebalance_frequency="monthly",
            skip_last_month=True,
            max_positions_per_sector=0,
            min_avg_dollar_volume=0.0,
            min_market_cap=0.0,
            ranking_method="raw_return",
            regime_filter=True,
            regime_reduced_exposure_pct=0.5,
            earnings_blackout_days=0
        )
    },
    {
        "name": "6. All 5 Filters Combined",
        "config": Config(
            start_date="2025-07-31",
            end_date="2026-08-04",
            initial_capital=30000.0,
            universe_file="russell1000.csv",
            positions=10,
            rebalance_frequency="monthly",
            skip_last_month=True,
            max_positions_per_sector=3,
            min_avg_dollar_volume=30_000_000.0,
            min_market_cap=2_000_000_000.0,
            ranking_method="risk_adjusted",
            regime_filter=True,
            regime_reduced_exposure_pct=0.5,
            earnings_blackout_days=3
        )
    }
]

results = []
raw_results = []

for sc in scenarios:
    res = run_backtest(sc["config"])
    metrics = res.get("metrics", {})
    port_hist = res.get("portfolio_history")
    
    total_return = float(metrics.get("Total Return", 0.0)) * 100.0
    sharpe = float(metrics.get("Sharpe Ratio", 0.0))
    
    # Calculate Max Drawdown and Date Range (Peak Date to Trough Date) independently from equity curve
    if port_hist:
        df_port = pd.DataFrame(port_hist) if isinstance(port_hist, list) else port_hist
        equity = df_port["Portfolio Value"].astype(float)
        if "Date" in df_port.columns:
            dates = pd.to_datetime(df_port["Date"])
            equity.index = dates
        
        cummax = equity.cummax()
        drawdown = (equity - cummax) / cummax
        trough_idx = drawdown.idxmin()
        peak_idx = equity.loc[:trough_idx].idxmax()
        max_dd_val = abs(float(drawdown.loc[trough_idx])) * 100.0
        
        peak_str = peak_idx.strftime("%Y-%m-%d") if hasattr(peak_idx, "strftime") else str(peak_idx)
        trough_str = trough_idx.strftime("%Y-%m-%d") if hasattr(trough_idx, "strftime") else str(trough_idx)
        dd_str = f"-{max_dd_val:.2f}% ({peak_str} to {trough_str})"
    else:
        max_dd_val = 0.0
        dd_str = "0.00%"

    # Count rebalance months where fewer than 10 positions were held
    rebal_snaps = res.get("rebalance_snapshots", [])
    months_under_10 = sum(1 for snap in rebal_snaps if snap.get("count", 0) < 10)
    
    raw_results.append({
        "scenario": sc["name"],
        "total_return": total_return,
        "max_dd_val": max_dd_val,
        "sharpe": sharpe,
        "dd_str": dd_str,
        "months_under_10": months_under_10
    })

    results.append({
        "Scenario": sc["name"],
        "Total Return (%)": f"{total_return:+.2f}%",
        "Max Drawdown (Range)": dd_str,
        "Sharpe Ratio": f"{sharpe:.2f}",
        "Months < 10 Pos": months_under_10
    })

# --- SANITY CHECK & CACHING AUDIT ---
warnings = []
for i in range(len(raw_results)):
    for j in range(i + 1, len(raw_results)):
        r1 = raw_results[i]
        r2 = raw_results[j]
        ret_diff = abs(r1["total_return"] - r2["total_return"])
        if ret_diff > 0.01:
            # Different total returns!
            dd_identical = abs(r1["max_dd_val"] - r2["max_dd_val"]) < 0.001 and r1["dd_str"] == r2["dd_str"]
            sharpe_identical = abs(r1["sharpe"] - r2["sharpe"]) < 0.001
            if dd_identical:
                warnings.append(
                    f"RED FLAG: Scenario '{r1['scenario']}' ({r1['total_return']:+.2f}%) and '{r2['scenario']}' ({r2['total_return']:+.2f}%) "
                    f"have different returns but IDENTICAL Max Drawdown ({r1['dd_str']}). Potential metric caching bug!"
                )
            if sharpe_identical:
                warnings.append(
                    f"RED FLAG: Scenario '{r1['scenario']}' ({r1['total_return']:+.2f}%) and '{r2['scenario']}' ({r2['total_return']:+.2f}%) "
                    f"have different returns but IDENTICAL Sharpe Ratio ({r1['sharpe']:.2f}). Potential metric caching bug!"
                )

parser = argparse.ArgumentParser()
parser.add_argument("--json-out", type=str, default="", help="Path to write JSON output")
args, _ = parser.parse_known_args()

df_res = pd.DataFrame(results)
print("\n\n" + "="*110)
print("                               SIX-WAY RISK FILTERS COMPARISON TABLE")
print("="*110)
print(df_res.to_string(index=False))
print("="*110)

if warnings:
    print("\n\n" + "!"*110)
    print("                               SANITY CHECK WARNINGS TRIGGERED:")
    print("!"*110)
    for w in warnings:
        print(f" - {w}")
    print("!"*110)
else:
    print("\n[Sanity Check Passed] All 6 scenario risk metrics independently verified. No caching artifacts detected.")

if args.json_out:
    out_payload = {
        "scenarios": results,
        "rawResults": raw_results,
        "warnings": warnings,
        "sanityCheckPassed": len(warnings) == 0,
        "timestamp": pd.Timestamp.now().isoformat()
    }
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(out_payload, f, indent=2)
    print(f"\n[Saved JSON comparison report to {args.json_out}]")


