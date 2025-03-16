import streamlit as st
import requests
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import pytz  # Timezone conversion

# 🔹 Load API Keys from Streamlit Secrets
ALPACA_API_KEY = st.secrets["ALPACA"]["API_KEY"]
ALPACA_SECRET_KEY = st.secrets["ALPACA"]["SECRET_KEY"]
TRADIER_API_KEY = st.secrets["TRADIER"]["API_KEY"]

# 🔹 API Endpoints
ALPACA_URL = "https://data.alpaca.markets/v2/stocks/SPY/bars"
TRADIER_URL_EXPIRATIONS = "https://api.tradier.com/v1/markets/options/expirations"
TRADIER_URL_OPTIONS = "https://api.tradier.com/v1/markets/options/chains"

# **Streamlit App Title**
st.title("📈 SPY Price, Option Strikes & Gamma")

# **Step 1: Fetch Expiration Dates**
@st.cache_data
def fetch_expiration_dates():
    params = {"symbol": "SPY"}
    headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}
    response = requests.get(TRADIER_URL_EXPIRATIONS, headers=headers, params=params)
    
    if response.status_code == 200:
        return response.json().get("expirations", {}).get("date", [])
    else:
        st.error(f"❌ Error fetching expiration dates: {response.text}")
        return []

expiration_dates = fetch_expiration_dates()
selected_expiration = st.selectbox("📅 Select Expiration Date", expiration_dates)

# **Step 2: User selects SPY Start & End Dates**
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("📆 Select Start Date", datetime.date.today() - datetime.timedelta(days=14))
with col2:
    end_date = st.date_input("📆 Select End Date", datetime.date.today())

start_date = datetime.datetime.combine(start_date, datetime.time(0, 0))
end_date = datetime.datetime.combine(end_date, datetime.time(23, 59))

# **Step 3: Fetch SPY Data**
@st.cache_data
def fetch_spy_data(start, end):
    params = {"timeframe": "5Min", "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 10000}
    headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY}
    
    response = requests.get(ALPACA_URL, headers=headers, params=params)

    if response.status_code == 200:
        return pd.DataFrame(response.json().get("bars", []))
    else:
        st.error(f"❌ Error fetching SPY data: {response.text}")
        return pd.DataFrame()

spy_df = fetch_spy_data(start_date, end_date)

if not spy_df.empty:
    spy_df["t"] = pd.to_datetime(spy_df["t"]).dt.tz_convert("US/Eastern")  # Convert to ET
    spy_df.set_index("t", inplace=True)
    latest_spy_price = spy_df["c"].iloc[-1]  # Last close price
    st.success("✅ SPY Data Retrieved Successfully!")
else:
    st.error("❌ No SPY data retrieved from Alpaca!")

# **Step 4: Fetch Options Data with Greeks (Gamma)**
@st.cache_data
def fetch_options_data(expiration_date):
    if not expiration_date:
        return pd.DataFrame()

    options_params = {"symbol": "SPY", "expiration": expiration_date, "greeks": "true"}
    headers = {"Authorization": f"Bearer {TRADIER_API_KEY}", "Accept": "application/json"}

    response = requests.get(TRADIER_URL_OPTIONS, headers=headers, params=options_params)

    if response.status_code == 200:
        options_data = response.json()
        if "options" in options_data and "option" in options_data["options"]:
            return pd.DataFrame(options_data["options"]["option"])
    return pd.DataFrame()

options_df = fetch_options_data(selected_expiration)

if not options_df.empty:
    st.success(f"✅ Retrieved {len(options_df)} SPY option contracts for {selected_expiration}!")
else:
    st.error("❌ No options data found for this expiration.")

# **Step 5: Check for "Gamma" Column & Handle Errors**
if "gamma" in options_df.columns:
    filtered_options = options_df[
        ((options_df["strike"] >= latest_spy_price * 0.95) & (options_df["strike"] <= latest_spy_price * 1.05)) &
        ((options_df["open_interest"] > options_df["open_interest"].quantile(0.80)) |
         (options_df["volume"] > options_df["volume"].quantile(0.80)))
    ]

    # Extract Gamma Values
    gamma_df = filtered_options[["strike", "gamma"]].dropna().sort_values("gamma", ascending=False).head(5)
    significant_strikes = gamma_df["strike"].tolist()  # Extract top 5 strike levels
    strike_labels = [f"Strike {s}: Gamma {g:.4f}" for s, g in zip(gamma_df["strike"], gamma_df["gamma"])]

    # **Step 6: Plot SPY Price with Significant Strikes & Gamma**
    st.subheader("📉 SPY Price Chart with Option Strikes & Gamma Levels")
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(spy_df.index, spy_df["c"], label="SPY 5-Min Close Price", color="black", linewidth=1)

    # Overlay Gamma Levels on the Chart
    for i, (strike, label) in enumerate(zip(significant_strikes, strike_labels)):
        ax.axhline(y=strike, linestyle="--", color="red", alpha=0.7, label=label)

    ax.set_title(f"SPY Price ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}) with Significant Gamma Levels ({selected_expiration})")
    ax.set_ylabel("Price")
    ax.set_xlabel("Date & Time (ET)")
    ax.tick_params(axis='x', rotation=45)
    ax.grid(True)
    ax.legend()
    st.pyplot(fig)

    # **Step 7: Display Top 5 Gamma Strikes**
    st.subheader("📊 Top 5 Option Strikes with Highest Gamma")
    st.dataframe(gamma_df)

else:
    st.warning("⚠️ 'Gamma' data not available in API response. Please check Tradier API permissions or data provider.")
