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
st.title("📈 SPY Price, VIX, & Significant Option Strikes")

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

# 🔹 **Fetch SPY & VIX Data from Alpaca**
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

# 🔹 **Filter Significant Option Strikes (Top 5)**
significant_options = options_df[
    (options_df["open_interest"] > options_df["open_interest"].quantile(0.80)) |
    (options_df["volume"] > options_df["volume"].quantile(0.80))
]
significant_options = significant_options.groupby("strike")["open_interest"].sum().reset_index()
significant_options = significant_options.sort_values("open_interest", ascending=False).head(5)
top_strikes = significant_options["strike"].tolist()

# 🔹 **SPY & VIX Chart**
st.subheader("📉 SPY Price & VIX Over Time")
fig, ax1 = plt.subplots(figsize=(12, 6))

ax1.plot(spy_df.index, spy_df["c"], label="SPY 5-Min Close Price", color="black", linewidth=1)
ax1.set_ylabel("SPY Price", color="black")
ax1.set_xlabel("Date & Time (ET)")
ax1.tick_params(axis='y', labelcolor="black")

if not vix_df.empty:
    ax2 = ax1.twinx()
    ax2.plot(vix_df.index, vix_df["c"], label="VIX 5-Min Close Price", color="blue", linestyle="dashed")
    ax2.set_ylabel("VIX Price", color="blue")
    ax2.tick_params(axis='y', labelcolor="blue")

ax1.set_title("SPY & VIX Over Selected Period")
ax1.legend(loc="upper left")
ax2.legend(loc="upper right")
st.pyplot(fig)

# Function to Fetch Options Data from Tradier
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
                df["expiration"] = exp_date  # Add expiration date as a column
                all_options.append(df)

    return pd.concat(all_options) if all_options else pd.DataFrame()

# Fetch Options Data
options_df = fetch_options_data(selected_expirations)

if not options_df.empty:
    st.success(f"✅ Retrieved {len(options_df)} SPY option contracts!")
else:
    st.error("❌ No options data found for the selected expirations.")

# Filter Option Strikes Near SPY Price (±5%)
filtered_options = options_df[
    ((options_df["strike"] >= latest_spy_price * 0.95) & (options_df["strike"] <= latest_spy_price * 1.05)) & 
   ((options_df["open_interest"] > options_df["open_interest"].quantile(0.80)) |
     (options_df["volume"] > options_df["volume"].quantile(0.80)))
]

# Generate Pareto Chart for Significant Strikes
pareto_df = filtered_options.groupby(["expiration", "strike"])["open_interest"].sum().reset_index()
pareto_df = pareto_df.sort_values("open_interest", ascending=False).head(5)
significant_strikes = pareto_df["strike"].tolist()

# 📊 **SPY Price Chart with Option Strikes**
st.subheader("📉 SPY Price Chart with Significant Option Strikes")
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(spy_df.index, spy_df["c"], label="SPY 5-Min Close Price", color="black", linewidth=1)

# Overlay Option Strikes as Horizontal Lines
for i, strike in enumerate(significant_strikes):
    ax.axhline(y=strike, linestyle="--", color="red", alpha=0.7, label=f"Strike {strike}")

ax.set_title("SPY Price Over Selected Period with Significant Option Strikes")
ax.set_ylabel("Price")
ax.set_xlabel("Date & Time (ET)")
ax.tick_params(axis='x', rotation=45)
ax.grid(True)
ax.legend()
st.pyplot(fig)

# 📊 **Pareto Chart**
st.subheader("📊 Pareto Chart: Top 5 Option Strikes by Open Interest")
fig, ax = plt.subplots(figsize=(10, 5))
ax.bar(pareto_df["strike"].astype(str), pareto_df["open_interest"], color="blue", alpha=0.7)
ax.set_title("Top 5 Option Strikes by Open Interest")
ax.set_xlabel("Strike Price")
ax.set_ylabel("Open Interest")
ax.grid(axis="y")
st.pyplot(fig)

# Streamlit Table: Show Top 5 Strikes
st.subheader("📋 Top 5 Significant Option Strikes")
st.dataframe(pareto_df)


# 🧠 **AI Trade Plan**
if st.button("🧠 Generate AI Trade Plan"):
    with st.spinner("Generating trade plan..."):
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "system", "content": "You are a professional trading strategist."},
                          {"role": "user", "content": f"Given SPY price {latest_spy_price}, VIX trend, and significant option strikes {top_strikes}, generate a simple trading plan."}]
            )
            st.subheader("📋 AI-Generated Trade Plan")
            st.write(response.choices[0].message.content)
        except Exception as e:
            st.error(f"⚠️ Error generating trade plan: {str(e)}")
