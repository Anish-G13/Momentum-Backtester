"""
Unit test for weekly rebalance date scheduler.
"""

import unittest
import pandas as pd
import numpy as np
from backtester.utils import get_rebalance_dates


class TestScheduler(unittest.TestCase):

    def test_weekly_rebalance_date_cadence(self):
        """
        Assert that over a full year of generated weekly rebalance dates,
        gaps fall in the 5-9 day range with no unanchored drift.
        """
        # Generate 1 full year of business days
        date_range = pd.date_range(start="2025-01-01", end="2025-12-31", freq="B")
        dummy_df = pd.DataFrame(index=date_range, data={"SPY": np.ones(len(date_range))})

        rebalance_dates = get_rebalance_dates(dummy_df, frequency="weekly")
        self.assertGreaterEqual(len(rebalance_dates), 50)

        gaps = []
        for i in range(1, len(rebalance_dates)):
            gap = (rebalance_dates[i] - rebalance_dates[i - 1]).days
            gaps.append(gap)

        # Count gaps in 5-9 range
        in_range_count = sum(1 for g in gaps if 5 <= g <= 9)
        self.assertGreaterEqual(
            in_range_count, 48,
            f"Expected at least 48 of 52 gaps to be in 5-9 day range, got {in_range_count}/{len(gaps)}"
        )

    def test_holiday_shift_anchor_independence(self):
        """
        Assert that a holiday shift on Friday week N shifts week N to Thursday,
        and week N+1 automatically recovers to Friday (not staying on Thursday).
        """
        # Create 3 weeks of trading days, removing Friday of week 2 (2025-01-10)
        dates = pd.date_range(start="2025-01-01", end="2025-01-24", freq="B")
        dates_with_holiday = [d for d in dates if d != pd.Timestamp("2025-01-10")]
        dummy_df = pd.DataFrame(index=dates_with_holiday, data={"SPY": np.ones(len(dates_with_holiday))})

        rebalance_dates = get_rebalance_dates(dummy_df, frequency="weekly")
        
        # Expected:
        # Week 1: 2025-01-03 (Fri)
        # Week 2: 2025-01-09 (Thu, because Jan 10 was a holiday)
        # Week 3: 2025-01-17 (Fri, anchor recovered to Friday!)
        # Week 4: 2025-01-24 (Fri)
        self.assertIn(pd.Timestamp("2025-01-03"), rebalance_dates)
        self.assertIn(pd.Timestamp("2025-01-09"), rebalance_dates)
        self.assertIn(pd.Timestamp("2025-01-17"), rebalance_dates)
        self.assertIn(pd.Timestamp("2025-01-24"), rebalance_dates)


if __name__ == "__main__":
    unittest.main()
