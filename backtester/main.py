"""
Main execution entry point for the Stock Momentum Backtester CLI & Engine.

Usage:
    python main.py
    python main.py --start 2020-01-01 --end 2026-08-04 --capital 30000 --positions 20 --json-out output.json
"""

import sys
import os
import argparse
import json
import logging
import pandas as pd

try:
    from backtester.config import Config
    from backtester.utils import load_universe, get_rebalance_dates
    from backtester.data import DataFetcher
    from backtester.strategy import CrossSectionalMomentumStrategy, MultiFactorCompositeStrategy, clear_strategy_cache
    from backtester.portfolio import BacktestEngine, clear_portfolio_cache
    from backtester.metrics import compute_performance_summary
    from backtester.report import (
        save_trades_csv,
        save_portfolio_csv,
        save_verification_csv,
        generate_equity_curve_chart,
        generate_drawdown_chart,
        print_summary_report,
        print_verification_report,
    )
except ImportError:
    from config import Config
    from utils import load_universe, get_rebalance_dates
    from data import DataFetcher
    from strategy import CrossSectionalMomentumStrategy, clear_strategy_cache
    from portfolio import BacktestEngine, clear_portfolio_cache
    from metrics import compute_performance_summary
    from report import (
        save_trades_csv,
        save_portfolio_csv,
        save_verification_csv,
        generate_equity_curve_chart,
        generate_drawdown_chart,
        print_summary_report,
        print_verification_report,
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Main")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Professional Python Stock Momentum Backtester")
    parser.add_argument("--start", type=str, default=None, help="Start Date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End Date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=None, help="Initial Capital USD")
    parser.add_argument("--positions", type=int, default=None, help="Top N positions to buy")
    parser.add_argument("--lookback", type=int, default=None, help="Lookback months for momentum")
    parser.add_argument("--skip-last", type=str, default=None, help="Skip last month (true/false)")
    parser.add_argument("--include-shorts", type=str, default=None, help="Include short leg (true/false)")
    parser.add_argument("--rebalance-freq", type=str, default=None, help="Rebalance frequency (monthly/weekly/quarterly)")
    parser.add_argument("--universe", type=str, default=None, help="CSV file with stock tickers")
    parser.add_argument("--verify-date", type=str, default=None, help="Rebalance date for verification mode (YYYY-MM-DD)")
    parser.add_argument("--max-positions-per-sector", type=int, default=None, help="Max positions per sector")
    parser.add_argument("--min-avg-dollar-volume", type=float, default=None, help="Min 20d avg dollar volume")
    parser.add_argument("--min-market-cap", type=float, default=None, help="Min market cap USD")
    parser.add_argument("--ranking-method", type=str, default=None, help="Ranking method: raw_return or risk_adjusted")
    parser.add_argument("--regime-filter", type=str, default=None, help="Enable SPY 200d SMA regime filter (true/false)")
    parser.add_argument("--regime-reduced-exposure-pct", type=float, default=None, help="Regime reduced exposure pct (e.g. 0.5)")
    parser.add_argument("--earnings-blackout-days", type=int, default=None, help="Earnings blackout window in trading days")
    parser.add_argument("--strategy-mode", type=str, default=None, help="Strategy mode: momentum_only or multi_factor_composite")
    parser.add_argument("--factor-weights", type=str, default=None, help="Comma-separated factor weights: momentum,quality,low_vol (e.g. 0.33,0.33,0.33)")
    parser.add_argument("--momentum-regime-filter", type=str, default=None, help="Enable momentum-factor-specific regime filter (true/false)")
    parser.add_argument("--momentum-regime-lookback-days", type=int, default=None, help="Momentum regime lookback days (default: 20)")
    parser.add_argument("--momentum-regime-threshold", type=float, default=None, help="Momentum regime threshold (default: 0.0)")
    parser.add_argument("--vol-scaling", type=str, default=None, help="Enable volatility scaling (true/false)")
    parser.add_argument("--vol-scaling-lookback-days", type=int, default=None, help="Volatility scaling lookback days (default: 20)")
    parser.add_argument("--target-volatility", type=float, default=None, help="Target volatility (e.g. 0.25)")
    parser.add_argument("--stop-loss-pct", type=float, default=None, help="Stop loss drawdown threshold (e.g. 0.15)")
    parser.add_argument("--stop-loss-cash-pct", type=float, default=None, help="Stop loss cash percentage (default: 1.0)")
    parser.add_argument("--stop-loss-reentry-mode", type=str, default=None, help="Stop loss re-entry mode: recovery or months")
    parser.add_argument("--stop-loss-reentry-pct", type=float, default=None, help="Stop loss re-entry recovery percentage")
    parser.add_argument("--stop-loss-reentry-months", type=int, default=None, help="Stop loss re-entry months")
    parser.add_argument("--json-out", type=str, default=None, help="Path to write JSON performance output")
    return parser.parse_args()


import math

def sanitize_for_json(obj):
    if isinstance(obj, (pd.Timestamp, pd.Period)):
        return str(obj)
    elif hasattr(obj, "isoformat"):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif hasattr(obj, "item"):
        val = obj.item()
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val
    elif pd.isna(obj):
        return None
    return obj

def run_backtest(config: Config) -> dict:
    """
    Run full backtest workflow and generate report outputs.
    """
    clear_strategy_cache()
    clear_portfolio_cache()

    logger.info("Starting Momentum Backtest run...")
    logger.info(f"Parameters: Start={config.start_date}, End={config.end_date}, "
                f"Capital=${config.initial_capital:,.2f}, Positions={config.positions}, "
                f"Lookback={config.lookback_months}m, SkipLast={config.skip_last_month}, "
                f"IncludeShorts={config.include_shorts}, Universe={config.universe_file}")

    # 1. Load ticker universe
    tickers = load_universe(config.universe_file)
    print(f"Total tickers loaded: {len(tickers)}")
    logger.info(f"Total tickers loaded: {len(tickers)} from universe file '{config.universe_file}'.")
    if "russell1000" in str(config.universe_file).lower():
        logger.info("Note: Historical constituent membership (DateAdded/DateRemoved) is unavailable for Russell 1000; default static dates used.")

    # 2. Fetch price data (close and open) for stock universe with local cache
    fetcher = DataFetcher(cache_dir=config.cache_dir)
    end_fetch_date = config.end_date
    if config.verify_date and config.verify_date > config.end_date:
        end_fetch_date = config.verify_date

    universe_prices, universe_open_prices, raw_universe_prices, universe_volumes = fetcher.fetch_universe_data(
        tickers=tickers,
        start_date=config.start_date,
        end_date=end_fetch_date,
        buffer_months=config.lookback_months + 3,
        return_raw=True,
        return_volume=True
    )

    # 3. Fetch SPY benchmark prices
    logger.info("Fetching SPY benchmark price data...")
    spy_series = fetcher.load_single_ticker("SPY", config.start_date, config.end_date)
    benchmark_history = None

    if spy_series is not None and not spy_series.empty:
        # Scale SPY buy-and-hold value to match initial capital
        spy_start_price = float(spy_series.iloc[0])
        spy_shares = config.initial_capital / spy_start_price
        spy_values = spy_series * spy_shares
        benchmark_history = pd.DataFrame({
            "Portfolio Value": spy_values,
            "Cash": 0.0
        })
        if "SPY" not in universe_prices.columns:
            universe_prices["SPY"] = spy_series

    # 4. Instantiate strategy based on strategy_mode
    if getattr(config, "strategy_mode", "momentum_only").lower() == "multi_factor_composite":
        logger.info(f"Instantiating MultiFactorCompositeStrategy with factor weights: {config.factor_weights}")
        strategy = MultiFactorCompositeStrategy(
            positions=config.positions,
            lookback_months=config.lookback_months,
            skip_last_month=config.skip_last_month,
            include_shorts=config.include_shorts,
            universe_file=config.universe_file,
            max_positions_per_sector=config.max_positions_per_sector,
            min_avg_dollar_volume=config.min_avg_dollar_volume,
            min_market_cap=config.min_market_cap,
            ranking_method=config.ranking_method,
            regime_filter=config.regime_filter,
            regime_reduced_exposure_pct=config.regime_reduced_exposure_pct,
            earnings_blackout_days=config.earnings_blackout_days,
            factor_weights=config.factor_weights,
            momentum_regime_filter=config.momentum_regime_filter,
            momentum_regime_lookback_days=config.momentum_regime_lookback_days,
            momentum_regime_threshold=config.momentum_regime_threshold,
            vol_scaling=config.vol_scaling,
            vol_scaling_lookback_days=config.vol_scaling_lookback_days,
            target_volatility=config.target_volatility
        )
    else:
        logger.info("Instantiating CrossSectionalMomentumStrategy (Momentum-Only Mode)")
        strategy = CrossSectionalMomentumStrategy(
            positions=config.positions,
            lookback_months=config.lookback_months,
            skip_last_month=config.skip_last_month,
            include_shorts=config.include_shorts,
            universe_file=config.universe_file,
            max_positions_per_sector=config.max_positions_per_sector,
            min_avg_dollar_volume=config.min_avg_dollar_volume,
            min_market_cap=config.min_market_cap,
            ranking_method=config.ranking_method,
            regime_filter=config.regime_filter,
            regime_reduced_exposure_pct=config.regime_reduced_exposure_pct,
            earnings_blackout_days=config.earnings_blackout_days,
            momentum_regime_filter=config.momentum_regime_filter,
            momentum_regime_lookback_days=config.momentum_regime_lookback_days,
            momentum_regime_threshold=config.momentum_regime_threshold,
            vol_scaling=config.vol_scaling,
            vol_scaling_lookback_days=config.vol_scaling_lookback_days,
            target_volatility=config.target_volatility
        )

    # 5. Run backtest engine
    engine = BacktestEngine(
        initial_capital=config.initial_capital,
        strategy=strategy,
        rebalance_frequency=config.rebalance_frequency,
        stop_loss_pct=config.stop_loss_pct,
        stop_loss_cash_pct=config.stop_loss_cash_pct,
        stop_loss_reentry_mode=config.stop_loss_reentry_mode,
        stop_loss_reentry_pct=config.stop_loss_reentry_pct,
        stop_loss_reentry_months=config.stop_loss_reentry_months
    )
    portfolio_history = engine.run(
        prices_df=universe_prices,
        start_date=config.start_date,
        end_date=config.end_date,
        open_prices_df=universe_open_prices,
        raw_prices_df=raw_universe_prices,
        volumes_df=universe_volumes
    )

    # 6. Calculate performance metrics
    metrics = compute_performance_summary(
        portfolio_history=portfolio_history,
        trade_logs=engine.trade_logs,
        benchmark_history=benchmark_history
    )

    # 7. Print terminal summary report
    print_summary_report(metrics)

    # 8. Save output CSV files
    trades_path = save_trades_csv(engine.trade_logs, config.output_dir)
    portfolio_path = save_portfolio_csv(portfolio_history, config.output_dir)
    logger.info(f"Saved trades log to '{trades_path}'")
    logger.info(f"Saved portfolio log to '{portfolio_path}'")

    # 8b. Verification Mode Execution
    verify_date_str = config.verify_date
    if not verify_date_str and engine.rebalance_snapshots:
        verify_date_str = engine.rebalance_snapshots[-1].date.strftime("%Y-%m-%d")
    elif not verify_date_str:
        verify_date_str = config.end_date

    verify_ts = pd.Timestamp(verify_date_str)
    matched_snapshot = None
    for snap in engine.rebalance_snapshots:
        if snap.date == verify_ts or snap.date.strftime("%Y-%m-%d") == verify_date_str:
            matched_snapshot = snap
            break

    if matched_snapshot:
        verify_signal_ts = matched_snapshot.signal_date
    else:
        rebal_dates = sorted(get_rebalance_dates(universe_prices, "M"))
        past_dates = [d for d in rebal_dates if d <= verify_ts]
        verify_signal_ts = past_dates[-1] if past_dates else verify_ts

    logger.info(f"Running Verification Mode for rebalance execution date: {verify_date_str} (signal date: {verify_signal_ts.strftime('%Y-%m-%d')})")
    df_verification = strategy.get_detailed_verification(verify_signal_ts, universe_prices)
    verification_path = save_verification_csv(df_verification, config.output_dir)
    logger.info(f"Saved verification log to '{verification_path}'")
    print_verification_report(df_verification, verify_signal_ts.strftime("%Y-%m-%d"))

    # 9. Generate charts
    equity_chart_path = generate_equity_curve_chart(
        portfolio_history=portfolio_history,
        benchmark_history=benchmark_history,
        output_dir=config.output_dir
    )
    drawdown_chart_path = generate_drawdown_chart(
        portfolio_history=portfolio_history,
        output_dir=config.output_dir
    )
    logger.info(f"Generated chart '{equity_chart_path}'")
    logger.info(f"Generated chart '{drawdown_chart_path}'")

    # Construct complete result object
    trade_dicts = [t.to_dict() for t in engine.trade_logs]
    history_dicts = portfolio_history.reset_index().to_dict(orient="records")
    for row in history_dicts:
        if isinstance(row["Date"], pd.Timestamp):
            row["Date"] = row["Date"].strftime("%Y-%m-%d")

    bm_dicts = []
    if benchmark_history is not None:
        bm_df = benchmark_history.reset_index()
        bm_df["Date"] = bm_df["Date"].dt.strftime("%Y-%m-%d")
        bm_dicts = bm_df.to_dict(orient="records")

    verification_records = df_verification.to_dict(orient="records")

    result_payload = {
        "metrics": metrics,
        "config": config.to_dict(),
        "portfolio_history": history_dicts,
        "benchmark_history": bm_dicts,
        "trades": trade_dicts,
        "delisted_records": engine.delisted_records,
        "rebalance_snapshots": [s.to_dict() for s in engine.rebalance_snapshots],
        "verification_date": verify_date_str,
        "verification_records": verification_records,
        "files": {
            "trades_csv": trades_path,
            "portfolio_csv": portfolio_path,
            "verification_csv": verification_path,
            "equity_curve_png": equity_chart_path,
            "drawdown_png": drawdown_chart_path
        }
    }

    return sanitize_for_json(result_payload)


def main():
    args = parse_args()

    # Load default config and apply command line overrides
    cfg = Config()
    if args.start:
        cfg.start_date = args.start
    if args.end:
        cfg.end_date = args.end
    if args.capital:
        cfg.initial_capital = args.capital
    if args.positions:
        cfg.positions = args.positions
    if args.lookback:
        cfg.lookback_months = args.lookback
    if args.skip_last is not None:
        cfg.skip_last_month = args.skip_last.lower() in ("true", "1", "t", "yes")
    if args.include_shorts is not None:
        cfg.include_shorts = args.include_shorts.lower() in ("true", "1", "t", "yes")
    if args.rebalance_freq:
        cfg.rebalance_frequency = args.rebalance_freq
    if args.universe:
        cfg.universe_file = args.universe
    if args.verify_date:
        cfg.verify_date = args.verify_date
    if args.max_positions_per_sector is not None:
        cfg.max_positions_per_sector = args.max_positions_per_sector
    if args.min_avg_dollar_volume is not None:
        cfg.min_avg_dollar_volume = args.min_avg_dollar_volume
    if args.min_market_cap is not None:
        cfg.min_market_cap = args.min_market_cap
    if args.ranking_method is not None:
        cfg.ranking_method = args.ranking_method
    if args.regime_filter is not None:
        cfg.regime_filter = args.regime_filter.lower() in ("true", "1", "t", "yes")
    if args.regime_reduced_exposure_pct is not None:
        cfg.regime_reduced_exposure_pct = args.regime_reduced_exposure_pct
    if args.earnings_blackout_days is not None:
        cfg.earnings_blackout_days = args.earnings_blackout_days
    if args.strategy_mode is not None:
        cfg.strategy_mode = args.strategy_mode
    if args.factor_weights is not None:
        try:
            parts = [float(p.strip()) for p in args.factor_weights.split(",")]
            if len(parts) == 3:
                cfg.factor_weights = {
                    "momentum": parts[0],
                    "quality": parts[1],
                    "low_vol": parts[2]
                }
        except Exception as e:
            logger.warning(f"Could not parse --factor-weights '{args.factor_weights}': {e}")

    results = run_backtest(cfg)

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Wrote JSON output to '{args.json_out}'")


if __name__ == "__main__":
    main()
