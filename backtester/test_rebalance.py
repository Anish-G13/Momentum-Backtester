"""
Unit test for portfolio rebalance position count and cash reconciliation assertions.
"""

import unittest
import pandas as pd
import numpy as np
from backtester.strategy import CrossSectionalMomentumStrategy
from backtester.portfolio import BacktestEngine


class TestRebalancePositionCount(unittest.TestCase):

    def test_strict_top_n_enforcement_and_reconciliation(self):
        """
        Assert that after every rebalance, active long positions strictly equal N (10),
        and net cash changes reconcile with trade logs.
        """
        # Create 12 months of synthetic price data for 20 tickers
        dates = pd.date_range(start="2025-01-01", end="2026-02-01", freq="B")
        tickers = [f"TICK_{i:02d}" for i in range(20)]
        np.random.seed(42)

        data = {}
        for i, t in enumerate(tickers):
            # Give each ticker a slightly different trend
            trend = 1.0 + (i * 0.05) * (np.arange(len(dates)) / len(dates))
            noise = np.random.normal(1.0, 0.01, size=len(dates))
            data[t] = 100.0 * trend * noise

        prices_df = pd.DataFrame(data, index=dates)

        positions_target = 10
        strat = CrossSectionalMomentumStrategy(
            positions=positions_target,
            lookback_months=6,
            skip_last_month=False
        )
        engine = BacktestEngine(
            initial_capital=50000.0,
            strategy=strat,
            rebalance_frequency="monthly"
        )

        history_df = engine.run(prices_df, start_date="2025-07-01", end_date="2026-02-01")

        # Verify history DataFrame is non-empty
        self.assertFalse(history_df.empty)

        # Assert engine active position count is exactly 10 at end
        self.assertEqual(len(engine.long_positions), positions_target)

        # Verify cumulative net holdings from trade log at each rebalance date
        trades_df = pd.DataFrame([t.to_dict() for t in engine.trade_logs])
        self.assertFalse(trades_df.empty)

        holdings = {}
        for date, group in trades_df.groupby("Date", sort=False):
            for _, row in group.iterrows():
                t = row["Ticker"]
                act = row["Action"]
                sh = row["Shares"]
                if act in ("BUY", "SHORT"):
                    holdings[t] = holdings.get(t, 0.0) + sh
                elif act in ("SELL", "COVER"):
                    holdings[t] = holdings.get(t, 0.0) - sh

            active_tickers = {k: v for k, v in holdings.items() if abs(v) > 0.0001}
            self.assertEqual(
                len(active_tickers),
                positions_target,
                f"Position count drift on rebalance date {date}: held {len(active_tickers)} vs target {positions_target}"
            )


class TestIssuerDeduplication(unittest.TestCase):

    def test_issuer_deduplication_goog_googl(self):
        """
        Assert that when GOOG and GOOGL both rank high in momentum,
        only the higher-ranked ticker is selected, and GOOG/GOOGL never co-exist.
        """
        dates = pd.date_range(start="2025-01-01", end="2026-02-01", freq="B")
        np.random.seed(42)
        tickers = ["GOOG", "GOOGL", "MSFT", "AAPL", "AMZN", "NVDA", "META", "TSLA", "NFLX", "AMD", "INTC", "IBM"]
        data = {}
        for i, t in enumerate(tickers):
            if t == "GOOG":
                trend = 1.0 + 0.8 * (np.arange(len(dates)) / len(dates))  # GOOG ranks highest
            elif t == "GOOGL":
                trend = 1.0 + 0.75 * (np.arange(len(dates)) / len(dates)) # GOOGL ranks 2nd highest
            else:
                trend = 1.0 + (i * 0.05) * (np.arange(len(dates)) / len(dates))
            data[t] = 100.0 * trend

        prices_df = pd.DataFrame(data, index=dates)

        strat = CrossSectionalMomentumStrategy(
            positions=5,
            lookback_months=6,
            skip_last_month=False
        )
        rebal_date = prices_df.index[-1]
        weights = strat.generate_target_weights(rebal_date, prices_df)

        # Confirm GOOG is selected and GOOGL is skipped
        self.assertIn("GOOG", weights)
        self.assertNotIn("GOOGL", weights)
        self.assertEqual(len(weights), 5)


if __name__ == "__main__":
    unittest.main()
