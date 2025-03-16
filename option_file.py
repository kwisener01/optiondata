import streamlit as st
import requests
import pandas as pd
import datetime
import time
import matplotlib.pyplot as plt
import pytz  # Timezone conversion
import openai  # OpenAI API for trade plan generation

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
TRADIER_URL_EXPIRATIONS = "https://api.tradier.com/v1/markets/options/expirations"

# 🔹 Sidebar for Dark Mode Toggle
st.sidebar.title("⚙️ Settings")
dark_mode = st.sidebar.checkbox("🌙 Enable Dark Mode")

# 🔹 Apply Dark Mode CSS
def set_dark_mode():
    dark_css = """
    <style>
        body { background-color: #0E1117; color: white; }
        .stApp { background-color: #0E1117; }
        .stDataFrame { background-color: #1E2127; color: white; }
        .st-bd { color: white; }
        .st-cd { color: white; }
        .stCheckbox label { color: white !important; }
        .stButton>button { background-color: #1F2937; color: white; border-radius: 8px; }
        .stTextInput>div>div>input { background-color: #1F2937; color: white; }
    </style>
    """
    st.markdown(dark_css, unsafe_allow_html=True)

if dark_mode:
    set_dark_mode()

# 🔹 Streamlit App Title
st.title("📈 SPY Price & Significant Option Strikes")

# 🔹 User Selects Start & End Date for SPY Data
start_date = st.date_input("Select SPY Start Date", datetime.date(2025, 3, 1))
end_date = st.date_input("Select SPY End Date", datetime.date(2025, 3, 15))

# 🔹 Fetch Available Expiration Dates
@st.cache_data
def fetch_expiration_dates():
    headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}
    response = requests.get(TRADIER_URL_EXPIRATIONS, headers=headers, params={"symbol": "SPY"})

    if response.status_code == 200:
        data = response.json()
        return data.get("expirations", {}).get("date", [])
    return []

expiration_dates = fetch_expiration_dates()

# Dropdown for Expiration Date Selection
expiration_date = st.selectbox("📅 Select Option Expiration Date", expiration_dates)

# 🔹 Function to Fetch SPY Data from Alpaca
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

# 🔹 Fetch SPY Data
spy_df = fetch_spy_data(pd.to_datetime(start_date), pd.to_datetime(end_date))

# Convert and Process SPY Data
if not spy_df.empty:
    spy_df["t"] = pd.to_datetime(spy_df["t"]).dt.tz_convert("US/Eastern")  # Convert to Eastern Time
    spy_df.set_index("t", inplace=True)
    latest_spy_price = spy_df["c"].iloc[-1]  # Last close price
    st.success("✅ SPY Data Retrieved Successfully!")
else:
    st.error("❌ No SPY data retrieved from Alpaca!")

# 🔹 Fetch Options Data from Tradier
@st.cache_data
def fetch_options_data(expiration_date):
    options_params = {"symbol": "SPY", "expiration": expiration_date}
    headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}

    response = requests.get(TRADIER_URL_OPTIONS, headers=headers, params=options_params)

    if response.status_code == 200:
        options_data = response.json()
        if "options" in options_data and "option" in options_data["options"]:
            return pd.DataFrame(options_data["options"]["option"])
    return pd.DataFrame()

options_df = fetch_options_data(expiration_date)

if not options_df.empty:
    st.success(f"✅ Retrieved {len(options_df)} SPY option contracts for {expiration_date}!")
else:
    st.error("❌ No options data found for this expiration.")

# 🔹 Filter Option Strikes Near SPY Price (±5%)
filtered_options = options_df[
    ((options_df["strike"] >= latest_spy_price * 0.95) & (options_df["strike"] <= latest_spy_price * 1.05)) &
    ((options_df["open_interest"] > options_df["open_interest"].quantile(0.80)) |
     (options_df["volume"] > options_df["volume"].quantile(0.80)))
]

# 🔹 Get Top 5 Strikes by Open Interest & Volume
pareto_df = (
    filtered_options.groupby("strike")[["open_interest", "volume"]].sum()
    .reset_index()
    .sort_values("open_interest", ascending=False)
    .head(5)
)
significant_strikes = pareto_df["strike"].tolist()

# 🔹 Button to Generate OpenAI Trade Plan
if st.button("🧠 Generate Trade Plan with OpenAI"):
    prompt = f"""
    Based on the latest SPY price of {latest_spy_price} and the top significant option strikes: {significant_strikes}, 
    generate a simple and actionable trade plan. Explain what traders should consider, 
    key levels to watch, and possible trade setups.
    """

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "system", "content": "You are a professional trading analyst."},
                  {"role": "user", "content": prompt}]
    )

    trade_plan = response["choices"][0]["message"]["content"]
    st.subheader("📜 Trade Plan")
    st.write(trade_plan)
