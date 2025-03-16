import streamlit as st
import requests
import pandas as pd
import datetime
import time
import matplotlib.pyplot as plt
import yfinance as yf
import openai

# 🔹 Load API Keys from Streamlit Secrets
ALPACA_API_KEY = st.secrets["ALPACA"]["API_KEY"]
ALPACA_SECRET_KEY = st.secrets["ALPACA"]["SECRET_KEY"]
TRADIER_API_KEY = st.secrets["TRADIER"]["API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI"]["API_KEY"]

# 🔹 API Endpoints
ALPACA_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
TRADIER_URL_EXPIRATIONS = "https://api.tradier.com/v1/markets/options/expirations"
TRADIER_URL_OPTIONS = "https://api.tradier.com/v1/markets/options/chains"

# 🔹 Set OpenAI API Key
openai.api_key = OPENAI_API_KEY

# Streamlit App Title
st.title("📈 SPY Market Sentiment & Trade Analysis")

# 🔹 User Inputs: Start & End Date Selection for SPY Data
st.sidebar.header("Select SPY Data Range")
start_date = st.sidebar.date_input("Start Date", datetime.date.today() - datetime.timedelta(days=7))
end_date = st.sidebar.date_input("End Date", datetime.date.today())

# 🔹 Fetch Available Expiration Dates from Tradier
@st.cache_data
def fetch_expiration_dates():
    headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}
    response = requests.get(f"{TRADIER_URL_EXPIRATIONS}?symbol=SPY", headers=headers)
    if response.status_code == 200:
        return response.json().get("expirations", {}).get("date", [])
    return []

expiration_dates = fetch_expiration_dates()
selected_expirations = st.sidebar.multiselect("Select Expiration Dates", expiration_dates, default=[expiration_dates[0]])

# 🔹 Fetch SPY Data from Alpaca
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
    st.error("❌ No SPY data retrieved from Alpaca!")

# 🔹 Fetch Options Data from Tradier for Selected Expirations
@st.cache_data
def fetch_options_data(expiration_dates):
    all_options = []
    headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}

    for exp_date in expiration_dates:
        response = requests.get(f"{TRADIER_URL_OPTIONS}?symbol=SPY&expiration={exp_date}", headers=headers)
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
    st.error("❌ No options data found.")

# 🔹 Filter Option Strikes Near SPY Price (±5%)
filtered_options = options_df[
    ((options_df["strike"] >= latest_spy_price * 0.95) & (options_df["strike"] <= latest_spy_price * 1.05)) &
    ((options_df["open_interest"] > options_df["open_interest"].quantile(0.80)) |
     (options_df["volume"] > options_df["volume"].quantile(0.80)))
]

# 🔹 Generate Pareto Chart for Significant Strikes
pareto_df = filtered_options.groupby("strike")["open_interest"].sum().reset_index()
pareto_df = pareto_df.sort_values("open_interest", ascending=False).head(5)
significant_strikes = pareto_df["strike"].tolist()

# 🔹 Fetch VIX & Put/Call Ratio
vix_data = yf.download("^VIX", start=start_date, end=end_date, interval="1d")["Close"]
put_call_ratio = yf.download("^PCCE", start=start_date, end=end_date, interval="1d")["Close"]

sentiment_score = (1 / put_call_ratio) * 100 - vix_data

# 🔹 Calculate Market Sentiment Score
sentiment_score = (1 / put_call_ratio) * 100 - vix_data
latest_sentiment = float(sentiment_score.iloc[-1])  # Ensure it's a numerical value

if latest_sentiment is not None:
    if latest_sentiment > 60:
        sentiment_color = "🟢 Bullish"
    elif 40 <= latest_sentiment <= 60:
        sentiment_color = "🟡 Neutral"
    else:
        sentiment_color = "🔴 Bearish"
    st.sidebar.markdown(f"**Market Sentiment: {sentiment_color} ({latest_sentiment:.2f})**")
else:
    st.sidebar.warning("⚠️ No sentiment data available.")

# 🔹 Plot Historical SPY Price with Option Strikes & Market Sentiment
st.subheader("📉 SPY Price Chart with Significant Option Strikes")
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(spy_df.index, spy_df["c"], label="SPY 5-Min Close Price", color="black", linewidth=1)

# Overlay Significant Strikes
for i, strike in enumerate(significant_strikes):
    ax.axhline(y=strike, linestyle="--", color="red", alpha=0.7, label=f"Strike {strike}" if i == 0 else "")

ax.set_title("SPY Price Over Time with Significant Option Strikes")
ax.set_ylabel("Price")
ax.set_xlabel("Date & Time (ET)")
ax.tick_params(axis='x', rotation=45)
ax.grid(True)
ax.legend()
st.pyplot(fig)

# 🔹 Display Market Sentiment Chart
st.subheader("📊 7-Day Market Sentiment")
fig, ax = plt.subplots(figsize=(12, 5))
ax.plot(sentiment_score, label="Sentiment Score", color="blue")
ax.axhline(y=60, linestyle="--", color="green", alpha=0.5, label="Bullish Threshold")
ax.axhline(y=40, linestyle="--", color="red", alpha=0.5, label="Bearish Threshold")
ax.set_title("Market Sentiment Over the Last 7 Days")
ax.legend()
st.pyplot(fig)

# 🔹 AI Trade Plan Button
if st.button("📜 Generate AI Trade Plan"):
    prompt = f"""
    SPY price is {latest_spy_price}, market sentiment is {latest_sentiment}.
    Option open interest levels suggest key price levels: {significant_strikes}.
    Using this data, provide a simple and actionable trade plan.
    """

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "system", "content": "You are a trading expert providing intuitive trade strategies."},
                  {"role": "user", "content": prompt}]
    )

    trade_plan = response["choices"][0]["message"]["content"]
    st.subheader("📜 AI-Generated Trade Plan")
    st.write(trade_plan)
