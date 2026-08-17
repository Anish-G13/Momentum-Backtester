"""
Utility functions for date parsing, universe loading, and formatting.
"""

import os
import pandas as pd
from typing import List, Optional


_UNIVERSE_CACHE: dict = {}
_REBALANCE_DATES_CACHE: dict = {}


def load_universe(file_path: str, date: Optional[pd.Timestamp] = None) -> List[str]:
    """
    Read stock tickers from a CSV file.
    Supports point-in-time universe selection if date is provided and CSV contains
    DateAdded / DateRemoved date columns.
    
    Args:
        file_path: Path to the universe CSV file.
        date: Optional Timestamp for point-in-time constituent filtering.
        
    Returns:
        List of upper-case ticker symbols active on the given date (or all unique tickers if date is None).
    """
    if not os.path.exists(file_path):
        # Try relative to module directory if not found directly
        base_dir = os.path.dirname(os.path.abspath(__file__))
        alt_path = os.path.join(base_dir, file_path)
        if os.path.exists(alt_path):
            file_path = alt_path
        else:
            raise FileNotFoundError(f"Universe CSV file not found at '{file_path}' or '{alt_path}'")

    abs_path = os.path.abspath(file_path)
    if date is not None:
        target_ts = pd.Timestamp(date).normalize()
        date_str = target_ts.strftime("%Y-%m-%d")
    else:
        target_ts = None
        date_str = None

    cache_key = (abs_path, date_str)
    if cache_key in _UNIVERSE_CACHE:
        return list(_UNIVERSE_CACHE[cache_key])

    tickers: List[str] = []
    
    try:
        df = pd.read_csv(file_path)
        col = [c for c in df.columns if str(c).strip().lower() in ["ticker", "symbol", "code", "stock"]]
        ticker_col = col[0] if col else df.columns[0]
        
        has_added = any(c.lower() in ["dateadded", "startdate", "start_date", "date_added", "added"] for c in df.columns)
        has_removed = any(c.lower() in ["dateremoved", "enddate", "end_date", "date_removed", "removed"] for c in df.columns)
        
        if target_ts is not None and has_added and has_removed:
            added_col = [c for c in df.columns if c.lower() in ["dateadded", "startdate", "start_date", "date_added", "added"]][0]
            removed_col = [c for c in df.columns if c.lower() in ["dateremoved", "enddate", "end_date", "date_removed", "removed"]][0]
            
            df[added_col] = pd.to_datetime(df[added_col], errors='coerce').fillna(pd.Timestamp("1900-01-01"))
            df[removed_col] = pd.to_datetime(df[removed_col], errors='coerce').fillna(pd.Timestamp("9999-12-31"))
            
            mask = (df[added_col] <= target_ts) & (df[removed_col] >= target_ts)
            filtered_df = df[mask]
            raw_tickers = filtered_df[ticker_col].astype(str).tolist()
        else:
            raw_tickers = df[ticker_col].astype(str).tolist()
            
        for t in raw_tickers:
            clean = t.strip().upper()
            if clean and clean not in ["NAN", "TICKER", "SYMBOL", "CODE", "STOCK"] and not clean.startswith("#"):
                clean = clean.replace(".", "-")
                if clean not in tickers:
                    tickers.append(clean)
    except Exception as e:
        try:
            df = pd.read_csv(file_path, header=None)
            raw_tickers = df.iloc[:, 0].astype(str).tolist()
            tickers = [t.strip().upper().replace(".", "-") for t in raw_tickers if t and t != "NAN" and not t.startswith("#")]
        except Exception:
            raise ValueError(f"Error parsing universe CSV file '{file_path}': {e}")
        
    # Remove duplicates while preserving order
    seen = set()
    unique_tickers = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            unique_tickers.append(t)
            
    _UNIVERSE_CACHE[cache_key] = unique_tickers
    return list(unique_tickers)


def get_rebalance_dates(prices_df: pd.DataFrame, frequency: str = "monthly") -> List[pd.Timestamp]:
    """
    Get rebalance dates based on frequency (monthly, weekly, quarterly).
    For weekly frequency:
      - Establishes a fixed anchor weekday from the start date (e.g., Friday).
      - Computes each intended_rebalance_date = anchor_date + 7*n days independently from the fixed anchor.
      - Maps intended_rebalance_date to actual_executed_date on the nearest valid trading day in prices_df.
      - Prevents cumulative drift across weeks, so market holidays shift only the affected week.

    Args:
        prices_df: Price DataFrame with DatetimeIndex.
        frequency: Rebalance frequency ('monthly', 'weekly', 'quarterly').
        
    Returns:
        Sorted list of Timestamps corresponding to actual executed rebalance dates.
    """
    if prices_df.empty:
        return []

    cache_key = (id(prices_df.index), len(prices_df), frequency.lower())
    if cache_key in _REBALANCE_DATES_CACHE:
        return list(_REBALANCE_DATES_CACHE[cache_key])
        
    index = pd.DatetimeIndex(prices_df.index).sort_values()
    start_date = index[0]
    end_date = index[-1]
    
    if frequency.lower() == "weekly":
        # Anchor to first Friday on or after start_date
        anchor_date = start_date + pd.Timedelta(days=(4 - start_date.weekday()) % 7)
        intended_rebalance_dates = pd.date_range(start=anchor_date, end=end_date, freq="7D")
        
        actual_executed_dates = []
        for intended_date in intended_rebalance_dates:
            if intended_date in index:
                actual_executed_dates.append(intended_date)
            else:
                # Fallback to nearest valid trading day on or before intended_date (e.g. Thursday before Friday holiday)
                sub_prev = index[index <= intended_date]
                if not sub_prev.empty:
                    actual_date = sub_prev[-1]
                else:
                    sub_next = index[index >= intended_date]
                    actual_date = sub_next[0] if not sub_next.empty else intended_date
                actual_executed_dates.append(actual_date)
                        
        res = sorted(list(set(actual_executed_dates)))
    elif frequency.lower() == "quarterly":
        # Group by year and quarter, pick last trading day
        actual_executed_dates = index.to_series().groupby([index.year, index.quarter]).max()
        res = sorted(actual_executed_dates.tolist())
    else:
        # Default: monthly - last trading day of each month
        actual_executed_dates = index.to_series().groupby([index.year, index.month]).max()
        res = sorted(actual_executed_dates.tolist())

    # Ensure the backtest start date (first trading day of range) is included as an initial rebalance signal date
    if index[0] not in res:
        res = sorted(list(set([index[0]] + res)))

    _REBALANCE_DATES_CACHE[cache_key] = res
    return list(res)
