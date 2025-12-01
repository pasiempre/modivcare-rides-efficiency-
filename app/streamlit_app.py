"""Streamlit dashboard for NEMT Rides Efficiency Analysis."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from datetime import datetime, timedelta
import sys
import io

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import PROCESSED_DIR, RAW_DIR


# Page config
st.set_page_config(
    page_title="NEMT Rides Efficiency Dashboard",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for better styling (works in both light and dark mode)
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 15px;
        margin: 5px;
    }
    /* Metric cards: use semi-transparent background that adapts to theme */
    [data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.1);
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    /* Ensure metric labels are visible */
    [data-testid="stMetricLabel"] {
        color: inherit !important;
    }
    /* Ensure metric values are visible */
    [data-testid="stMetricValue"] {
        color: inherit !important;
    }
    .insight-box {
        background-color: #e8f4f8;
        border-left: 4px solid #1f77b4;
        padding: 10px;
        margin: 10px 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 10px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

st.title("🚗 NEMT Rides Efficiency Dashboard")
st.markdown("Analyze ride efficiency, identify bottlenecks, and compare routing strategies.")


@st.cache_data
def load_data():
    """Load processed data files with proper datetime parsing."""
    try:
        trips = pd.read_csv(
            PROCESSED_DIR / "trips_with_efficiency.csv",
            parse_dates=[
                "requested_pickup_time",
                "scheduled_pickup_time",
                "actual_pickup_time",
                "actual_dropoff_time",
            ],
        )
        drivers = pd.read_csv(PROCESSED_DIR / "drivers.csv")
        simulations = pd.read_csv(PROCESSED_DIR / "simulation_results.csv")
        
        # Load additional datasets if available
        evaluation = None
        sensitivity = None
        try:
            evaluation = pd.read_csv(PROCESSED_DIR / "evaluation_summary.csv")
        except FileNotFoundError:
            pass
        try:
            sensitivity = pd.read_csv(PROCESSED_DIR / "sensitivity_analysis.csv")
        except FileNotFoundError:
            pass
            
        return trips, drivers, simulations, evaluation, sensitivity
    except FileNotFoundError as e:
        st.error(f"Data files not found. Please run the data pipeline first: {e}")
        return None, None, None, None, None


def calculate_bottlenecks(df: pd.DataFrame) -> dict:
    """Identify operational bottlenecks from trip data."""
    active = df[~df["is_cancelled"]]
    
    # Worst performing drivers
    driver_perf = active.groupby("driver_id").agg({
        "efficiency_index": "mean",
        "is_late_pickup": "mean",
        "trip_id": "count",
    }).reset_index()
    
    worst_drivers = driver_perf.nsmallest(5, "efficiency_index")
    
    # Worst hours
    hourly_perf = active.groupby("scheduled_hour").agg({
        "is_late_pickup": "mean",
        "trip_id": "count",
    }).reset_index()
    worst_hours = hourly_perf.nlargest(3, "is_late_pickup")
    
    # Worst regions
    region_perf = active.groupby("region").agg({
        "efficiency_index": "mean",
        "is_late_pickup": "mean",
    }).reset_index()
    worst_regions = region_perf.nsmallest(3, "efficiency_index")
    
    return {
        "worst_drivers": worst_drivers,
        "worst_hours": worst_hours,
        "worst_regions": worst_regions,
    }


def calculate_improvement_potential(df: pd.DataFrame) -> dict:
    """Estimate potential improvements from optimization."""
    active = df[~df["is_cancelled"]]
    
    current_on_time = 1 - active["is_late_pickup"].mean()
    current_efficiency = active["efficiency_index"].mean()
    median_efficiency = active["efficiency_index"].median()
    
    below_median = active[active["efficiency_index"] < median_efficiency]
    improvement_potential = median_efficiency - below_median["efficiency_index"].mean()
    
    # Estimate cost savings (simplified)
    cost_per_mile = 2.15  # Industry average
    avg_deviation = (active["trip_duration_minutes"] / 
                     (active["distance_miles"].clip(lower=0.1) / 25 * 60)).mean()
    
    if avg_deviation > 1.2:
        miles_saving = active["distance_miles"].sum() * (avg_deviation - 1.2) / avg_deviation
    else:
        miles_saving = 0
    
    return {
        "current_on_time_rate": current_on_time * 100,
        "target_on_time_rate": 90.0,
        "current_efficiency": current_efficiency,
        "median_efficiency": median_efficiency,
        "improvement_potential": improvement_potential,
        "trips_below_median": len(below_median),
        "estimated_miles_savings": miles_saving,
        "estimated_cost_savings": miles_saving * cost_per_mile,
    }


# Load data
trips, drivers, simulations, evaluation, sensitivity = load_data()

if trips is None:
    st.warning("⚠️ No data available. Run the pipeline first:")
    st.code("""
