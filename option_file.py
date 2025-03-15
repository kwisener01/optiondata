import streamlit as st
import requests
import pandas as pd
import datetime
import time
import matplotlib.pyplot as plt
import yfinance as yf
import pytz  # Timezone conversion

# 🔹 Load API Keys from Streamlit Secrets
TRADIER_API_KEY = st.secrets["TRADIER"]["API_KEY"]

# 🔹 Tradier API Endpoint for Options
TRADIER_URL_OPTIONS = "https://api.tradier.com/v1/markets/options/chains"

# Streamlit App Title
st.title("📈 SPY Price & Significant Option Strikes")

# User Options: Weekly or Monthly Options
col1, col2 = st.columns(2)

with col1:
    weekly_selected = st.checkbox("Weekly Options", value=True)
with col2:
    monthly_selected = st.checkbox("Monthly Options", value=False)

# Timezone
eastern = pytz.timezone("US/Eastern")

# 🔹 Fetch SPY Data from Yahoo Finance
@st.cache_data
def fetch_spy_data():
    spy_ticker = yf.Ticker("SPY")
    spy_df = spy_ticker.history(period="14d", interval="5m")  # Last 2 weeks, 5-min intervals
    spy_df = spy_df.reset_index()
    spy_df["Datetime"] = spy_df["Datetime"].dt.tz_localize("UTC").dt.tz_convert("US/Eastern")
    return spy_df

# 🔹 Fetch Options Data from Tradier
@st.cache_data
def fetch_options_data(expiration_type):
    """Fetch options based on user selection (weekly or monthly)."""
    if expiration_type == "Weekly":
        expiration_date = "2025-03-21"  # Example: Next Friday
    elif expiration_type == "Monthly":
        expiration_date = "2025-04-19"  # Example: 3rd Friday of the month

    params = {"symbol": "SPY", "expiration": expiration_date}
    headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}

    response = requests.get(TRADIER_URL_OPTIONS, headers=headers, params=params)

    if response.status_code == 200:
        options_data = response.json()
        if "options" in options_data and "option" in options_data["options"]:
            return pd.DataFrame(options_data["options"]["option"]), expiration_date
    st.error(f"Error fetching options data: {response.text}")
    return pd.DataFrame(), None

# 🔹 Fetch SPY Data
spy_df = fetch_spy_data()

# 🔹 Fetch Weekly or Monthly Options Based on Selection
options_dfs = []
expiration_dates = []
if weekly_selected:
    weekly_options_df, weekly_exp_date = fetch_options_data("Weekly")
    if not weekly_options_df.empty:
        options_dfs.append(weekly_options_df)
        expiration_dates.append(weekly_exp_date)
if monthly_selected:
    monthly_options_df, monthly_exp_date = fetch_options_data("Monthly")
    if not monthly_options_df.empty:
        options_dfs.append(monthly_options_df)
        expiration_dates.append(monthly_exp_date)

# 🔹 Validate Data
if spy_df.empty or not options_dfs:
    st.error("No data retrieved. Please try again later.")
    st.stop()

# 🔹 Latest SPY Price
latest_spy_price = spy_df["Close"].iloc[-1]

# 🔹 Combine Options Data
options_df = pd.concat(options_dfs) if options_dfs else pd.DataFrame()

# 🔹 Filter Significant Options Strikes
filtered_options = options_df[
    ((options_df["strike"] >= latest_spy_price * 0.95) & (options_df["strike"] <= latest_spy_price * 1.05)) &
    ((options_df["open_interest"] > options_df["open_interest"].quantile(0.80)) |
     (options_df["volume"] > options_df["volume"].quantile(0.80)))
]

# 🔹 Pareto Chart Data
pareto_df = filtered_options.groupby("strike")["open_interest"].sum().reset_index()
pareto_df = pareto_df.sort_values("open_interest", ascending=False).head(5)
significant_strikes = pareto_df["strike"].tolist()

# 🔹 Plot SPY Price Chart with Significant Option Strikes
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(spy_df["Datetime"], spy_df["Close"], label="SPY 5-Min Close Price", color="black", linewidth=1)

# 🔹 Add Strike Levels
for strike in significant_strikes:
    ax.axhline(y=strike, linestyle="--", color="red", alpha=0.7, label=f"Strike {strike}")

ax.set_title("SPY Price Over Last Two Weeks with Significant Option Strikes")
ax.set_ylabel("Price")
ax.set_xlabel("Date & Time (ET)")
ax.tick_params(axis='x', rotation=45)
ax.legend()
ax.grid(True)

# 🔹 Display in Streamlit
st.pyplot(fig)

# 🔹 Show Top 5 Significant Strikes in a Table
st.subheader("📊 Top 5 Significant Option Strikes")
st.dataframe(pareto_df)
