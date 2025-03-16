import streamlit as st
import requests
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import openai  # OpenAI API for trade plan generation
import pytz  # Timezone conversion

# 🔹 Load API Keys from Streamlit Secrets
ALPACA_API_KEY = st.secrets["ALPACA"]["API_KEY"]
ALPACA_SECRET_KEY = st.secrets["ALPACA"]["SECRET_KEY"]
TRADIER_API_KEY = st.secrets["TRADIER"]["API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI"]["API_KEY"]

openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)  # Initialize OpenAI client

# 🔹 API Endpoints
ALPACA_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
ALPACA_VIX_URL = "https://data.alpaca.markets/v2/stocks/VIXY/bars"  # VIXY ETF as a proxy for VIX
TRADIER_URL_EXPIRATIONS = "https://api.tradier.com/v1/markets/options/expirations"
TRADIER_URL_OPTIONS = "https://api.tradier.com/v1/markets/options/chains"

# 🔹 User Input for Date Range
st.sidebar.subheader("📅 Select Date Range")
start_date = st.sidebar.date_input("Start Date", datetime.date(2025, 3, 1))
end_date = st.sidebar.date_input("End Date", datetime.date(2025, 3, 15))

# Streamlit App Title
st.title("📈 SPY Price, VIX, Significant Option Strikes, & Put/Call Ratio")

# 🔹 Fetch Available Expiration Dates
@st.cache_data
def fetch_expiration_dates():
    headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}
    response = requests.get(f"{TRADIER_URL_EXPIRATIONS}?symbol=SPY", headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data.get("expirations", {}).get("date", [])
    else:
        st.error("⚠️ Error fetching expiration dates!")
        return []

expiration_dates = fetch_expiration_dates()

# 📆 **Expiration Date Multi-Select**
selected_expirations = st.sidebar.multiselect("📆 Select Expiration Dates", expiration_dates, default=[expiration_dates[0]])

# 🔹 Fetch SPY & VIX Data from Alpaca
@st.cache_data
def fetch_price_data(url, start, end):
    params = {
        "timeframe": "5Min",
        "start": f"{start}T00:00:00Z",
        "end": f"{end}T23:59:59Z",
        "limit": 10000
    }
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json().get("bars", [])
        return pd.DataFrame(data) if data else pd.DataFrame()
    else:
        st.error(f"❌ Error fetching data from Alpaca: {response.text}")
        return pd.DataFrame()

spy_df = fetch_price_data(ALPACA_URL, start_date, end_date)
vix_df = fetch_price_data(ALPACA_VIX_URL, start_date, end_date)

# Convert and Process Data
if not spy_df.empty:
    spy_df["t"] = pd.to_datetime(spy_df["t"]).dt.tz_convert("US/Eastern")
    spy_df.set_index("t", inplace=True)
    latest_spy_price = spy_df["c"].iloc[-1]
    st.success("✅ SPY Data Retrieved Successfully!")
else:
    st.error("❌ No SPY data retrieved from Alpaca!")

if not vix_df.empty:
    vix_df["t"] = pd.to_datetime(vix_df["t"]).dt.tz_convert("US/Eastern")
    vix_df.set_index("t", inplace=True)
    st.success("✅ VIX Data Retrieved Successfully!")
else:
    st.error("❌ No VIX data retrieved from Alpaca!")

# 🔹 Fetch Options Data
@st.cache_data
def fetch_options_data(expiration_dates):
    all_options = []
    for exp_date in expiration_dates:
        options_params = {"symbol": "SPY", "expiration": exp_date}
        headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}
        response = requests.get(TRADIER_URL_OPTIONS, headers=headers, params=options_params)
        if response.status_code == 200:
            options_data = response.json()
            if "options" in options_data and "option" in options_data["options"]:
                df = pd.DataFrame(options_data["options"]["option"])
                df["expiration"] = exp_date
                all_options.append(df)
    return pd.concat(all_options) if all_options else pd.DataFrame()

options_df = fetch_options_data(selected_expirations)

if not options_df.empty:
    st.success(f"✅ Retrieved {len(options_df)} SPY option contracts!")
else:
    st.error("❌ No options data found for the selected expirations.")

# 🔹 Put/Call Ratio Calculation
put_call_ratio_df = options_df.groupby("expiration").apply(
    lambda x: (x[x["option_type"] == "put"]["volume"].sum() / x[x["option_type"] == "call"]["volume"].sum()) if x[x["option_type"] == "call"]["volume"].sum() > 0 else 0
).reset_index()
put_call_ratio_df.columns = ["Expiration", "Put/Call Ratio"]
put_call_ratio_df = put_call_ratio_df.sort_values("Expiration")

# 📈 Put/Call Ratio Line Chart
st.subheader("📉 Put/Call Ratio Over Time (Next Month Expiration)")
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(put_call_ratio_df["Expiration"], put_call_ratio_df["Put/Call Ratio"], marker='o', linestyle='-', color='purple', label="Put/Call Ratio")
ax.axhline(y=1.5, color='red', linestyle='--', alpha=0.5, label="Bearish Threshold (1.5)")
ax.axhline(y=0.7, color='green', linestyle='--', alpha=0.5, label="Bullish Threshold (0.7)")
ax.axhline(y=2.5, color='darkred', linestyle='--', alpha=0.5, label="Extreme Bearish (2.5)")
ax.set_title("Put/Call Ratio for Selected Expiration")
ax.set_ylabel("Put/Call Ratio")
ax.set_xlabel("Expiration Date")
ax.grid(True)
ax.legend()
st.pyplot(fig)

# 📊 Put/Call Ratio Interpretation Table
st.subheader("📊 Put/Call Ratio Sentiment Guide")
pc_table = pd.DataFrame({
    "Put/Call Ratio": ["> 2.5", "> 1.5", "0.7 - 1.5", "< 0.7"],
    "Market Sentiment": [
        "📉 Extreme Bearish (Potential for Reversal)",
        "⚠️ Bearish Sentiment (Downside Risk)",
        "🟡 Neutral / Mixed Sentiment",
        "🟢 Bullish Sentiment (Upside Potential)"
    ]
})
st.table(pc_table)

# 📉 SPY Price Chart with Significant Option Strikes
st.subheader("📉 SPY Price Chart with Significant Option Strikes")
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(spy_df.index, spy_df["c"], label="SPY 5-Min Close Price", color="black", linewidth=1)
ax.set_title("SPY Price Over Selected Period")
ax.set_ylabel("Price")
ax.set_xlabel("Date & Time (ET)")
ax.tick_params(axis='x', rotation=45)
ax.grid(True)
st.pyplot(fig)