python -m src.data_generation
python -m src.data_cleaning  
python -m src.feature_engineering
python -m src.efficiency_scoring
python -m src.routing_simulation
    """)
    st.stop()


# Sidebar filters
st.sidebar.header("🔍 Filters")

# Date range filter (if date data is available)
if trips is not None and "scheduled_pickup_time" in trips.columns:
    min_date = trips["scheduled_pickup_time"].min().date()
    max_date = trips["scheduled_pickup_time"].max().date()
    
    date_range = st.sidebar.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    
    # Handle single date selection
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range if not isinstance(date_range, tuple) else date_range[0]

selected_regions = st.sidebar.multiselect(
    "Regions",
    options=trips["region"].unique(),
    default=trips["region"].unique()
)

selected_trip_types = st.sidebar.multiselect(
    "Trip Types",
    options=trips["trip_type"].unique(),
    default=trips["trip_type"].unique()
)

# Efficiency threshold filter
efficiency_threshold = st.sidebar.slider(
    "Min Efficiency Index",
    min_value=0,
    max_value=100,
    value=0,
    help="Filter to trips with efficiency above this threshold"
)

# Filter data
filtered_trips = trips[
    (trips["region"].isin(selected_regions)) &
    (trips["trip_type"].isin(selected_trip_types)) &
    (~trips["is_cancelled"]) &
    (trips["efficiency_index"] >= efficiency_threshold)
]

# Apply date filter if available
if "scheduled_pickup_time" in trips.columns:
    filtered_trips = filtered_trips[
        (filtered_trips["scheduled_pickup_time"].dt.date >= start_date) &
        (filtered_trips["scheduled_pickup_time"].dt.date <= end_date)
    ]

# Sidebar stats
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Quick Stats")
st.sidebar.metric("Filtered Trips", f"{len(filtered_trips):,}")
st.sidebar.metric("Total Trips", f"{len(trips):,}")
filter_pct = len(filtered_trips) / len(trips) * 100 if len(trips) > 0 else 0
st.sidebar.progress(filter_pct / 100)

# Export functionality in sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("### 📥 Export Data")

@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

if st.sidebar.button("📄 Export Filtered Trips"):
    csv = convert_df_to_csv(filtered_trips)
    st.sidebar.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"filtered_trips_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )


# Tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Overview", 
    "🎯 Executive Summary",
    "👥 Driver Performance", 
    "🗺️ Regional Analysis",
    "🔄 Routing Simulation",
    "🔍 Trip Details"
])


# Tab 1: Overview
with tab1:
    st.header("Overall Performance Metrics")
    
    # Handle empty filter results
    if len(filtered_trips) == 0:
        st.warning("⚠️ No trips match the current filters. Please adjust your selection.")
        st.stop()
    
    # KPI cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        on_time_rate = (1 - filtered_trips["is_late_pickup"].mean()) * 100
        st.metric("On-Time Rate", f"{on_time_rate:.1f}%")
    
    with col2:
        avg_efficiency = filtered_trips["efficiency_index"].mean()
        st.metric("Avg Efficiency Index", f"{avg_efficiency:.1f}")
    
    with col3:
        total_trips = len(filtered_trips)
        st.metric("Total Trips", f"{total_trips:,}")
    
    with col4:
        total_miles = filtered_trips["distance_miles"].sum()
        st.metric("Total Miles", f"{total_miles:,.0f}")
    
    st.markdown("---")
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Efficiency Distribution")
        fig = px.histogram(
            filtered_trips,
            x="efficiency_index",
            nbins=30,
            title="Trip Efficiency Index Distribution",
            color_discrete_sequence=["#1f77b4"]
        )
        fig.update_layout(xaxis_title="Efficiency Index", yaxis_title="Count")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("On-Time Performance by Hour")
        hourly = filtered_trips.groupby("scheduled_hour").agg({
            "is_late_pickup": lambda x: (1 - x.mean()) * 100,
            "trip_id": "count"
        }).reset_index()
        hourly.columns = ["Hour", "On-Time Rate", "Trip Count"]
        
        fig = px.bar(
            hourly,
            x="Hour",
            y="On-Time Rate",
            title="On-Time Rate by Hour of Day",
            color="On-Time Rate",
            color_continuous_scale="RdYlGn"
        )
        fig.update_layout(yaxis_title="On-Time Rate (%)")
        st.plotly_chart(fig, use_container_width=True)
    
    # Trip type breakdown
    st.subheader("Performance by Trip Type")
    trip_type_perf = filtered_trips.groupby("trip_type").agg({
        "efficiency_index": "mean",
        "is_late_pickup": lambda x: (1 - x.mean()) * 100,
        "trip_id": "count"
    }).reset_index()
    trip_type_perf.columns = ["Trip Type", "Avg Efficiency", "On-Time Rate", "Count"]
    
    fig = px.bar(
        trip_type_perf,
        x="Trip Type",
        y=["Avg Efficiency", "On-Time Rate"],
        barmode="group",
        title="Efficiency & On-Time Rate by Trip Type"
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Time trend analysis
    st.subheader("📈 Daily Trend Analysis")
    
    if "scheduled_pickup_time" in filtered_trips.columns:
        daily_trends = filtered_trips.groupby(filtered_trips["scheduled_pickup_time"].dt.date).agg({
            "efficiency_index": "mean",
            "is_late_pickup": lambda x: (1 - x.mean()) * 100,
            "trip_id": "count"
        }).reset_index()
        daily_trends.columns = ["Date", "Avg Efficiency", "On-Time Rate", "Trip Count"]
        
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Scatter(x=daily_trends["Date"], y=daily_trends["Avg Efficiency"], 
                      name="Avg Efficiency", line=dict(color="#1f77b4")),
            secondary_y=False
        )
        fig.add_trace(
            go.Scatter(x=daily_trends["Date"], y=daily_trends["On-Time Rate"], 
                      name="On-Time Rate %", line=dict(color="#2ca02c")),
            secondary_y=True
        )
        fig.update_layout(title="Daily Performance Trends")
        fig.update_yaxes(title_text="Efficiency Index", secondary_y=False)
        fig.update_yaxes(title_text="On-Time Rate %", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)


# Tab 2: Executive Summary
with tab2:
    st.header("🎯 Executive Summary & Insights")
    
    # Calculate bottlenecks and improvement potential
    bottlenecks = calculate_bottlenecks(filtered_trips)
    improvements = calculate_improvement_potential(filtered_trips)
    
    # Key insights
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 📊 Current Performance")
        st.metric(
            "On-Time Rate",
            f"{improvements['current_on_time_rate']:.1f}%",
            delta=f"{improvements['current_on_time_rate'] - improvements['target_on_time_rate']:.1f}% vs target"
        )
        st.metric(
            "Avg Efficiency",
            f"{improvements['current_efficiency']:.1f}",
            delta=f"{improvements['current_efficiency'] - improvements['median_efficiency']:.1f} vs median"
        )
    
    with col2:
        st.markdown("### 💰 Improvement Potential")
        st.metric(
            "Trips Below Median",
            f"{improvements['trips_below_median']:,}",
            delta="Need improvement",
            delta_color="inverse"
        )
        st.metric(
            "Est. Miles Savings",
            f"{improvements['estimated_miles_savings']:,.0f}",
            help="Potential miles reduction through optimization"
        )
    
    with col3:
        st.markdown("### 💵 Cost Impact")
        st.metric(
            "Est. Cost Savings",
            f"${improvements['estimated_cost_savings']:,.0f}",
            help="Based on $2.15/mile industry average"
        )
        efficiency_gap = improvements['improvement_potential']
        st.metric(
            "Efficiency Gap",
            f"{efficiency_gap:.1f} pts",
            help="Gap between low performers and median"
        )
    
    st.markdown("---")
    
    # Bottleneck Analysis
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("⚠️ Worst Performing Hours")
        worst_hours = bottlenecks["worst_hours"]
        fig = px.bar(
            worst_hours,
            x="scheduled_hour",
            y="is_late_pickup",
            title="Hours with Highest Late Pickup Rate",
            color="is_late_pickup",
            color_continuous_scale="Reds"
        )
        fig.update_layout(xaxis_title="Hour of Day", yaxis_title="Late Pickup Rate")
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)
        
        # Insights
        peak_hour = worst_hours.iloc[0]["scheduled_hour"] if len(worst_hours) > 0 else "N/A"
        st.info(f"💡 **Insight:** Hour {peak_hour}:00 has the highest late pickup rate. Consider adding more drivers during this window.")
    
    with col2:
        st.subheader("⚠️ Underperforming Regions")
        worst_regions = bottlenecks["worst_regions"]
        fig = px.bar(
            worst_regions,
            x="region",
            y="efficiency_index",
            title="Regions with Lowest Efficiency",
            color="is_late_pickup",
            color_continuous_scale="RdYlGn_r"
        )
        fig.update_layout(xaxis_title="Region", yaxis_title="Avg Efficiency Index")
        st.plotly_chart(fig, use_container_width=True)
        
        # Insights
        worst_region = worst_regions.iloc[0]["region"] if len(worst_regions) > 0 else "N/A"
        st.info(f"💡 **Insight:** {worst_region} has the lowest efficiency. Investigate local factors like traffic or driver coverage.")
    
    # Actionable Recommendations
    st.subheader("📋 Recommended Actions")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        **🚗 Driver Optimization**
        - Review bottom 10% of drivers
        - Implement targeted training
        - Adjust driver assignments by strength
        """)
    
    with col2:
        st.markdown("""
        **⏰ Scheduling Improvements**
        - Add capacity during peak hours
        - Stagger appointment times
        - Buffer high-traffic routes
        """)
    
    with col3:
        st.markdown("""
        **🗺️ Route Optimization**
        - Consolidate nearby pickups
        - Use capacity-aware routing
        - Pre-position drivers strategically
        """)


