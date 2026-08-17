"""
Reporting and Visualization module.

Generates CSV trade and portfolio logs, renders performance chart PNGs, and prints terminal summaries.
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server/script execution
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from typing import Dict, List, Any, Optional
try:
    from backtester.metrics import calculate_drawdowns
except ImportError:
    from metrics import calculate_drawdowns


def save_trades_csv(trade_logs: List[Any], output_dir: str) -> str:
    """Save trade logs to trades.csv."""
    file_path = os.path.join(output_dir, "trades.csv")
    trade_dicts = [t.to_dict() if hasattr(t, "to_dict") else t for t in trade_logs]
    df = pd.DataFrame(trade_dicts)
    if df.empty:
        df = pd.DataFrame(columns=["Date", "Ticker", "Action", "Price", "Shares", "Portfolio Value"])
    df.to_csv(file_path, index=False)
    return file_path


def save_portfolio_csv(portfolio_history: pd.DataFrame, output_dir: str) -> str:
    """Save portfolio history to portfolio.csv."""
    file_path = os.path.join(output_dir, "portfolio.csv")
    df = portfolio_history.reset_index()
    if "Date" in df.columns:
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    df[["Date", "Portfolio Value", "Cash"]].to_csv(file_path, index=False)
    return file_path


def generate_equity_curve_chart(
    portfolio_history: pd.DataFrame,
    benchmark_history: Optional[pd.DataFrame],
    output_dir: str,
    title: str = "Portfolio Equity Curve vs SPY Benchmark"
) -> str:
    """
    Generate equity_curve.png plot comparing Strategy vs Benchmark.
    """
    file_path = os.path.join(output_dir, "equity_curve.png")

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    
    # Clean dark modern design palette
    ax.set_facecolor("#18181b")
    fig.patch.set_facecolor("#09090b")

    # Plot strategy line
    ax.plot(
        portfolio_history.index,
        portfolio_history["Portfolio Value"],
        label="Momentum Strategy",
        color="#38bdf8",  # Sky blue
        linewidth=2.0
    )

    # Plot SPY benchmark line if present
    if benchmark_history is not None and not benchmark_history.empty:
        ax.plot(
            benchmark_history.index,
            benchmark_history["Portfolio Value"],
            label="SPY Benchmark (Buy & Hold)",
            color="#a1a1aa",  # Muted grey/zinc
            linewidth=1.5,
            linestyle="--"
        )

    ax.set_title(title, color="#f4f4f5", fontsize=14, pad=12, fontweight="bold")
    ax.set_xlabel("Date", color="#a1a1aa", fontsize=10)
    ax.set_ylabel("Portfolio Value ($)", color="#a1a1aa", fontsize=10)

    # Format Y-axis to USD currency ($X,XXX)
    ax.yaxis.set_major_formatter("${x:,.0f}")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    # Style grid and spines
    ax.grid(True, linestyle=":", alpha=0.25, color="#52525b")
    ax.tick_params(colors="#a1a1aa", labelsize=9)
    for spine in ax.spines.values():
        spine.set_color("#3f3f46")

    ax.legend(facecolor="#18181b", edgecolor="#3f3f46", labelcolor="#f4f4f5", loc="upper left")

    plt.tight_layout()
    plt.savefig(file_path, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)

    return file_path


def generate_drawdown_chart(
    portfolio_history: pd.DataFrame,
    output_dir: str,
    title: str = "Portfolio Underwater Drawdown (%)"
) -> str:
    """
    Generate drawdown.png area plot.
    """
    file_path = os.path.join(output_dir, "drawdown.png")

    equity = portfolio_history["Portfolio Value"]
    drawdown, _ = calculate_drawdowns(equity)

    fig, ax = plt.subplots(figsize=(10, 4), dpi=150)

    ax.set_facecolor("#18181b")
    fig.patch.set_facecolor("#09090b")

    # Drawdown area in red/crimson
    ax.fill_between(
        drawdown.index,
        drawdown.values * 100.0,
        0,
        color="#f87171",
        alpha=0.4,
        label="Drawdown %"
    )
    ax.plot(
        drawdown.index,
        drawdown.values * 100.0,
        color="#ef4444",
        linewidth=1.2
    )

    ax.set_title(title, color="#f4f4f5", fontsize=14, pad=12, fontweight="bold")
    ax.set_xlabel("Date", color="#a1a1aa", fontsize=10)
    ax.set_ylabel("Drawdown (%)", color="#a1a1aa", fontsize=10)

    ax.yaxis.set_major_formatter("{x:.1f}%")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    ax.grid(True, linestyle=":", alpha=0.25, color="#52525b")
    ax.tick_params(colors="#a1a1aa", labelsize=9)
    for spine in ax.spines.values():
        spine.set_color("#3f3f46")

    plt.tight_layout()
    plt.savefig(file_path, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)

    return file_path


def print_summary_report(metrics: Dict[str, Any]) -> None:
    """
    Print clean ASCII terminal summary report.
    """
    print("\n" + "=" * 65)
    print("         MOMENTUM STRATEGY BACKTEST PERFORMANCE REPORT        ")
    print("=" * 65)

    print(f"  Starting Capital:            ${metrics.get('Starting Capital', 0):,.2f}")
    print(f"  Ending Capital:              ${metrics.get('Ending Capital', 0):,.2f}")
    print(f"  Total Return:                {metrics.get('Total Return', 0)*100:.2f}%")
    print(f"  Annualized Return (CAGR):    {metrics.get('Annualized Return (CAGR)', 0)*100:.2f}%")
    print(f"  Maximum Drawdown:            {metrics.get('Maximum Drawdown', 0)*100:.2f}%")
    print(f"  Annualized Volatility:       {metrics.get('Volatility', 0)*100:.2f}%")
    print(f"  Sharpe Ratio:                {metrics.get('Sharpe Ratio', 0):.2f}")
    print(f"  Total Trades Executed:       {metrics.get('Number of Trades', 0)}")
    print(f"  Average Holding Period:      {metrics.get('Average Holding Period (Days)', 0):.1f} days")

    if "Benchmark Total Return" in metrics:
        print("-" * 65)
        print("  BENCHMARK COMPARISON (SPY Buy & Hold)")
        print("-" * 65)
        print(f"  SPY Total Return:            {metrics.get('Benchmark Total Return', 0)*100:.2f}%")
        print(f"  SPY Annualized Return (CAGR):{metrics.get('Benchmark CAGR', 0)*100:.2f}%")
        print(f"  SPY Maximum Drawdown:        {metrics.get('Benchmark Max Drawdown', 0)*100:.2f}%")
        print(f"  Alpha (CAGR Spread):         {metrics.get('Alpha vs Benchmark', 0)*100:+.2f}%")

    print("=" * 65 + "\n")


def save_verification_csv(df_verification: pd.DataFrame, output_dir: str) -> str:
    """Save verification breakdown dataframe to verification.csv."""
    file_path = os.path.join(output_dir, "verification.csv")
    df_verification.to_csv(file_path, index=False)
    return file_path


def print_verification_report(df_verification: pd.DataFrame, rebalance_date: str) -> None:
    """
    Print terminal report for verification mode showing top 20 ranked stocks.
    """
    valid_df = df_verification[df_verification["Status"] == "VALID"].copy()
    
    print("\n" + "=" * 96)
    print(f"      REBALANCE VERIFICATION REPORT — REBALANCE DATE: {rebalance_date}")
    print("=" * 96)
    print(f"  Total Stocks Evaluated:      {len(df_verification)}")
    print(f"  Valid Momentum Scores:       {len(valid_df)}")
    print(f"  Skipped / Stale / Missing:   {len(df_verification) - len(valid_df)}")
    print("-" * 96)
    print("  TOP 20 RANKED STOCKS (12-1 Momentum Calculation)")
    print("-" * 96)
    print(f"  {'Rank':<5} {'Ticker':<8} {'Score (%)':<11} {'Selected':<10} {'Start Date':<12} {'Start Price':<12} {'End Date':<12} {'End Price':<12}")
    print("  " + "-" * 94)

    top20 = valid_df.head(20)
    for idx, row in top20.iterrows():
        rank_str = str(int(row["Rank"])) if pd.notna(row.get("Rank")) else "-"
        score_val = row.get("MomentumScore")
        if score_val is None:
            score_val = row.get("CompositeScore")
        if score_val is None:
            score_val = row.get("Raw_Mom")

        if pd.notna(score_val):
            if "CompositeScore" in row and pd.notna(row["CompositeScore"]):
                score_str = f"{score_val:+.4f}"
            else:
                score_str = f"{score_val * 100:+.2f}%"
        else:
            score_str = "N/A"

        selected_str = str(row.get("Selected", "NO"))
        start_dt = str(row.get("Start_Date", "-")) if pd.notna(row.get("Start_Date")) else "-"
        start_px = f"${row['Start_Price']:,.2f}" if pd.notna(row.get("Start_Price")) else "-"
        end_dt = str(row.get("End_Date", "-")) if pd.notna(row.get("End_Date")) else "-"
        end_px = f"${row['End_Price']:,.2f}" if pd.notna(row.get("End_Price")) else "-"

        print(f"  {rank_str:<5} {row['Ticker']:<8} {score_str:<11} {selected_str:<10} {start_dt:<12} {start_px:<12} {end_dt:<12} {end_px:<12}")

    print("=" * 96 + "\n")

