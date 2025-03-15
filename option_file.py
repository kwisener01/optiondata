import streamlit as st
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime
import time
import pytz

# Load API Keys from Streamlit Secrets
ALPACA_API_KEY = st.secrets["ALPACA"]["API_KEY"]
ALPACA_SECRET_KEY = st.secrets["ALPACA"]["SECRET_KEY"]
TRADIER_API_KEY = st.secrets["TRADIER"]["API_KEY"]

# API Endpoints
ALPACA_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
TRADIER_URL_OPTIONS = "https://api.tradier.com/v1/markets/options/chains"

# Timezone
eastern = pytz.timezone("US/Eastern")

# Function to fetch SPY data from Alpaca
@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_spy_data():
    start_date = (datetime.datetime.now() - datetime.timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_date = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {"timeframe": "5Min", "start": start_date, "end": end_date, "limit": 10000}
    headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY}

    response = requests.get(ALPACA_URL, headers=headers, params=params)

    if response.status_code == 200:
        data = response.json().get("bars", [])
        df = pd.DataFrame(data) if data else pd.DataFrame()
        df["t"] = pd.to_datetime(df["t"]).dt.tz_localize("UTC").dt.tz_convert("US/Eastern")
        return df
    else:
        st.error(f"Error fetching SPY data: {response.text}")
        return pd.DataFrame()

# Function to fetch options data from Tradier
@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_options_data():
    expiration_date = "2025-03-21"
    params = {"symbol": "SPY", "expiration": expiration_date}
    headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}

    response = requests.get(TRADIER_URL_OPTIONS, headers=headers, params=params)

    if response.status_code == 200:
        options_data = response.json()
        if "options" in options_data and "option" in options_data["options"]:
            return pd.DataFrame(options_data["options"]["option"])
    st.error(f"Error fetching options data: {response.text}")
    return pd.DataFrame()

# UI Layout
st.title("SPY Price & Significant Options Strikes")
st.write("This app fetches SPY price data from Alpaca and options data from Tradier.")

# Buttons
col1, col2 = st.columns(2)

with col1:
    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.experimental_rerun()

with col2:
    auto_refresh = st.checkbox("Auto Refresh Every 5 Minutes (Market Hours Only)")

# Fetch Data
spy_df = fetch_spy_data()
options_df = fetch_options_data()

# Validate Data
if spy_df.empty or options_df.empty:
    st.error("No data retrieved. Please try again later.")
    st.stop()

# Latest SPY Price
latest_spy_price = spy_df["c"].iloc[-1]

# Filter Significant Options Strikes
filtered_options = options_df[
    ((options_df["strike"] >= latest_spy_price * 0.95) & (options_df["strike"] <= latest_spy_price * 1.05)) &
    ((options_df["open_interest"] > options_df["open_interest"].quantile(0.80)) |
     (options_df["volume"] > options_df["volume"].quantile(0.80)))
]

# Pareto Chart Data
pareto_df = filtered_options.groupby("strike")["open_interest"].sum().reset_index()
pareto_df = pareto_df.sort_values("open_interest", ascending=False).head(5)
significant_strikes = pareto_df["strike"].tolist()

# Plot SPY Price Chart with Significant Option Strikes
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(spy_df["t"], spy_df["c"], label="SPY 5-Min Close Price", color="black", linewidth=1)

# Add Strike Levels
for strike in significant_strikes:
    ax.axhline(y=strike, linestyle="--", color="red", alpha=0.7, label=f"Strike {strike}")

ax.set_title("SPY Price Over Last Two Weeks with Significant Option Strikes")
ax.set_ylabel("Price")
ax.set_xlabel("Date & Time (ET)")
ax.tick_params(axis='x', rotation=45)
ax.legend()
ax.grid(True)

# Display in Streamlit
st.pyplot(fig)

# Auto Refresh Logic
if auto_refresh:
    current_time = datetime.datetime.now(eastern)
    market_open = current_time.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = current_time.replace(hour=16, minute=0, second=0, microsecond=0)

    if market_open <= current_time <= market_close:
        time.sleep(300)  # Refresh every 5 minutes
        st.experimental_rerun()