# Tab 3: Driver Performance
with tab3:
    st.header("Driver Performance Analysis")
    
    # Compute driver stats from trips
    driver_stats = filtered_trips[~filtered_trips["is_cancelled"]].groupby("driver_id").agg({
        "trip_id": "count",
        "efficiency_index": "mean",
        "is_late_pickup": "mean",
        "score_on_time": "mean",
        "score_route": "mean",
        "score_capacity": "mean",
        "score_idle": "mean",
        "distance_miles": "sum"
    }).reset_index()
    driver_stats.columns = ["driver_id", "total_trips", "avg_efficiency", "late_pickup_rate",
                            "avg_on_time_score", "avg_route_score", "avg_capacity_score", 
                            "avg_idle_score", "total_miles"]
    driver_stats = driver_stats.sort_values("avg_efficiency", ascending=False)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Driver Efficiency Rankings")
        
        # Top/bottom toggle
        view = st.radio("View", ["Top Performers", "Bottom Performers"], horizontal=True)
        n_drivers = st.slider("Number of drivers", 5, 20, 10)
        
        if view == "Top Performers":
            display_drivers = driver_stats.head(n_drivers)
        else:
            display_drivers = driver_stats.tail(n_drivers).iloc[::-1]
        
        fig = px.bar(
            display_drivers,
            x="driver_id",
            y="avg_efficiency",
            color="late_pickup_rate",
            color_continuous_scale="RdYlGn_r",
            title=f"{view} - Driver Efficiency"
        )
        fig.update_layout(xaxis_title="Driver ID", yaxis_title="Avg Efficiency Index")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Driver Stats")
        st.dataframe(
            display_drivers[[
                "driver_id", "avg_efficiency", "total_trips", "late_pickup_rate"
            ]].style.format({
                "avg_efficiency": "{:.1f}",
                "late_pickup_rate": "{:.1%}"
            }),
            height=400
        )
    
    # Score breakdown
    st.subheader("Score Component Breakdown")
    score_cols = ["avg_on_time_score", "avg_route_score", "avg_capacity_score", "avg_idle_score"]
    
    avg_scores = driver_stats[score_cols].mean()
    fig = px.bar(
        x=["On-Time", "Route Efficiency", "Capacity", "Idle Time"],
        y=avg_scores.values,
        title="Average Score by Component (All Drivers)",
        color=avg_scores.values,
        color_continuous_scale="Blues"
    )
    fig.update_layout(xaxis_title="Component", yaxis_title="Avg Score")
    st.plotly_chart(fig, use_container_width=True)
    
    # Driver comparison scatter plot
    st.subheader("Driver Performance Matrix")
    fig = px.scatter(
        driver_stats,
        x="total_trips",
        y="avg_efficiency",
        size="total_miles",
        color="late_pickup_rate",
        color_continuous_scale="RdYlGn_r",
        hover_data=["driver_id"],
        title="Trips vs Efficiency (size = total miles)"
    )
    fig.update_layout(xaxis_title="Total Trips", yaxis_title="Avg Efficiency")
    st.plotly_chart(fig, use_container_width=True)


