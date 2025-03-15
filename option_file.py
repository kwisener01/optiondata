import streamlit as st
import requests
import pandas as pd
import datetime
import time
import matplotlib.pyplot as plt
import pytz  # Timezone conversion

# 🔹 Load API Keys from Streamlit Secrets
ALPACA_API_KEY = st.secrets["ALPACA"]["API_KEY"]
ALPACA_SECRET_KEY = st.secrets["ALPACA"]["SECRET_KEY"]
TRADIER_API_KEY = st.secrets["TRADIER"]["API_KEY"]

# 🔹 API Endpoints
ALPACA_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
TRADIER_URL_OPTIONS = "https://api.tradier.com/v1/markets/options/chains"

# 🔹 Define Date Range
start_date = datetime.datetime(2025, 3, 1)  # Adjust this
end_date = datetime.datetime(2025, 3, 15)  # Adjust this

# Streamlit App Title
st.title("📈 SPY Price & Significant Option Strikes")

# Function to Fetch SPY Data from Alpaca
@st.cache_data
def fetch_spy_data(start, end):
    params = {
        "timeframe": "5Min",
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": 10000  # Max records per request
    }
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
    }
    
    response = requests.get(ALPACA_URL, headers=headers, params=params)

    if response.status_code == 200:
        data = response.json().get("bars", [])
        return pd.DataFrame(data) if data else pd.DataFrame()
    else:
        st.error(f"❌ Error fetching SPY data: {response.text}")
        return pd.DataFrame()

# Fetch SPY Data
spy_df = fetch_spy_data(start_date, end_date)

# Convert and Process SPY Data
if not spy_df.empty:
    spy_df["t"] = pd.to_datetime(spy_df["t"]).dt.tz_convert("US/Eastern")  # Convert to Eastern Time
    spy_df.set_index("t", inplace=True)
    latest_spy_price = spy_df["c"].iloc[-1]  # Last close price
    st.success("✅ SPY Data Retrieved Successfully!")
else:
    st.error("❌ No SPY data retrieved from Alpaca!")

# Fetch Options Data from Tradier
@st.cache_data
def fetch_options_data(expiration_date="2025-03-21"):
    options_params = {"symbol": "SPY", "expiration": expiration_date}
    headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}

    response = requests.get(TRADIER_URL_OPTIONS, headers=headers, params=options_params)

    if response.status_code == 200:
        options_data = response.json()
        if "options" in options_data and "option" in options_data["options"]:
            return pd.DataFrame(options_data["options"]["option"])
    return pd.DataFrame()

options_df = fetch_options_data()

if not options_df.empty:
    st.success(f"✅ Retrieved {len(options_df)} SPY option contracts!")
else:
    st.error("❌ No options data found for this expiration.")

# Filter Option Strikes Near SPY Price (±5%)
filtered_options = options_df[
    ((options_df["strike"] >= latest_spy_price * 0.95) & (options_df["strike"] <= latest_spy_price * 1.05)) &
    ((options_df["open_interest"] > options_df["open_interest"].quantile(0.80)) |
     (options_df["volume"] > options_df["volume"].quantile(0.80)))
]

# Generate Pareto Chart for Significant Strikes
pareto_df = filtered_options.groupby("strike")["open_interest"].sum().reset_index()
pareto_df = pareto_df.sort_values("open_interest", ascending=False).head(5)
significant_strikes = pareto_df["strike"].tolist()  # Extract top 5 strike levels

# Streamlit Plot: Historical SPY Price with Option Strike Levels
st.subheader("📉 SPY Price Chart with Significant Option Strikes")
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(spy_df.index, spy_df["c"], label="SPY 5-Min Close Price", color="black", linewidth=1)

# Overlay Option Strikes as Horizontal Lines
for i, strike in enumerate(significant_strikes):
    ax.axhline(y=strike, linestyle="--", color="red", alpha=0.7, label=f"Strike {strike}" if i == 0 else "")

ax.set_title("SPY Price Over Last Two Weeks with Significant Option Strikes")
ax.set_ylabel("Price")
ax.set_xlabel("Date & Time (ET)")
ax.tick_params(axis='x', rotation=45)
ax.grid(True)
ax.legend()
st.pyplot(fig)

# Streamlit Table: Show Top 5 Strikes
st.subheader("📊 Top 5 Significant Option Strikes")
st.dataframe(pareto_df)


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


