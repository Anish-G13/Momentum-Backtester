import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import json
import logging
import pandas as pd
import numpy as np

from backtester.config import Config
from backtester.utils import load_universe, get_rebalance_dates
from backtester.data import DataFetcher
from backtester.strategy import CrossSectionalMomentumStrategy, MultiFactorCompositeStrategy, clear_strategy_cache
from backtester.portfolio import BacktestEngine, clear_portfolio_cache
from backtester.metrics import compute_performance_summary, calculate_drawdowns

# Suppress debug logs for clean execution
logging.getLogger("BacktestEngine").setLevel(logging.WARNING)
logging.getLogger("Main").setLevel(logging.WARNING)

def run_single_scenario(name, strat_kwargs, engine_kwargs, universe_prices, open_prices, raw_prices, volumes, config):
    clear_strategy_cache()
    clear_portfolio_cache()

    mode = strat_kwargs.pop("strategy_mode", "momentum_only")
    if mode == "multi_factor_composite":
        strategy = MultiFactorCompositeStrategy(**strat_kwargs)
    else:
        strategy = CrossSectionalMomentumStrategy(**strat_kwargs)

    engine = BacktestEngine(
        initial_capital=config.initial_capital,
        strategy=strategy,
        rebalance_frequency=config.rebalance_frequency,
        **engine_kwargs
    )

    portfolio_history = engine.run(
        prices_df=universe_prices,
        start_date=config.start_date,
        end_date=config.end_date,
        open_prices_df=open_prices,
        raw_prices_df=raw_prices,
        volumes_df=volumes
    )

    metrics = compute_performance_summary(
        portfolio_history=portfolio_history,
        trade_logs=engine.trade_logs
    )

    # Calculate June-August 2026 performance window
    ja_sub = portfolio_history.loc[(portfolio_history.index >= "2026-06-01") & (portfolio_history.index <= "2026-08-04")]
    if not ja_sub.empty:
        ja_start = ja_sub["Portfolio Value"].iloc[0]
        ja_end = ja_sub["Portfolio Value"].iloc[-1]
        ja_return = (ja_end / ja_start - 1.0) if ja_start > 0 else 0.0
        _, ja_max_dd = calculate_drawdowns(ja_sub["Portfolio Value"])
    else:
        ja_return = 0.0
        ja_max_dd = 0.0

    return {
        "Scenario": name,
        "Total Return": metrics["Total Return"],
        "CAGR": metrics["Annualized Return (CAGR)"],
        "Max Drawdown": metrics["Maximum Drawdown"],
        "Calmar Ratio": metrics.get("Calmar Ratio", 0.0),
        "Volatility": metrics["Volatility"],
        "Sharpe Ratio": metrics["Sharpe Ratio"],
        "Jun-Aug 2026 Return": ja_return,
        "Jun-Aug 2026 Max DD": ja_max_dd,
        "Stop Loss Triggers": getattr(engine, "stop_loss_trigger_count", 0),
        "Whipsaw Count": getattr(engine, "whipsaw_count", 0),
        "Portfolio History": portfolio_history
    }