# Tab 4: Regional Analysis
with tab4:
    st.header("Regional Performance Analysis")
    
    # Compute region stats from trips
    regions = filtered_trips.groupby("region").agg({
        "trip_id": "count",
        "efficiency_index": "mean",
        "is_late_pickup": "mean",
        "distance_miles": "mean"
    }).reset_index()
    regions.columns = ["region", "total_trips", "avg_efficiency", "late_pickup_rate", "avg_distance"]
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Efficiency by Region")
        fig = px.bar(
            regions.sort_values("avg_efficiency", ascending=False),
            x="region",
            y="avg_efficiency",
            color="late_pickup_rate",
            color_continuous_scale="RdYlGn_r",
            title="Regional Efficiency Comparison"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Region Statistics")
        st.dataframe(
            regions.style.format({
                "avg_efficiency": "{:.1f}",
                "late_pickup_rate": "{:.1%}",
                "avg_distance": "{:.1f}"
            }),
            height=300
        )
    
    # Regional trends
    st.subheader("Trip Volume by Region")
    fig = px.pie(
        regions,
        values="total_trips",
        names="region",
        title="Trip Distribution by Region"
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Regional heatmap by hour
    st.subheader("Regional Performance by Hour")
    region_hour = filtered_trips.groupby(["region", "scheduled_hour"]).agg({
        "efficiency_index": "mean"
    }).reset_index()
    
    heatmap_data = region_hour.pivot(index="region", columns="scheduled_hour", values="efficiency_index")
    fig = px.imshow(
        heatmap_data,
        labels=dict(x="Hour of Day", y="Region", color="Efficiency"),
        color_continuous_scale="RdYlGn",
        title="Efficiency Heatmap: Region vs Hour"
    )
    st.plotly_chart(fig, use_container_width=True)


# Tab 5: Routing Simulation
with tab5:
    st.header("Routing Strategy Comparison")
    
    if simulations is not None and len(simulations) > 0:
        st.subheader("Strategy Performance Metrics")
        
        # Comparison chart
        fig = go.Figure()
        
        metrics = ["on_time_rate", "utilization_rate"]
        for metric in metrics:
            fig.add_trace(go.Bar(
                name=metric.replace("_", " ").title(),
                x=simulations["strategy"],
                y=simulations[metric],
            ))
        
        fig.update_layout(
            barmode="group",
            title="Strategy Comparison: On-Time Rate & Utilization",
            xaxis_title="Strategy",
            yaxis_title="Percentage (%)"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Details table
        st.subheader("Detailed Results")
        st.dataframe(
            simulations.style.format({
                "on_time_rate": "{:.1f}%",
                "total_miles": "{:,.0f}",
                "avg_trip_duration": "{:.1f} min",
                "utilization_rate": "{:.1f}%"
            })
        )
        
        # Recommendation
        best_strategy = simulations.loc[simulations["on_time_rate"].idxmax(), "strategy"]
        st.success(f"🏆 **Recommended Strategy:** {best_strategy} (highest on-time rate)")
        
        # Sensitivity Analysis
        if sensitivity is not None and len(sensitivity) > 0:
            st.markdown("---")
            st.subheader("📊 Sensitivity Analysis: Driver Count Impact")
            
            fig = px.line(
                sensitivity,
                x="n_drivers",
                y="on_time_rate",
                color="strategy",
                markers=True,
                title="On-Time Rate vs Number of Drivers"
            )
            fig.update_layout(
                xaxis_title="Number of Drivers",
                yaxis_title="On-Time Rate (%)"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            st.info("💡 **Insight:** This analysis shows how performance scales with driver count. Use this to determine optimal fleet size.")
        
        # Strategy comparison radar
        st.subheader("Strategy Comparison Radar")
        categories = ["On-Time Rate", "Utilization", "Avg Duration", "Total Miles"]
        
        fig = go.Figure()
        for _, row in simulations.iterrows():
            # Normalize values for radar chart
            values = [
                row["on_time_rate"] / 100,  # Normalize to 0-1
                row["utilization_rate"] / 100,
                1 - (row["avg_trip_duration"] / simulations["avg_trip_duration"].max()),  # Invert so lower is better
                1 - (row["total_miles"] / simulations["total_miles"].max()),  # Invert so lower is better
            ]
            values.append(values[0])  # Close the radar
            
            fig.add_trace(go.Scatterpolar(
                r=values,
                theta=categories + [categories[0]],
                name=row["strategy"]
            ))
        
        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 1])))
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.warning("No simulation results available. Run the routing simulation first.")


