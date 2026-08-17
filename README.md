# Professional Stock Momentum Backtester (Python 3.12)

A modular, high-performance Python 3.12 backtester for academic cross-sectional momentum and factor trading strategies using free Yahoo Finance (`yfinance`) historical adjusted close data.

---

## 🎯 Primary Goal

This backtester is engineered to answer a single critical investment question:

> **"If I had invested $X on DATE using this momentum strategy and rebalanced monthly, what would my portfolio be worth today?"**

---

## 📁 Project Directory Structure

```text
/
├── backtester/
│   ├── main.py          # Backtest orchestrator and CLI entry point
│   ├── config.py        # Configuration variables and parameter defaults
│   ├── strategy.py      # CrossSectionalMomentumStrategy & BaseStrategy interface
│   ├── portfolio.py     # BacktestEngine, execution simulation & trade logs
│   ├── data.py          # yfinance price loader with local Parquet/CSV caching
│   ├── metrics.py       # Performance stats (CAGR, Sharpe, Drawdowns, Volatility)
│   ├── report.py        # Terminal report printer & Matplotlib chart generator
│   ├── utils.py         # Universe CSV reader & rebalance date generator
│   ├── requirements.txt # Python dependencies
│   ├── sp500.csv        # Stock universe ticker file (1 ticker per line)
│   └── cache/           # Local price cache folder
├── server.ts            # Express server for interactive web UI preview
├── src/                 # React frontend dashboard
├── main.py              # Root wrapper script for 'python main.py'
└── README.md            # Documentation
```

---

## 🛠️ Installation

1. Ensure Python 3.10+ or Python 3.12 is installed on your system.
2. Install required dependencies:

```bash
pip install -r backtester/requirements.txt
```

---

## 🚀 How to Run

### 1. Simple Command Line Execution (Default Configuration)

Run from either the root directory or inside `/backtester`:

```bash
python main.py
```

or

```bash
python backtester/main.py
```

### 2. Custom Parameters CLI Execution

Override parameters directly via command-line arguments:

```bash
python main.py \
  --start 2020-01-01 \
  --end 2026-08-04 \
  --capital 30000 \
  --positions 20 \
  --lookback 12 \
  --skip-last True \
  --rebalance-freq monthly \
  --universe sp500.csv \
  --json-out output.json
```

---

## ⚙️ How to Change Strategy Parameters

All default parameters reside in `backtester/config.py`. You can modify `config.py` directly, set environment variables, or pass CLI flags:

| Parameter | Config Name | Default | Description |
| :--- | :--- | :--- | :--- |
| **Start Date** | `START_DATE` | `"2020-01-01"` | Backtest start date (`YYYY-MM-DD`) |
| **End Date** | `END_DATE` | `"2026-08-04"` | Backtest end date (`YYYY-MM-DD`) |
| **Initial Capital** | `INITIAL_CAPITAL` | `30000` | Starting portfolio cash ($) |
| **Top Positions** | `POSITIONS` | `20` | Number of top momentum stocks to hold ($N$) |
| **Lookback Window** | `LOOKBACK_MONTHS` | `12` | Lookback period in months for momentum return |
| **Skip Last Month** | `SKIP_LAST_MONTH` | `True` | Exclude $t-1\text{m}$ to avoid short-term mean reversion |
| **Rebalance Freq** | `REBALANCE_FREQUENCY` | `"monthly"` | Rebalance schedule (`monthly`, `weekly`, `quarterly`) |
| **Universe CSV** | `UNIVERSE_FILE` | `"sp500.csv"` | Ticker list file |

---

## 📊 How to Change the Stock Universe

To test a custom list of stocks:

1. Edit or replace `backtester/sp500.csv` (or create your own CSV file e.g., `tech_tickers.csv`).
2. Add tickers one per line (or under a column header named `Ticker` or `Symbol`):

```csv
Ticker
AAPL
MSFT
NVDA
AMZN
GOOGL
META
TSLA
...
```

3. Run the backtester referencing your new universe file:

```bash
python main.py --universe tech_tickers.csv
```

---

## 🧩 Future Extensibility (Adding New Strategies)

The strategy architecture relies on an abstract base class `BaseStrategy` in `backtester/strategy.py`. To implement a new strategy (e.g. Value, Trend Following, Quality, Multi-Factor) without touching the backtest engine:

1. Open `backtester/strategy.py`.
2. Inherit from `BaseStrategy` and implement `generate_target_weights`:

```python
class MyCustomStrategy(BaseStrategy):
    def generate_target_weights(
        self,
        current_date: pd.Timestamp,
        prices_df: pd.DataFrame
    ) -> Dict[str, float]:
        # Calculate custom signal scores (e.g., trend following / value)
        # Return dictionary mapping ticker -> target weight (e.g. {'AAPL': 0.10})
        return target_weights
```

3. Pass your strategy instance to `BacktestEngine(initial_capital=30000, strategy=MyCustomStrategy())` in `main.py`.

---

## 📈 Generated Outputs & Artifacts

After running a backtest, the following output files are created in the output directory:

1. **`trades.csv`**: Complete trade log history.
   - Columns: `Date`, `Ticker`, `Action` (BUY/SELL), `Price`, `Shares`, `Portfolio Value`
2. **`portfolio.csv`**: Daily equity curve and cash balances.
   - Columns: `Date`, `Portfolio Value`, `Cash`
3. **`equity_curve.png`**: High-resolution chart comparing Portfolio Value vs SPY Benchmark.
4. **`drawdown.png`**: High-resolution underwater drawdown area plot.
