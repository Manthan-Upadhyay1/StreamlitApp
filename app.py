from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


st.set_page_config(page_title="Supply Chain Delivery Delay Analysis", page_icon="SC", layout="wide")
DATA_FILE = Path(__file__).parent / "data" / "supply_chain_order_fulfillment_delay_risk.csv"
DELAY_COLOR = "#E05252"
ONTIME_COLOR = "#31A66A"
NAVY = "#183153"


@st.cache_data
def load_data(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path, parse_dates=["order_date"])
    data["delay_status"] = data["delayed"].map({1: "Delayed", 0: "On time"})
    data["order_day"] = data["order_date"].dt.floor("D")
    return data


def risk_summary(data: pd.DataFrame, group: str) -> pd.DataFrame:
    return (
        data.groupby(group, as_index=False)
        .agg(orders=("order_id", "size"), delay_rate=("delayed", "mean"), delayed_orders=("delayed", "sum"))
        .sort_values("delay_rate", ascending=False)
    )


def binned_risk(data: pd.DataFrame, field: str, label: str, bins: int = 5) -> pd.DataFrame:
    values = data[field]
    edges = pd.interval_range(start=values.min(), end=values.max(), periods=bins)
    bucket = pd.cut(values, bins=edges, include_lowest=True)
    result = data.assign(bucket=bucket).groupby("bucket", observed=True, as_index=False).agg(
        orders=("order_id", "size"), delay_rate=("delayed", "mean")
    )
    result[label] = result["bucket"].map(lambda x: f"{x.left:,.0f} - {x.right:,.0f}")
    return result


if not DATA_FILE.exists():
    st.error(f"Could not find the dataset at `{DATA_FILE}`.")
    st.stop()