# Tab 6: Trip Details
with tab6:
    st.header("🔍 Trip-Level Analysis")
    
    st.markdown("Explore individual trips and identify specific issues.")
    
    # Search and filter
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_driver = st.text_input("Search Driver ID", placeholder="e.g., D001")
    
    with col2:
        min_efficiency = st.number_input("Min Efficiency", value=0, min_value=0, max_value=100)
        max_efficiency = st.number_input("Max Efficiency", value=100, min_value=0, max_value=100)
    
    with col3:
        show_late_only = st.checkbox("Show Late Pickups Only")
    
    # Apply search filters
    detail_trips = filtered_trips.copy()
    
    if search_driver:
        detail_trips = detail_trips[detail_trips["driver_id"].str.contains(search_driver, case=False, na=False)]
    
    detail_trips = detail_trips[
        (detail_trips["efficiency_index"] >= min_efficiency) &
        (detail_trips["efficiency_index"] <= max_efficiency)
    ]
    
    if show_late_only:
        detail_trips = detail_trips[detail_trips["is_late_pickup"] == True]
    
    st.markdown(f"**Showing {len(detail_trips):,} trips**")
    
    # Display columns selection
    display_cols = [
        "trip_id", "driver_id", "region", "trip_type",
        "scheduled_pickup_time", "efficiency_index", 
        "is_late_pickup", "pickup_delay_minutes", "distance_miles"
    ]
    available_cols = [c for c in display_cols if c in detail_trips.columns]
    
    # Interactive data table
    st.dataframe(
        detail_trips[available_cols].sort_values("efficiency_index").head(100).style.format({
            "efficiency_index": "{:.1f}",
            "pickup_delay_minutes": "{:.1f}",
            "distance_miles": "{:.1f}"
        }).background_gradient(subset=["efficiency_index"], cmap="RdYlGn"),
        height=400,
        width="stretch"
    )
    
    # Trip distribution
    st.subheader("Trip Efficiency Distribution")
    fig = px.histogram(
        detail_trips,
        x="efficiency_index",
        nbins=50,
        color="is_late_pickup",
        barmode="overlay",
        title="Efficiency Distribution (Late vs On-Time)",
        color_discrete_map={True: "#d62728", False: "#2ca02c"}
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Outlier analysis
    st.subheader("⚠️ Worst Performing Trips")
    worst_trips = filtered_trips.nsmallest(10, "efficiency_index")[available_cols]
    st.dataframe(
        worst_trips.style.format({
            "efficiency_index": "{:.1f}",
            "pickup_delay_minutes": "{:.1f}",
            "distance_miles": "{:.1f}"
        }),
        width="stretch"
    )


# Footer
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("*ModivCare Rides Efficiency Dashboard*")
with col2:
    st.markdown(f"*Data as of: {datetime.now().strftime('%Y-%m-%d')}*")
with col3:
    st.markdown("*Built with Streamlit & Plotly*")
