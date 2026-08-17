import streamlit as st
import datetime
import pandas as pd
from backtester.portfolio import BacktestEngine
from backtester.strategy import CrossSectionalMomentumStrategy
from backtester.data import DataLoader
from backtester.config import START_DATE, INITIAL_CAPITAL, POSITIONS

st.set_page_config(page_title="Momentum Strategy Backtester", layout="wide")
st.title("📈 Momentum Strategy Backtester")

# Sidebar Configuration Controls
st.sidebar.header("Strategy Parameters")
start_date = st.sidebar.date_input("Start Date", value=datetime.date(2020, 1, 1))
capital = st.sidebar.number_input("Initial Capital ($)", value=30000, step=1000)
positions = st.sidebar.slider("Top Positions (N)", min_value=5, max_value=50, value=20)

if st.button("Run Backtest", type="primary"):
    with st.spinner("Fetching data and running momentum backtest..."):
        try:
            # Initialize Strategy & Engine
            strategy = CrossSectionalMomentumStrategy(n_positions=positions)
            engine = BacktestEngine(
                initial_capital=capital,
                start_date=str(start_date),
                strategy=strategy
            )
            
            # Run simulation
            results = engine.run()
            
            st.success("Backtest completed successfully!")
            
            # Display KPIs
            col1, col2, col3 = st.columns(3)
            col1.metric("Final Value", f"${results.get('final_value', 0):,.2f}")
            col2.metric("CAGR", f"{results.get('cagr', 0):.2%}")
            col3.metric("Sharpe Ratio", f"{results.get('sharpe_ratio', 0):.2f}")

            # Plot Equity Curve
            if "portfolio_history" in results:
                st.subheader("Equity Curve")
                st.line_chart(results["portfolio_history"].set_index("Date")["Portfolio Value"])

        except Exception as e:
            st.error(f"Error running backtest: {e}")
