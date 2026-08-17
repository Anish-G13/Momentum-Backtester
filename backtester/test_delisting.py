"""
Unit tests for delisted stock handling in BacktestEngine.

Covers:
1. Bankruptcy (write down to $0.00 for long & short positions).
2. Acquisition (realization at buyout/final price).
3. Temporary trading halt (retained at last price, no delisting).
4. Missing Yahoo Finance data (data feed gap retained, no delisting).
5. Prevention of purchasing/shorting delisted securities during rebalances.
"""

import unittest
import pandas as pd
import numpy as np
from typing import Dict

from backtester.portfolio import BacktestEngine, TradeRecord
from backtester.strategy import BaseStrategy


class DummyStrategy(BaseStrategy):
    """Simple strategy returning predefined target weights."""
    def __init__(self, target_weights: Dict[str, float]):
        self.target_weights = target_weights

    def generate_target_weights(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame
    ) -> Dict[str, float]:
        return self.target_weights.copy()


class TestDelistingHandling(unittest.TestCase):

    def setUp(self):
        # Create a 20-day trading calendar
        self.dates = pd.date_range("2025-01-01", periods=20, freq="B")

    def test_bankruptcy_delisting_long_position(self):
        """
        Verify that a stock undergoing bankruptcy (e.g., SIVB, FRC, or $0 final value)
        is immediately realized at $0.00, writing the long position down to $0.
        """
        # BNKR trades normally for days 0..9 at $50, then permanently disappears (NaN) on day 10..19
        close_data = {
            "STABLE": [100.0] * 20,
            "BNKR": [50.0] * 10 + [np.nan] * 10
        }
        raw_df = pd.DataFrame(close_data, index=self.dates)
        prices_df = raw_df.ffill()  # Forward-filled prices as produced by DataFetcher

        strategy = DummyStrategy({"STABLE": 0.5, "BNKR": 0.5})
        engine = BacktestEngine(initial_capital=10000.0, strategy=strategy)
        engine.register_delisting_metadata("BNKR", reason="bankruptcy", final_price=0.0)

        # Rebalance on Day 0 to buy 100 shares of BNKR ($5,000) and 50 shares of STABLE ($5,000)
        engine.execute_rebalance(self.dates[0], prices_df, {"STABLE": 0.5, "BNKR": 0.5}, raw_prices_df=raw_df)
        self.assertIn("BNKR", engine.long_positions)
        self.assertEqual(engine.long_positions["BNKR"], 100.0)

        # On Day 10 (first day of permanent trading stop), process_delistings runs
        processed = engine.process_delistings(self.dates[10], prices_df, raw_prices_df=raw_df)
        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0]["ticker"], "BNKR")
        self.assertEqual(processed[0]["reason"], "bankruptcy")
        self.assertEqual(processed[0]["realized_price"], 0.0)

        # Position must be completely removed from holdings
        self.assertNotIn("BNKR", engine.long_positions)
        self.assertNotIn("BNKR", engine.positions)

        # Value of BNKR should be $0. Proceeds = $0. Cash remains unchanged.
        # Total portfolio value should drop by the $5,000 write-down
        total_val = engine.get_portfolio_value(self.dates[10], prices_df)
        self.assertAlmostEqual(total_val, 5000.0, places=2)

        # Verify trade log has SELL at $0.00
        sell_trades = [t for t in engine.trade_logs if t.ticker == "BNKR" and t.action == "SELL"]
        self.assertEqual(len(sell_trades), 1)
        self.assertEqual(sell_trades[0].price, 0.0)

    def test_bankruptcy_delisting_short_position(self):
        """
        Verify that a short position in a bankrupt stock is covered at $0.00,
        realizing a 100% gain on the short sale.
        """
        close_data = {
            "STABLE": [100.0] * 20,
            "BNKR_SHORT": [50.0] * 10 + [np.nan] * 10
        }
        raw_df = pd.DataFrame(close_data, index=self.dates)
        prices_df = raw_df.ffill()

        strategy = DummyStrategy({"STABLE": 0.5, "BNKR_SHORT": -0.5})
        engine = BacktestEngine(initial_capital=10000.0, strategy=strategy)
        engine.register_delisting_metadata("BNKR_SHORT", reason="bankruptcy", final_price=0.0)

        # Rebalance on Day 0: Short 50 shares of BNKR_SHORT at $50 (Cash +$2500, Liability -$2500)
        engine.execute_rebalance(self.dates[0], prices_df, {"STABLE": 0.5, "BNKR_SHORT": -0.5}, raw_prices_df=raw_df)
        self.assertIn("BNKR_SHORT", engine.short_positions)

        # On Day 10, BNKR_SHORT goes bankrupt
        processed = engine.process_delistings(self.dates[10], prices_df, raw_prices_df=raw_df)
        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0]["realized_price"], 0.0)

        # Short liability is wiped out at $0 cost
        self.assertNotIn("BNKR_SHORT", engine.short_positions)
        cover_trades = [t for t in engine.trade_logs if t.ticker == "BNKR_SHORT" and t.action == "COVER"]
        self.assertEqual(len(cover_trades), 1)
        self.assertEqual(cover_trades[0].price, 0.0)

    def test_acquisition_delisting_long_position(self):
        """
        Verify that an acquired stock (e.g., TWTR, ATVI) is realized at the buyout price / last available price,
        converting shares into cash proceeds.
        """
        # ACQ trades at $80 up to day 9, buyout completes on day 10 at $100.00 buyout price
        close_data = {
            "STABLE": [100.0] * 20,
            "ACQ": [80.0] * 10 + [np.nan] * 10
        }
        raw_df = pd.DataFrame(close_data, index=self.dates)
        prices_df = raw_df.ffill()

        strategy = DummyStrategy({"STABLE": 0.5, "ACQ": 0.5})
        engine = BacktestEngine(initial_capital=10000.0, strategy=strategy)
        engine.register_delisting_metadata("ACQ", reason="acquisition", final_price=100.0)

        # Buy 62.5 shares of ACQ at $80 ($5,000)
        engine.execute_rebalance(self.dates[0], prices_df, {"STABLE": 0.5, "ACQ": 0.5}, raw_prices_df=raw_df)
        self.assertIn("ACQ", engine.long_positions)

        # Day 10: Acquisition realized at $100.00
        cash_before = engine.cash
        processed = engine.process_delistings(self.dates[10], prices_df, raw_prices_df=raw_df)
        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0]["reason"], "acquisition")
        self.assertEqual(processed[0]["realized_price"], 100.0)

        # Position liquidated, proceeds = 62.5 shares * $100 = $6,250 added to cash
        self.assertNotIn("ACQ", engine.long_positions)
        self.assertAlmostEqual(engine.cash, cash_before + 6250.0, places=2)

    def test_temporary_trading_halt_retained(self):
        """
        Verify that a stock subject to a temporary trading halt (missing prices on days 5..7,
        resuming on day 8+) is NOT delisted, and is retained at its last known price.
        """
        close_data = {
            "STABLE": [100.0] * 20,
            "HALT": [50.0] * 5 + [np.nan] * 3 + [60.0] * 12
        }
        raw_df = pd.DataFrame(close_data, index=self.dates)
        prices_df = raw_df.ffill()

        strategy = DummyStrategy({"STABLE": 0.5, "HALT": 0.5})
        engine = BacktestEngine(initial_capital=10000.0, strategy=strategy)

        # Buy HALT on day 0
        engine.execute_rebalance(self.dates[0], prices_df, {"STABLE": 0.5, "HALT": 0.5}, raw_prices_df=raw_df)
        self.assertIn("HALT", engine.long_positions)

        # On day 6 (during the halt), process_delistings MUST NOT delist HALT because future prices exist on day 8+
        processed = engine.process_delistings(self.dates[6], prices_df, raw_prices_df=raw_df)
        self.assertEqual(len(processed), 0)
        self.assertIn("HALT", engine.long_positions)

        # Ticker price should evaluate to last known price ($50.0) during halt
        self.assertEqual(engine.get_ticker_price("HALT", self.dates[6], prices_df), 50.0)

    def test_missing_yahoo_data_feed_gap_retained(self):
        """
        Verify that temporary Yahoo Finance data gaps (e.g. 2 days of missing data mid-series)
        are NOT treated as permanent delistings.
        """
        close_data = {
            "STABLE": [100.0] * 20,
            "GAP": [40.0] * 8 + [np.nan] * 2 + [42.0] * 10
        }
        raw_df = pd.DataFrame(close_data, index=self.dates)
        prices_df = raw_df.ffill()

        strategy = DummyStrategy({"STABLE": 0.5, "GAP": 0.5})
        engine = BacktestEngine(initial_capital=10000.0, strategy=strategy)

        engine.execute_rebalance(self.dates[0], prices_df, {"STABLE": 0.5, "GAP": 0.5}, raw_prices_df=raw_df)

        # On day 8 (during data gap)
        processed = engine.process_delistings(self.dates[8], prices_df, raw_prices_df=raw_df)
        self.assertEqual(len(processed), 0)
        self.assertIn("GAP", engine.long_positions)

    def test_delisting_prevents_new_purchases(self):
        """
        Verify that execute_rebalance refuses to buy a stock that is permanently delisted,
        preserving cash instead of buying phantom shares.
        """
        close_data = {
            "STABLE": [100.0] * 20,
            "DEAD": [50.0] * 5 + [np.nan] * 15
        }
        raw_df = pd.DataFrame(close_data, index=self.dates)
        prices_df = raw_df.ffill()

        strategy = DummyStrategy({"STABLE": 0.5, "DEAD": 0.5})
        engine = BacktestEngine(initial_capital=10000.0, strategy=strategy)

        # On day 10, try to rebalance into DEAD (which permanently stopped trading on day 5)
        engine.execute_rebalance(self.dates[10], prices_df, {"STABLE": 0.5, "DEAD": 0.5}, raw_prices_df=raw_df)

        # DEAD must NOT be bought
        self.assertNotIn("DEAD", engine.long_positions)
        self.assertIn("STABLE", engine.long_positions)


if __name__ == "__main__":
    unittest.main()
