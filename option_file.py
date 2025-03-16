import streamlit as st
import requests
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import openai
import pytz  # Timezone conversion

# 🔹 Load API Keys from Streamlit Secrets
ALPACA_API_KEY = st.secrets["ALPACA"]["API_KEY"]
ALPACA_SECRET_KEY = st.secrets["ALPACA"]["SECRET_KEY"]
TRADIER_API_KEY = st.secrets["TRADIER"]["API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI"]["API_KEY"]

openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)  # Initialize OpenAI client

# 🔹 API Endpoints
TRADIER_URL_EXPIRATIONS = "https://api.tradier.com/v1/markets/options/expirations"
TRADIER_URL_OPTIONS = "https://api.tradier.com/v1/markets/options/chains"

# 📌 **Dark Mode Option**
dark_mode = st.sidebar.checkbox("🌙 Enable Dark Mode")

if dark_mode:
    st.markdown("""
        <style>
            body { background-color: #121212; color: #FFFFFF; }
            .stDataFrame { background-color: #1E1E1E; color: #FFFFFF; }
        </style>
    """, unsafe_allow_html=True)

# 📅 **User Input for Date Range**
st.sidebar.subheader("📅 Select Date Range")
start_date = st.sidebar.date_input("Start Date", datetime.date(2025, 3, 1))
end_date = st.sidebar.date_input("End Date", datetime.date(2025, 3, 15))

# 📈 **App Title**
st.title("📈 SPY Market Data & Options Sentiment")

# 🔹 **Fetch Available Expiration Dates**
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

# 🔹 **Fetch SPY Price Data**
@st.cache_data
def fetch_spy_data(start, end):
    ALPACA_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
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

spy_df = fetch_spy_data(start_date, end_date)

if not spy_df.empty:
    spy_df["t"] = pd.to_datetime(spy_df["t"]).dt.tz_convert("US/Eastern")
    spy_df.set_index("t", inplace=True)
    latest_spy_price = spy_df["c"].iloc[-1]
    st.success("✅ SPY Data Retrieved Successfully!")
else:
    st.error("❌ No SPY data retrieved from Alpaca!")

# 🔹 **Fetch Options Data**
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

# 🔹 **Filter Significant Option Strikes**
significant_options = options_df[
    (options_df["open_interest"] > options_df["open_interest"].quantile(0.80)) |
    (options_df["volume"] > options_df["volume"].quantile(0.80))
]

# 🔹 **Calculate Put/Call Ratio by Strike (Only Strikes > 0)**
if not significant_options.empty:
    calls = significant_options[significant_options["option_type"] == "call"]
    puts = significant_options[significant_options["option_type"] == "put"]

    call_oi = calls.groupby("strike")["open_interest"].sum()
    put_oi = puts.groupby("strike")["open_interest"].sum()

    put_call_df = pd.DataFrame({"Call OI": call_oi, "Put OI": put_oi}).fillna(0)
    put_call_df["Put/Call Ratio"] = put_call_df["Put OI"] / put_call_df["Call OI"]
    put_call_df = put_call_df[put_call_df["Put/Call Ratio"] > 0]  # Filter out zeros
    put_call_df = put_call_df.sort_index()

    st.subheader("📊 Put/Call Ratio by Strike Price")
    st.dataframe(put_call_df)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(put_call_df.index, put_call_df["Put/Call Ratio"], marker="o", linestyle="-", color="black")
    ax.axhline(y=1, color="red", linestyle="--", label="Neutral Level (1.0)")
    ax.set_title("Put/Call Ratio by Strike Price")
    ax.set_ylabel("Put/Call Ratio")
    ax.set_xlabel("Strike Price")
    ax.grid(True)
    ax.legend()
    st.pyplot(fig)
else:
    st.warning("⚠️ No significant option data available.")

# 🔹 **SPY Price Chart with Significant Option Strikes**
st.subheader("📉 SPY Price with Significant Option Strikes")
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(spy_df.index, spy_df["c"], label="SPY 5-Min Close Price", color="black", linewidth=1)

for strike in put_call_df.index:
    ax.axhline(y=strike, linestyle="--", color="red", alpha=0.7, label=f"Strike {strike}")

ax.set_title("SPY Price with Significant Option Strikes")
ax.set_ylabel("Price")
ax.set_xlabel("Date & Time (ET)")
ax.grid(True)
ax.legend()
st.pyplot(fig)

# 🔹 **AI-Generated Trade Plan**
if st.button("🧠 Generate AI Trade Plan"):
    with st.spinner("Generating trade plan..."):
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a professional trading strategist."},
                    {"role": "user", "content": f"Given SPY's price and significant option strikes, with Put/Call ratios: {put_call_df.to_dict()}, generate a simple trading plan that is easy to follow."}
                ]
            )
            trade_plan = response.choices[0].message.content
            st.success("✅ Trade Plan Generated!")
            st.subheader("📋 AI-Generated Trade Plan")
            st.write(trade_plan)
        except Exception as e:
            st.error(f"⚠️ Error generating trade plan: {str(e)}")
