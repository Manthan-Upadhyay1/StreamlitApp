from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Supply Chain Delay Risk", page_icon="ðŸšš", layout="wide")
DATA_FILE = Path(__file__).with_name("supply_chain_order_fulfillment_delay_risk.csv")


@st.cache_data
def load_data(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    data["order_date"] = pd.to_datetime(data["order_date"], errors="coerce")
    data["delay_status"] = data["delayed"].map({1: "Delayed", 0: "On time"})
    return data


if not DATA_FILE.exists():
    st.error(f"Could not find `{DATA_FILE.name}` next to this app.")
    st.stop()

df = load_data(DATA_FILE)
st.title("Supply Chain Order Fulfilment Dashboard")
st.caption("Explore which operational conditions are associated with fulfilment delays.")

with st.sidebar:
    st.header("Filters")
    date_min, date_max = df["order_date"].min().date(), df["order_date"].max().date()
    selected_dates = st.date_input("Order date range", (date_min, date_max), date_min, date_max)
    methods = st.multiselect("Shipping method", sorted(df.shipping_method.dropna().unique()), default=sorted(df.shipping_method.dropna().unique()))
    weather = st.multiselect("Weather condition", sorted(df.weather_condition.dropna().unique()), default=sorted(df.weather_condition.dropna().unique()))
    priorities = st.multiselect("Order priority", sorted(df.order_priority.dropna().unique()), default=sorted(df.order_priority.dropna().unique()))

filtered = df.copy()
if len(selected_dates) == 2:
    start, end = map(pd.to_datetime, selected_dates)
    filtered = filtered[filtered.order_date.between(start, end + pd.Timedelta(days=1))]
filtered = filtered[filtered.shipping_method.isin(methods) & filtered.weather_condition.isin(weather) & filtered.order_priority.isin(priorities)]

if filtered.empty:
    st.warning("No orders match the selected filters. Adjust the filters to see the dashboard.")
    st.stop()

metrics = st.columns(4)
metrics[0].metric("Orders analysed", f"{len(filtered):,}")
metrics[1].metric("Delayed orders", f"{int(filtered.delayed.sum()):,}")
metrics[2].metric("Delay rate", f"{filtered.delayed.mean():.1%}")
metrics[3].metric("Avg. processing time", f"{filtered.processing_time_hours.mean():.1f} hrs")

st.divider()
left, right = st.columns(2)
with left:
    st.subheader("Delay rate by shipping method")
    method_risk = filtered.groupby("shipping_method").delayed.mean().sort_values(ascending=False).to_frame("Delay rate")
    st.bar_chart(method_risk, color="#e85d04", horizontal=True)
with right:
    st.subheader("Delay rate by weather condition")
    weather_risk = filtered.groupby("weather_condition").delayed.mean().sort_values(ascending=False).to_frame("Delay rate")
    st.bar_chart(weather_risk, color="#3a86ff", horizontal=True)

left, right = st.columns(2)
with left:
    st.subheader("Delay trend over time")
    daily_risk = filtered.set_index("order_date").resample("D").delayed.mean().rename("Delay rate").dropna()
    st.line_chart(daily_risk, color="#8338ec")
with right:
    st.subheader("Operational profile by outcome")
    profile = filtered.groupby("delay_status")[["processing_time_hours", "shipping_distance_km", "order_quantity"]].mean()
    profile.columns = ["Processing time (hrs)", "Shipping distance (km)", "Order quantity"]
    st.bar_chart(profile, color=["#2a9d8f", "#e63946", "#457b9d"])

st.subheader("Order-level data")
columns = ["order_id", "order_date", "delay_status", "shipping_method", "weather_condition", "order_priority", "supplier_reliability_score", "warehouse_inventory_level", "order_quantity", "shipping_distance_km", "processing_time_hours"]
st.dataframe(filtered[columns].sort_values("order_date", ascending=False), width="stretch", hide_index=True, column_config={
    "order_date": st.column_config.DatetimeColumn("Order date", format="D MMM YYYY, HH:mm"),
    "supplier_reliability_score": st.column_config.NumberColumn("Supplier reliability", format="%.2f"),
    "shipping_distance_km": st.column_config.NumberColumn("Shipping distance (km)", format="%.1f"),
    "processing_time_hours": st.column_config.NumberColumn("Processing time (hrs)", format="%.1f"),
})
st.download_button("Download filtered data as CSV", filtered.drop(columns="delay_status").to_csv(index=False).encode("utf-8"), "filtered_supply_chain_orders.csv", "text/csv")
