import streamlit as st
import requests
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import openai  # OpenAI API for trade plan generation
import yfinance as yf  # Fetch VIX & Put/Call Ratio
import pytz  # Timezone conversion

# 🔹 Load API Keys from Streamlit Secrets
ALPACA_API_KEY = st.secrets["ALPACA"]["API_KEY"]
ALPACA_SECRET_KEY = st.secrets["ALPACA"]["SECRET_KEY"]
TRADIER_API_KEY = st.secrets["TRADIER"]["API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI"]["API_KEY"]

openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)  # Initialize OpenAI client

# 🔹 API Endpoints
ALPACA_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
TRADIER_URL_EXPIRATIONS = "https://api.tradier.com/v1/markets/options/expirations"
TRADIER_URL_OPTIONS = "https://api.tradier.com/v1/markets/options/chains"

# 🔹 User Input for Date Range
st.sidebar.subheader("📅 Select Date Range")
start_date = st.sidebar.date_input("Start Date", datetime.date(2025, 3, 1))
end_date = st.sidebar.date_input("End Date", datetime.date(2025, 3, 15))

# Streamlit App Title
st.title("📈 SPY Price, Options, & Market Sentiment")

# Function to Fetch Available Expiration Dates
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

# Fetch Expiration Dates
expiration_dates = fetch_expiration_dates()

# Expiration Date Multi-Select Dropdown
selected_expirations = st.sidebar.multiselect("📆 Select Expiration Dates", expiration_dates, default=[expiration_dates[0]])

# Function to Fetch SPY Data from Alpaca
@st.cache_data
def fetch_spy_data(start, end):
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
    spy_df["t"] = pd.to_datetime(spy_df["t"]).dt.tz_convert("US/Eastern")
    spy_df.set_index("t", inplace=True)
    latest_spy_price = spy_df["c"].iloc[-1]
    st.success("✅ SPY Data Retrieved Successfully!")
else:
    st.error("❌ No SPY data retrieved from Alpaca!")

# Function to Fetch VIX & Put/Call Ratio from Yahoo Finance
@st.cache_data
def fetch_market_sentiment():
    vix = yf.download("^VIX", period="7d", interval="1d")["Close"]
    put_call = yf.download("^PCCE", period="7d", interval="1d")["Close"]  # CBOE Equity Put/Call Ratio
    
    sentiment_df = pd.DataFrame({
        "Date": vix.index,
        "VIX": vix.values,
        "Put/Call Ratio": put_call.values
    }).dropna()
    
    # Compute Sentiment Score (Lower VIX & Put/Call → More Bullish)
    sentiment_df["Sentiment Score"] = 100 - ((sentiment_df["VIX"] * 2) + (sentiment_df["Put/Call Ratio"] * 100))
    return sentiment_df

# Fetch Market Sentiment Data
sentiment_df = fetch_market_sentiment()

# Determine Latest Sentiment Score
if not sentiment_df.empty:
    latest_sentiment = sentiment_df["Sentiment Score"].iloc[-1]
    
    # Color Code Sentiment
    if latest_sentiment > 60:
        sentiment_label = "🟢 Bullish"
    elif latest_sentiment > 40:
        sentiment_label = "🟡 Neutral"
    else:
        sentiment_label = "🔴 Bearish"

    st.subheader("📊 Market Sentiment Score")
    st.metric(label="Market Sentiment", value=f"{latest_sentiment:.1f}", delta=sentiment_label)

    # Plot Sentiment Over Time
    st.subheader("📈 7-Day Market Sentiment Trend")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(sentiment_df["Date"], sentiment_df["Sentiment Score"], marker="o", linestyle="-", color="black")
    ax.set_title("Market Sentiment (Last 7 Days)")
    ax.set_ylabel("Sentiment Score")
    ax.grid(True)
    st.pyplot(fig)

# 🧠 **Trade Plan with Market Sentiment**
if st.button("🧠 Generate AI Trade Plan"):
    with st.spinner("Generating trade plan..."):
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a professional trading strategist."},
                    {"role": "user", "content": f"Given SPY price {latest_spy_price}, significant option strikes {selected_expirations}, and market sentiment {sentiment_label} (score: {latest_sentiment:.1f}), generate a simple trading plan that is easy to follow."}
                ]
            )
            trade_plan = response.choices[0].message.content
            st.success("✅ Trade Plan Generated!")
            st.subheader("📋 AI-Generated Trade Plan")
            st.write(trade_plan)
        except Exception as e:
            st.error(f"⚠️ Error generating trade plan: {str(e)}")