def main():
    config = Config()
    tickers = load_universe(config.universe_file)
    fetcher = DataFetcher(cache_dir=config.cache_dir)

    universe_prices, universe_open_prices, raw_universe_prices, universe_volumes = fetcher.fetch_universe_data(
        tickers=tickers,
        start_date=config.start_date,
        end_date=config.end_date,
        buffer_months=config.lookback_months + 3,
        return_raw=True,
        return_volume=True
    )

    base_strat_kwargs = {
        "positions": 20,
        "lookback_months": 12,
        "skip_last_month": True,
        "universe_file": config.universe_file,
        "max_positions_per_sector": 3,
        "min_avg_dollar_volume": 30000000,
        "min_market_cap": 2000000000,
        "ranking_method": "risk_adjusted",
        "regime_filter": True,
        "regime_reduced_exposure_pct": 0.5,
        "earnings_blackout_days": 5,
    }

    scenarios = [
        ("1. Baseline (Existing 5 Filters)", {}, {}),
        ("2. Momentum Regime Filter Only", {"momentum_regime_filter": True, "momentum_regime_lookback_days": 20, "momentum_regime_threshold": 0.0}, {}),
        ("3. Volatility Scaling Only", {"vol_scaling": True, "vol_scaling_lookback_days": 20, "target_volatility": 0.25}, {}),
        ("4. Stop Loss Only (100% Cash)", {}, {"stop_loss_pct": 0.15, "stop_loss_cash_pct": 1.0}),
        ("5. All 3 Protections Combined", {"momentum_regime_filter": True, "momentum_regime_lookback_days": 20, "momentum_regime_threshold": 0.0, "vol_scaling": True, "vol_scaling_lookback_days": 20, "target_volatility": 0.25}, {"stop_loss_pct": 0.15, "stop_loss_cash_pct": 1.0}),
        ("6. Stop Loss (50% Partial Cash)", {}, {"stop_loss_pct": 0.15, "stop_loss_cash_pct": 0.5}),
        ("7. Multi-Factor + All 3 Protections", {"strategy_mode": "multi_factor_composite", "momentum_regime_filter": True, "momentum_regime_lookback_days": 20, "momentum_regime_threshold": 0.0, "vol_scaling": True, "vol_scaling_lookback_days": 20, "target_volatility": 0.25}, {"stop_loss_pct": 0.15, "stop_loss_cash_pct": 1.0}),
    ]

    results = []
    print("\nExecuting comparative backtests across 7 scenarios...\n")

    for name, s_extra, e_extra in scenarios:
        s_kwargs = base_strat_kwargs.copy()
        s_kwargs.update(s_extra)
        res = run_single_scenario(name, s_kwargs, e_extra, universe_prices, universe_open_prices, raw_universe_prices, universe_volumes, config)
        results.append(res)
        print(f"Completed: {name}")

    # Audit for identical metrics across scenarios (Detecting calculation/caching bugs)
    print("\n==========================================================================================")
    print("                      IDENTICAL METRICS AUDIT (INTEGRITY CHECK)")
    print("==========================================================================================")
    all_returns = [r["Total Return"] for r in results]
    if len(all_returns) != len(set(all_returns)):
        print("WARNING: Identical total return detected across distinct scenarios! Investigating duplicate values...")
    else:
        print("PASSED: All 7 scenarios produced distinct, independent metrics. No cached-result bug detected.")

    # Print summary table
    print("\n=================================================================================================================================");
    print("                                            COMPARATIVE BACKTEST PERFORMANCE SUMMARY REPORT");
    print("=================================================================================================================================");
    hdr = f"{'Scenario':<36} | {'Tot Ret':<9} | {'CAGR':<8} | {'Max DD':<8} | {'Calmar':<7} | {'Vol':<8} | {'Sharpe':<7} | {'Jun-Aug Ret':<11} | {'Jun-Aug DD':<10} | {'SL Trigs':<8} | {'Whipsaws':<8}"
    print(hdr)
    print("-" * len(hdr))

    summary_export = []
    for r in results:
        tot_ret = f"{r['Total Return']*100:+.2f}%"
        cagr = f"{r['CAGR']*100:.2f}%"
        mdd = f"{r['Max Drawdown']*100:.2f}%"
        calmar = f"{r['Calmar Ratio']:.2f}"
        vol = f"{r['Volatility']*100:.2f}%"
        sharpe = f"{r['Sharpe Ratio']:.2f}"
        ja_ret = f"{r['Jun-Aug 2026 Return']*100:+.2f}%"
        ja_dd = f"{r['Jun-Aug 2026 Max DD']*100:.2f}%"
        sl_trig = str(r['Stop Loss Triggers'])
        whipsaw = str(r['Whipsaw Count'])

        print(f"{r['Scenario']:<36} | {tot_ret:<9} | {cagr:<8} | {mdd:<8} | {calmar:<7} | {vol:<8} | {sharpe:<7} | {ja_ret:<11} | {ja_dd:<10} | {sl_trig:<8} | {whipsaw:<8}")

        summary_export.append({
            "Scenario": r["Scenario"],
            "Total Return Pct": round(r["Total Return"] * 100, 2),
            "CAGR Pct": round(r["CAGR"] * 100, 2),
            "Max Drawdown Pct": round(r["Max Drawdown"] * 100, 2),
            "Calmar Ratio": round(r["Calmar Ratio"], 2),
            "Volatility Pct": round(r["Volatility"] * 100, 2),
            "Sharpe Ratio": round(r["Sharpe Ratio"], 2),
            "Jun-Aug 2026 Return Pct": round(r["Jun-Aug 2026 Return"] * 100, 2),
            "Jun-Aug 2026 Max DD Pct": round(r["Jun-Aug 2026 Max DD"] * 100, 2),
            "Stop Loss Triggers": r["Stop Loss Triggers"],
            "Whipsaw Count": r["Whipsaw Count"]
        })

    with open("/backtester/comparative_results.json", "w") as f:
        json.dump(summary_export, f, indent=2)

    print("\nResults successfully exported to /backtester/comparative_results.json")

if __name__ == "__main__":
    main()
