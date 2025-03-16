import streamlit as st
import requests
import pandas as pd
import datetime
import time
import matplotlib.pyplot as plt
import pytz  # Timezone conversion
import yfinance as yf
import openai

# 🔹 Load API Keys from Streamlit Secrets
ALPACA_API_KEY = st.secrets["ALPACA"]["API_KEY"]
ALPACA_SECRET_KEY = st.secrets["ALPACA"]["SECRET_KEY"]
TRADIER_API_KEY = st.secrets["TRADIER"]["API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI"]["API_KEY"]

# Set OpenAI API Key
openai.api_key = OPENAI_API_KEY

# 🔹 API Endpoints
ALPACA_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
TRADIER_URL_OPTIONS = "https://api.tradier.com/v1/markets/options/chains"

# Streamlit App Title
st.title("📈 SPY Market Sentiment & Trade Plan")

# User selects start & end dates for SPY data
start_date = st.date_input("Select Start Date", datetime.date(2025, 3, 1))
end_date = st.date_input("Select End Date", datetime.date(2025, 3, 15))

# User selects expiration dates (multi-select dropdown)
selected_expirations = st.multiselect("Select Option Expiration Dates", ["2025-03-21", "2025-03-28", "2025-04-05"])

# Fetch SPY Data from Alpaca
@st.cache_data
def fetch_spy_data(start, end):
    params = {
        "timeframe": "5Min",
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": 10000
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

spy_df = fetch_spy_data(start_date, end_date)
if not spy_df.empty:
    spy_df["t"] = pd.to_datetime(spy_df["t"]).dt.tz_convert("US/Eastern")
    spy_df.set_index("t", inplace=True)
    latest_spy_price = spy_df["c"].iloc[-1]
    st.success("✅ SPY Data Retrieved Successfully!")
else:
    st.error("❌ No SPY data retrieved!")

# Fetch Options Data
@st.cache_data
def fetch_options_data(expirations):
    all_options = []
    for exp_date in expirations:
        options_params = {"symbol": "SPY", "expiration": exp_date}
        headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}
        response = requests.get(TRADIER_URL_OPTIONS, headers=headers, params=options_params)
        if response.status_code == 200:
            options_data = response.json()
            if "options" in options_data and "option" in options_data["options"]:
                all_options.append(pd.DataFrame(options_data["options"]["option"]))
    return pd.concat(all_options) if all_options else pd.DataFrame()

options_df = fetch_options_data(selected_expirations)

# Fetch VIX & Put/Call Ratio
vix_data = yf.download("^VIX", start=start_date, end=end_date, interval="1d")
pcr_data = yf.download("^PCRATIO", start=start_date, end=end_date, interval="1d")

# Compute Sentiment Score
sentiment_scores = []
for date in vix_data.index:
    vix = vix_data.loc[date, "Close"]
    pcr = pcr_data.loc[date, "Close"] if date in pcr_data.index else 0.85  # Default neutral PCR
    vix_score = max(0, 100 - (vix - 18) * 5)
    pcr_score = max(0, 100 - (pcr - 0.7) * 100)
    sentiment_scores.append((date, (vix_score + pcr_score) / 2))

sentiment_df = pd.DataFrame(sentiment_scores, columns=["Date", "Sentiment Score"])

# Plot Sentiment Score
st.subheader("📉 7-Day Market Sentiment Trend")
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(sentiment_df["Date"], sentiment_df["Sentiment Score"], marker="o", linestyle="-", color="blue")
ax.axhline(y=60, color="green", linestyle="--", label="Bullish")
ax.axhline(y=40, color="yellow", linestyle="--", label="Neutral")
ax.axhline(y=20, color="red", linestyle="--", label="Bearish")
ax.set_ylabel("Sentiment Score (0-100)")
ax.set_title("Market Sentiment Over Last 7 Days")
ax.legend()
st.pyplot(fig)

# Generate AI Trade Plan
if st.button("Generate AI Trade Plan"):
prompt = f"""
SPY price is {latest_spy_price}, market sentiment is {sentiment_df.iloc[-1]['Sentiment Score']}.
Using the sentiment data and option open interest levels, suggest a trade plan that is easy to follow.
"""
    Based on significant options and sentiment, generate an easy-to-follow trade plan."
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "system", "content": "You are an expert trading assistant."},
                  {"role": "user", "content": prompt}]
    )
    trade_plan = response["choices"][0]["message"]["content"]
    st.subheader("📋 AI-Generated Trade Plan")
    st.write(trade_plan)
