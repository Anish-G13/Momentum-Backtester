import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import pandas as pd
import numpy as np
from backtester.config import Config
from backtester.utils import load_universe
from backtester.data import DataFetcher
from backtester.strategy import CrossSectionalMomentumStrategy

def main():
    config = Config()
    tickers = load_universe(config.universe_file)
    fetcher = DataFetcher(cache_dir=config.cache_dir)
    
    universe_prices, universe_open_prices, raw_universe_prices, universe_volumes = fetcher.fetch_universe_data(
        tickers=tickers,
        start_date="2020-01-01",
        end_date="2026-08-04",
        buffer_months=15,
        return_raw=True,
        return_volume=True
    )

    strat = CrossSectionalMomentumStrategy(
        positions=20,
        lookback_months=12,
        skip_last_month=True,
        universe_file=config.universe_file,
        max_positions_per_sector=3,
        min_avg_dollar_volume=30000000,
        min_market_cap=2000000000,
        ranking_method="risk_adjusted",
        regime_filter=True,
        earnings_blackout_days=5,
        momentum_regime_filter=True,
        momentum_regime_lookback_days=20,
        momentum_regime_threshold=0.0,
        vol_scaling=True,
        vol_scaling_lookback_days=20,
        target_volatility=0.25
    )

    sample_dates = [
        "2026-05-01", "2026-05-15", "2026-06-01", "2026-06-15",
        "2026-07-01", "2026-07-15", "2026-08-01"
    ]

    print("\n==========================================================================================")
    print("      SAMPLE VERIFICATION DATA AROUND JUNE-AUGUST 2026 (TREND-REVERSAL PROTECTION)")
    print("==========================================================================================\n")
    print(f"{'Date':<12} | {'Mom Sleeve 20d Ret':<20} | {'Mom Filter Triggered?':<22} | {'Trailing 20d Realized Vol':<26} | {'Vol Scale':<10}")
    print("-" * 102)

    for d_str in sample_dates:
        available_dates = universe_prices.index[universe_prices.index <= d_str]
        if available_dates.empty:
            continue
        actual_d = available_dates[-1]

        mom_ret = strat.calculate_momentum_sleeve_trailing_return(
            actual_d, universe_prices, volumes_df=universe_volumes, lookback_days=20
        )
        
        # Get selected long tickers for vol calculation
        mom_series = strat.calculate_momentum_returns(actual_d, universe_prices, volumes_df=universe_volumes)
        top_tickers = []
        if not mom_series.empty:
            df_mom = pd.DataFrame({'Momentum': mom_series}).dropna()
            df_mom['Ticker'] = df_mom.index
            df_sorted = df_mom.sort_values(by=['Momentum', 'Ticker'], ascending=[False, True])
            top_tickers = list(df_sorted['Ticker'][:20])

        realized_vol = strat.calculate_realized_volatility(
            actual_d, universe_prices, lookback_days=20, selected_tickers=top_tickers
        )
        
        triggered = (mom_ret is not None and mom_ret < 0.0)
        vol_scale = min(1.0, 0.25 / realized_vol) if realized_vol > 1e-6 else 1.0

        ret_str = f"{mom_ret*100:+.2f}%" if mom_ret is not None else "N/A"
        vol_str = f"{realized_vol*100:.2f}%"
        trig_str = "YES (FILTER ACTIVE)" if triggered else "NO"
        
        print(f"{actual_d.strftime('%Y-%m-%d'):<12} | {ret_str:<20} | {trig_str:<22} | {vol_str:<26} | {vol_scale*100:.1f}%")

if __name__ == "__main__":
    main()
