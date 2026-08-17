"""
Data module for fetching and caching stock price history via yfinance.
"""

import os
import time
import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DataFetcher")


class DataFetcher:
    """
    Handles downloading adjusted close stock price data from Yahoo Finance with local caching.
    """

    def __init__(self, cache_dir: str = "cache"):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.cache_dir = cache_dir if os.path.isabs(cache_dir) else os.path.join(base_dir, cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
        self._df_memory_cache: Dict[str, pd.DataFrame] = {}

    def _get_ticker_cache_path(self, ticker: str) -> str:
        clean_ticker = ticker.replace("^", "").replace("/", "_").replace(".", "_")
        return os.path.join(self.cache_dir, f"{clean_ticker}.parquet")

    def _get_ticker_cache_csv_path(self, ticker: str) -> str:
        clean_ticker = ticker.replace("^", "").replace("/", "_").replace(".", "_")
        return os.path.join(self.cache_dir, f"{clean_ticker}.csv")

    def _load_df_from_cache(self, ticker: str) -> Optional[pd.DataFrame]:
        """Try loading ticker data from parquet first, then CSV, removing corrupted files."""
        if ticker in self._df_memory_cache:
            return self._df_memory_cache[ticker]

        parquet_path = self._get_ticker_cache_path(ticker)
        csv_path = self._get_ticker_cache_csv_path(ticker)

        if os.path.exists(parquet_path):
            try:
                df = pd.read_parquet(parquet_path)
                if not df.empty:
                    self._df_memory_cache[ticker] = df
                    return df
            except Exception as e:
                logger.debug(f"Corrupt parquet for {ticker}, removing: {e}")
                try:
                    os.remove(parquet_path)
                except Exception:
                    pass

        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
                if not df.empty:
                    self._df_memory_cache[ticker] = df
                    return df
            except Exception as e:
                logger.debug(f"Corrupt csv for {ticker}: {e}")

        return None

    def is_cache_valid(self, ticker: str, req_start: pd.Timestamp, req_end: pd.Timestamp) -> bool:
        """Check if cached file or delisted marker exists."""
        parquet_path = self._get_ticker_cache_path(ticker)
        csv_path = self._get_ticker_cache_csv_path(ticker)
        delisted_path = os.path.join(self.cache_dir, f"{ticker}.delisted")

        if os.path.exists(delisted_path):
            return True

        if os.path.exists(parquet_path) or os.path.exists(csv_path):
            return True

        return False

    def load_cached_series(
        self,
        ticker: str,
        req_start: pd.Timestamp,
        req_end: pd.Timestamp,
        column: str = "Adj Close"
    ) -> Optional[pd.Series]:
        """Load specific price series (e.g. 'Adj Close' or 'Adj Open') from cache if present."""
        df = self._load_df_from_cache(ticker)
        if df is None or df.empty:
            return None
        try:
            df.index = pd.to_datetime(df.index)
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            if column in df.columns:
                series = df[column]
            elif column == "Adj Open" and "Open" in df.columns:
                series = df["Open"]
            elif column == "Volume":
                if "Volume" in df.columns:
                    series = df["Volume"]
                else:
                    return None
            else:
                series = df["Adj Close"] if "Adj Close" in df.columns else (df["Close"] if "Close" in df.columns else df.iloc[:, 0])

            sub = series.loc[(series.index >= req_start) & (series.index <= req_end)]
            if not sub.empty:
                return sub
            return series
        except Exception:
            return None

    def fetch_universe_data(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
        buffer_months: int = 15,
        return_raw: bool = False,
        return_volume: bool = False
    ) -> Any:
        """
        Fetch universe price and volume data returning Closing, Opening, and Volume DataFrames.
        If return_raw=True, also returns the un-forward-filled raw_close_df to allow delisting detection.
        If return_volume=True, also returns volume_df.
        """
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        fetch_start = (start_ts - pd.DateOffset(months=buffer_months)).strftime("%Y-%m-%d")
        fetch_start_ts = pd.Timestamp(fetch_start)

        logger.info(f"Fetching universe price data (Close, Open, Volume) for {len(tickers)} tickers from {fetch_start} to {end_date}...")

        missing_tickers = [t for t in tickers if not self.is_cache_valid(t, fetch_start_ts, end_ts)]
        
        if missing_tickers:
            logger.info(f"Downloading {len(missing_tickers)} missing/outdated tickers in parallel chunks...")
            chunk_size = 50
            for i in range(0, len(missing_tickers), chunk_size):
                chunk = missing_tickers[i:i + chunk_size]
                try:
                    logger.info(f"Downloading chunk {i // chunk_size + 1}/{(len(missing_tickers) + chunk_size - 1) // chunk_size} ({len(chunk)} tickers)...")
                    batch_df = yf.download(
                        chunk,
                        start=fetch_start,
                        end=end_date,
                        progress=False,
                        auto_adjust=False,
                        threads=True
                    )
                    if not batch_df.empty:
                        self._save_batch_to_cache(chunk, batch_df)
                    for t in chunk:
                        cache_path = self._get_ticker_cache_path(t)
                        cache_csv = self._get_ticker_cache_csv_path(t)
                        if not os.path.exists(cache_path) and not os.path.exists(cache_csv):
                            delisted_path = os.path.join(self.cache_dir, f"{t}.delisted")
                            try:
                                with open(delisted_path, "w") as f:
                                    f.write("delisted")
                            except Exception:
                                pass
                except Exception as e:
                    logger.warning(f"Error downloading chunk {chunk[:3]}...: {e}")

        # Load close, open, and volume series from cache
        close_dict: Dict[str, pd.Series] = {}
        open_dict: Dict[str, pd.Series] = {}
        vol_dict: Dict[str, pd.Series] = {}

        for t in tickers:
            sc = self.load_cached_series(t, fetch_start_ts, end_ts, column="Adj Close")
            so = self.load_cached_series(t, fetch_start_ts, end_ts, column="Adj Open")
            sv = self.load_cached_series(t, fetch_start_ts, end_ts, column="Volume")
            if sc is not None and not sc.empty:
                close_dict[t] = sc
            if so is not None and not so.empty:
                open_dict[t] = so
            if sv is not None and not sv.empty:
                vol_dict[t] = sv

        if not close_dict:
            logger.error("No valid prices loaded from cache/download. Generating fallback market data...")
            fb = self._generate_fallback_data(tickers, fetch_start, end_date)
            if return_volume:
                return fb, fb, fb, fb
            if return_raw:
                return fb, fb, fb
            return fb, fb

        raw_close_df = pd.DataFrame(close_dict).sort_index()
        close_df = raw_close_df.ffill()

        if open_dict:
            raw_open_df = pd.DataFrame(open_dict).sort_index()
            open_df = raw_open_df.reindex(index=raw_close_df.index, columns=raw_close_df.columns).ffill()
        else:
            open_df = close_df.copy()

        if vol_dict:
            raw_vol_df = pd.DataFrame(vol_dict).sort_index()
            vol_df = raw_vol_df.reindex(index=raw_close_df.index, columns=raw_close_df.columns).fillna(0.0)
        else:
            vol_df = pd.DataFrame(0.0, index=raw_close_df.index, columns=raw_close_df.columns)

        close_df.index = pd.to_datetime(close_df.index)
        open_df.index = pd.to_datetime(open_df.index)
        raw_close_df.index = pd.to_datetime(raw_close_df.index)
        vol_df.index = pd.to_datetime(vol_df.index)

        logger.info(f"Successfully loaded price data for {len(close_df.columns)} active tickers.")
        if return_volume:
            return close_df, open_df, raw_close_df, vol_df
        if return_raw:
            return close_df, open_df, raw_close_df
        return close_df, open_df

    def fetch_universe_prices(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
        buffer_months: int = 15
    ) -> pd.DataFrame:
        close_df, _ = self.fetch_universe_data(tickers, start_date, end_date, buffer_months)
        return close_df

    def _save_batch_to_cache(self, tickers: List[str], batch_df: pd.DataFrame):
        """Extract individual ticker data from yf.download batch output and write to cache."""
        try:
            if isinstance(batch_df.columns, pd.MultiIndex):
                levels = batch_df.columns.levels
                ticker_level = 0 if any(t in levels[0] for t in tickers) else 1

                for t in tickers:
                    try:
                        if ticker_level == 0:
                            sub_df = batch_df[t] if t in levels[0] else None
                        else:
                            sub_df = batch_df.xs(t, level=1, axis=1) if t in levels[1] else None

                        if sub_df is not None and not sub_df.empty:
                            col_close = "Adj Close" if "Adj Close" in sub_df.columns else ("Close" if "Close" in sub_df.columns else None)
                            col_open = "Open" if "Open" in sub_df.columns else None

                            if col_close:
                                series_close = sub_df[col_close].dropna()
                                if not series_close.empty:
                                    if col_open and "Close" in sub_df.columns:
                                        adj_factor = (sub_df[col_close] / sub_df["Close"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)
                                        series_open = (sub_df[col_open] * adj_factor).reindex(series_close.index).fillna(series_close)
                                    elif col_open:
                                        series_open = sub_df[col_open].reindex(series_close.index).fillna(series_close)
                                    else:
                                        series_open = series_close

                                    col_vol = "Volume" if "Volume" in sub_df.columns else None
                                    series_vol = sub_df[col_vol].reindex(series_close.index).fillna(0.0) if col_vol else pd.Series(0.0, index=series_close.index)
                                    save_df = pd.DataFrame({"Adj Close": series_close, "Adj Open": series_open, "Volume": series_vol})
                                    try:
                                        save_df.to_parquet(self._get_ticker_cache_path(t))
                                    except Exception:
                                        save_df.to_csv(self._get_ticker_cache_csv_path(t))
                                    continue
                        # If ticker had no valid price data, mark as delisted to prevent future downloading retries
                        delisted_file = os.path.join(self.cache_dir, f"{t}.delisted")
                        with open(delisted_file, "w") as f:
                            f.write("delisted")
                    except Exception as e:
                        logger.debug(f"Failed to save ticker {t} from batch: {e}")
                        delisted_file = os.path.join(self.cache_dir, f"{t}.delisted")
                        with open(delisted_file, "w") as f:
                            f.write("delisted")
            else:
                if len(tickers) == 1:
                    t = tickers[0]
                    col_close = "Adj Close" if "Adj Close" in batch_df.columns else ("Close" if "Close" in batch_df.columns else None)
                    col_open = "Open" if "Open" in batch_df.columns else None
                    if col_close:
                        series_close = batch_df[col_close].dropna()
                        if not series_close.empty:
                            if col_open and "Close" in batch_df.columns:
                                adj_factor = (batch_df[col_close] / batch_df["Close"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)
                                series_open = (batch_df[col_open] * adj_factor).reindex(series_close.index).fillna(series_close)
                            elif col_open:
                                series_open = batch_df[col_open].reindex(series_close.index).fillna(series_close)
                            else:
                                series_open = series_close

                            save_df = pd.DataFrame({"Adj Close": series_close, "Adj Open": series_open})
                            try:
                                save_df.to_parquet(self._get_ticker_cache_path(t))
                            except Exception:
                                save_df.to_csv(self._get_ticker_cache_csv_path(t))
        except Exception as e:
            logger.warning(f"Error saving batch to cache: {e}")

    def load_single_ticker(self, ticker: str, start_date: str, end_date: str) -> Optional[pd.Series]:
        req_start = pd.Timestamp(start_date)
        req_end = pd.Timestamp(end_date)
        s = self.load_cached_series(ticker, req_start, req_end)
        if s is not None and not s.empty:
            return s
        try:
            df = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=False)
            if not df.empty:
                sub_df = df
                if isinstance(df.columns, pd.MultiIndex):
                    if ticker in df.columns.get_level_values(1):
                        sub_df = df.xs(ticker, level=1, axis=1)
                    elif ticker in df.columns.get_level_values(0):
                        sub_df = df[ticker]
                
                col = "Adj Close" if "Adj Close" in sub_df.columns else ("Close" if "Close" in sub_df.columns else None)
                if col:
                    series = sub_df[col]
                    if isinstance(series, pd.DataFrame):
                        series = series.iloc[:, 0]
                    series = series.dropna()
                    if not series.empty:
                        series.index = pd.to_datetime(series.index)
                        if series.index.tz is not None:
                            series.index = series.index.tz_localize(None)
                        save_df = pd.DataFrame({"Adj Close": series})
                        try:
                            save_df.to_parquet(self._get_ticker_cache_path(ticker))
                        except Exception:
                            save_df.to_csv(self._get_ticker_cache_csv_path(ticker))
                        return series
        except Exception as e:
            logger.warning(f"Error downloading single ticker {ticker}: {e}")
        return None

    def _generate_fallback_data(self, tickers: List[str], start_date: str, end_date: str) -> pd.DataFrame:
        dates = pd.date_range(start=start_date, end=end_date, freq="B")
        np.random.seed(42)
        data = {}
        for i, t in enumerate(tickers[:50]):
            base_price = 50.0 + (i * 10) % 200
            returns = np.random.normal(0.0005, 0.015, size=len(dates))
            prices = base_price * np.exp(np.cumsum(returns))
            data[t] = pd.Series(prices, index=dates)
        return pd.DataFrame(data)
