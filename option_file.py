import streamlit as st
import requests
import pandas as pd
import numpy as np
import datetime
import time
import pytz
import matplotlib.pyplot as plt

# Load API Keys from Streamlit Secrets
ALPACA_API_KEY = st.secrets["ALPACA"]["API_KEY"]
ALPACA_SECRET_KEY = st.secrets["ALPACA"]["SECRET_KEY"]
TRADIER_API_KEY = st.secrets["TRADIER"]["API_KEY"]

# API Endpoints
ALPACA_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
TRADIER_URL_OPTIONS = "https://api.tradier.com/v1/markets/options/chains"

# Define function to check if market is open
def is_market_open():
    now = datetime.datetime.now(pytz.timezone("US/Eastern"))
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close

# Function to fetch SPY Data from Alpaca
@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_spy_data():
    start_date = (datetime.datetime.now() - datetime.timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_date = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "timeframe": "5Min",
        "start": start_date,
        "end": end_date,
        "limit": 10000
    }
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
    }

    response = requests.get(ALPACA_URL, headers=headers, params=params)

    if response.status_code == 200:
        data = response.json().get("bars", [])
        df = pd.DataFrame(data)
        df["t"] = pd.to_datetime(df["t"]).dt.tz_convert("US/Eastern")  # Convert to EST
        return df
    else:
        st.error(f"Error fetching SPY data: {response.text}")
        return pd.DataFrame()

# Function to fetch options data from Tradier
@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_options_data(expiration_date="2025-03-21"):
    params = {"symbol": "SPY", "expiration": expiration_date}
    headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}

    response = requests.get(TRADIER_URL_OPTIONS, headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        if "options" in data and "option" in data["options"]:
            return pd.DataFrame(data["options"]["option"])
    st.error(f"Error fetching options data: {response.text}")
    return pd.DataFrame()

# Streamlit UI
st.title("📈 SPY Price & Options Data")

# Buttons for refresh and auto-refresh toggle
refresh = st.button("🔄 Refresh Data")
auto_refresh = st.checkbox("⏳ Auto Refresh Every 5 Minutes (Market Hours Only)", value=True)

# Fetch data
if refresh or (auto_refresh and is_market_open()):
    spy_df = fetch_spy_data()
    options_df = fetch_options_data()

    if not spy_df.empty and not options_df.empty:
        latest_spy_price = spy_df["c"].iloc[-1]

        # Filter options data
        filtered_options = options_df[
            ((options_df["strike"] >= latest_spy_price * 0.95) & (options_df["strike"] <= latest_spy_price * 1.05)) &
            ((options_df["open_interest"] > options_df["open_interest"].quantile(0.80)) |
             (options_df["volume"] > options_df["volume"].quantile(0.80)))
        ]

        # Get top 5 significant strikes
        pareto_df = filtered_options.groupby("strike")["open_interest"].sum().reset_index()
        pareto_df = pareto_df.sort_values("open_interest", ascending=False).head(5)
        significant_strikes = pareto_df["strike"].tolist()

        # Plot SPY Price with Option Strike Levels
        st.subheader("📊 SPY Price with Significant Option Strikes")
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(spy_df["t"], spy_df["c"], label="SPY 5-Min Close Price", color="black", linewidth=1)

        # Overlay option strikes
        for strike in significant_strikes:
            ax.axhline(y=strike, linestyle="--", color="red", alpha=0.7, label=f"Strike {strike}")

        ax.set_title("SPY Price Over Last Two Weeks with Significant Option Strikes")
        ax.set_ylabel("Price")
        ax.set_xlabel("Date & Time (EST)")
        ax.legend()
        ax.grid(True)
        plt.xticks(rotation=45)
        st.pyplot(fig)

        # Show DataTables
        st.subheader("📋 Significant Option Strikes")
        st.dataframe(pareto_df)

        st.subheader("📉 SPY Data (Last 10 Entries)")
        st.dataframe(spy_df.tail(10))

# Auto-refresh logic
if auto_refresh and is_market_open():
    st.experimental_rerun()