df = load_data(DATA_FILE)

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    .hero { background: linear-gradient(120deg, #183153, #24527a); padding: 1.35rem 1.6rem;
            border-radius: 16px; color: #fff; margin-bottom: 1rem; }
    .hero h1 { margin: 0; font-size: 2rem; }
    .hero p { margin: .35rem 0 0; opacity: .84; }
    [data-testid="stMetric"] { background: #f7f9fc; border: 1px solid #e7edf5; border-radius: 12px; padding: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown("""<div class="hero"><h1>Supply Chain Control Tower</h1><p>Order fulfilment delay risk | 2,800 orders from January to April 2023</p></div>""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Dashboard filters")
    date_min, date_max = df["order_date"].min().date(), df["order_date"].max().date()
    selected_dates = st.date_input("Order date range", value=(date_min, date_max), min_value=date_min, max_value=date_max)
    methods = st.multiselect("Shipping method", sorted(df["shipping_method"].unique()), default=sorted(df["shipping_method"].unique()))
    weather = st.multiselect("Weather condition", sorted(df["weather_condition"].unique()), default=sorted(df["weather_condition"].unique()))
    priorities = st.multiselect("Order priority", sorted(df["order_priority"].unique()), default=sorted(df["order_priority"].unique()))
    st.caption("All charts and KPIs update with these filters.")

filtered = df.copy()
if len(selected_dates) == 2:
    start, end = map(pd.to_datetime, selected_dates)
    filtered = filtered[filtered["order_date"].between(start, end + pd.Timedelta(days=1))]
filtered = filtered[
    filtered["shipping_method"].isin(methods)
    & filtered["weather_condition"].isin(weather)
    & filtered["order_priority"].isin(priorities)
]

if filtered.empty:
    st.warning("No orders match the selected filters. Please widen a filter selection.")
    st.stop()

baseline_delay_rate = df["delayed"].mean()
delay_rate = filtered["delayed"].mean()
metrics = st.columns(5)
metrics[0].metric("Orders in view", f"{len(filtered):,}")
metrics[1].metric("Delayed orders", f"{int(filtered['delayed'].sum()):,}")
metrics[2].metric("Delay rate", f"{delay_rate:.1%}", f"{(delay_rate - baseline_delay_rate):+.1%} vs full dataset")
metrics[3].metric("Avg. processing", f"{filtered['processing_time_hours'].mean():.1f} hrs")
metrics[4].metric("Avg. supplier reliability", f"{filtered['supplier_reliability_score'].mean():.2f}")

overview_tab, driver_tab, explorer_tab = st.tabs(["Executive overview", "Risk drivers", "Order explorer"])

with overview_tab:
    left, right = st.columns((1.3, 1))
    with left:
        st.subheader("Daily delay rate")
        daily = filtered.groupby("order_day", as_index=False).agg(delay_rate=("delayed", "mean"), orders=("order_id", "size"))
        trend = alt.Chart(daily).mark_area(line={"color": DELAY_COLOR}, color=DELAY_COLOR, opacity=0.18).encode(
            x=alt.X("order_day:T", title="Order day"),
            y=alt.Y("delay_rate:Q", title="Delay rate", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, max(0.5, daily.delay_rate.max() * 1.1)])),
            tooltip=[alt.Tooltip("order_day:T", title="Day"), alt.Tooltip("delay_rate:Q", title="Delay rate", format=".1%"), alt.Tooltip("orders:Q", title="Orders")],
        ).properties(height=300)
        st.altair_chart(trend, width="stretch")
    with right:
        st.subheader("Orders by fulfilment outcome")
        outcomes = filtered.groupby("delay_status", as_index=False).agg(orders=("order_id", "size"))
        donut = alt.Chart(outcomes).mark_arc(innerRadius=65).encode(
            theta=alt.Theta("orders:Q"), color=alt.Color("delay_status:N", scale=alt.Scale(domain=["Delayed", "On time"], range=[DELAY_COLOR, ONTIME_COLOR]), legend=alt.Legend(title="Outcome")),
            tooltip=["delay_status:N", alt.Tooltip("orders:Q", format=",")],
        ).properties(height=300)
        st.altair_chart(donut, width="stretch")

    st.subheader("Transport and weather risk matrix")
    matrix = filtered.groupby(["shipping_method", "weather_condition"], as_index=False).agg(orders=("order_id", "size"), delay_rate=("delayed", "mean"))
    heatmap = alt.Chart(matrix).mark_rect(cornerRadius=4).encode(
        x=alt.X("shipping_method:N", title="Shipping method"), y=alt.Y("weather_condition:N", title="Weather condition"),
        color=alt.Color("delay_rate:Q", title="Delay rate", scale=alt.Scale(scheme="yelloworangered"), legend=alt.Legend(format="%")),
        tooltip=["shipping_method:N", "weather_condition:N", alt.Tooltip("orders:Q", format=","), alt.Tooltip("delay_rate:Q", format=".1%")],
    ).properties(height=230)
    labels = alt.Chart(matrix).mark_text(color="#17212b", fontWeight="bold").encode(
        x="shipping_method:N", y="weather_condition:N", text=alt.Text("delay_rate:Q", format=".0%")
    )
    st.altair_chart(heatmap + labels, width="stretch")

with driver_tab:
    left, right = st.columns(2)
    with left:
        st.subheader("Risk by shipping method")
        method_risk = risk_summary(filtered, "shipping_method")
        chart = alt.Chart(method_risk).mark_bar(cornerRadiusEnd=5).encode(
            y=alt.Y("shipping_method:N", sort="-x", title=None), x=alt.X("delay_rate:Q", title="Delay rate", axis=alt.Axis(format="%")),
            color=alt.condition(alt.datum.delay_rate > delay_rate, alt.value(DELAY_COLOR), alt.value("#6B9AC4")),
            tooltip=["shipping_method:N", alt.Tooltip("orders:Q", format=","), alt.Tooltip("delay_rate:Q", format=".1%")],
        ).properties(height=240)
        st.altair_chart(chart, width="stretch")
    with right:
        st.subheader("Risk by weather condition")
        weather_risk = risk_summary(filtered, "weather_condition")
        chart = alt.Chart(weather_risk).mark_bar(cornerRadiusEnd=5).encode(
            y=alt.Y("weather_condition:N", sort="-x", title=None), x=alt.X("delay_rate:Q", title="Delay rate", axis=alt.Axis(format="%")),
            color=alt.condition(alt.datum.delay_rate > delay_rate, alt.value(DELAY_COLOR), alt.value("#6B9AC4")),
            tooltip=["weather_condition:N", alt.Tooltip("orders:Q", format=","), alt.Tooltip("delay_rate:Q", format=".1%")],
        ).properties(height=240)
        st.altair_chart(chart, width="stretch")

    st.subheader("Processing-time risk profile")
    processing_bins = binned_risk(filtered, "processing_time_hours", "Processing time (hrs)")
    processing_chart = alt.Chart(processing_bins).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X("Processing time (hrs):N", sort=None, title="Processing-time band"),
        y=alt.Y("delay_rate:Q", title="Delay rate", axis=alt.Axis(format="%")),
        color=alt.Color("delay_rate:Q", scale=alt.Scale(scheme="orangered"), legend=None),
        tooltip=["Processing time (hrs):N", alt.Tooltip("orders:Q", format=","), alt.Tooltip("delay_rate:Q", format=".1%")],
    ).properties(height=280)
    st.altair_chart(processing_chart, width="stretch")

    st.subheader("Average operating conditions by outcome")
    comparison = filtered.groupby("delay_status", as_index=False).agg(
        processing_time_hours=("processing_time_hours", "mean"),
        supplier_reliability_score=("supplier_reliability_score", "mean"),
        shipping_distance_km=("shipping_distance_km", "mean"),
    ).melt("delay_status", var_name="measure", value_name="value")
    comparison["measure"] = comparison["measure"].map({"processing_time_hours": "Processing time (hrs)", "supplier_reliability_score": "Supplier reliability score", "shipping_distance_km": "Shipping distance (km)"})
    st.dataframe(comparison.pivot(index="measure", columns="delay_status", values="value").round(2), width="stretch")

with explorer_tab:
    st.subheader("Filtered order records")
    display_columns = ["order_id", "order_date", "delay_status", "shipping_method", "weather_condition", "order_priority", "supplier_reliability_score", "warehouse_inventory_level", "order_quantity", "shipping_distance_km", "processing_time_hours"]
    st.dataframe(
        filtered[display_columns].sort_values("order_date", ascending=False), width="stretch", hide_index=True,
        column_config={
            "order_date": st.column_config.DatetimeColumn("Order date", format="D MMM YYYY, HH:mm"),
            "supplier_reliability_score": st.column_config.NumberColumn("Supplier reliability", format="%.2f"),
            "shipping_distance_km": st.column_config.NumberColumn("Shipping distance (km)", format="%.1f"),
            "processing_time_hours": st.column_config.NumberColumn("Processing time (hrs)", format="%.1f"),
        },
    )
    st.download_button("Download filtered data as CSV", filtered.drop(columns=["delay_status", "order_day"]).to_csv(index=False).encode("utf-8"), "filtered_supply_chain_orders.csv", "text/csv")
