import streamlit as st
# Import your strategy/engine from the backtester module
# from backtester.portfolio import BacktestEngine

st.title("Momentum Strategy Backtester")

# Add interactive controls
start_date = st.sidebar.date_input("Start Date")
capital = st.sidebar.number_input("Initial Capital", value=30000)

if st.button("Run Backtest"):
    with st.spinner("Running simulation..."):
        # Run your backtest and display results
        st.success("Backtest complete!")
