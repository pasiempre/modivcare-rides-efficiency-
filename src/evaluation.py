"""Evaluation metrics and analysis for NEMT efficiency."""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple

from .config import PROCESSED_DIR


def calculate_summary_stats(df: pd.DataFrame) -> Dict:
    """Calculate overall summary statistics."""
    active = df[~df["is_cancelled"]]
    
    return {
        "total_trips": len(df),
        "completed_trips": len(active),
        "cancelled_trips": len(df) - len(active),
        "cancellation_rate": (len(df) - len(active)) / len(df) * 100,
        "on_time_rate": (1 - active["is_late_pickup"].mean()) * 100,
        "avg_efficiency_index": active["efficiency_index"].mean(),
        "avg_distance_miles": active["distance_miles"].mean(),
        "avg_trip_duration": active["trip_duration_minutes"].mean(),
        "total_miles": active["distance_miles"].sum(),
        "unique_drivers": active["driver_id"].nunique(),
        "unique_regions": active["region"].nunique(),
    }


def identify_bottlenecks(df: pd.DataFrame, top_n: int = 10) -> Dict:
    """Identify operational bottlenecks."""
    active = df[~df["is_cancelled"]]
    
    # Worst performing drivers
    driver_perf = active.groupby("driver_id").agg({
        "efficiency_index": "mean",
        "is_late_pickup": "mean",
        "trip_id": "count",
    }).reset_index()
    
    worst_drivers = driver_perf.nsmallest(top_n, "efficiency_index")[
        ["driver_id", "efficiency_index", "is_late_pickup"]
    ].to_dict("records")
    
    # Worst hours
    hourly_perf = active.groupby("scheduled_hour").agg({
        "is_late_pickup": "mean",
        "trip_id": "count",
    }).reset_index()
    
    worst_hours = hourly_perf.nlargest(3, "is_late_pickup")[
        ["scheduled_hour", "is_late_pickup"]
    ].to_dict("records")
    
    # Worst regions
    region_perf = active.groupby("region").agg({
        "efficiency_index": "mean",
        "is_late_pickup": "mean",
    }).reset_index()
    
    worst_regions = region_perf.nsmallest(3, "efficiency_index")[
        ["region", "efficiency_index", "is_late_pickup"]
    ].to_dict("records")
    
    # Worst trip types
    trip_type_perf = active.groupby("trip_type").agg({
        "is_late_pickup": "mean",
        "trip_id": "count",
    }).reset_index()
    
    worst_trip_types = trip_type_perf.nlargest(3, "is_late_pickup")[
        ["trip_type", "is_late_pickup"]
    ].to_dict("records")
    
    return {
        "worst_drivers": worst_drivers,
        "worst_hours": worst_hours,
        "worst_regions": worst_regions,
        "worst_trip_types": worst_trip_types,
    }


def calculate_improvement_potential(df: pd.DataFrame) -> Dict:
    """Estimate potential improvements from optimization."""
    active = df[~df["is_cancelled"]]
    
    current_on_time = 1 - active["is_late_pickup"].mean()
    current_efficiency = active["efficiency_index"].mean()
    
    # Target: bring low performers up to median
    median_efficiency = active["efficiency_index"].median()
    
    below_median = active[active["efficiency_index"] < median_efficiency]
    improvement_potential = (median_efficiency - below_median["efficiency_index"].mean())
    
    # Estimate miles saved if routes were more efficient
    # Guard against zero-distance trips
    safe_distance = active["distance_miles"].clip(lower=0.1)
    avg_deviation = (active["trip_duration_minutes"] / 
                     (safe_distance / 25 * 60)).mean()
    
    if avg_deviation > 1.2:
        miles_saving_potential = active["distance_miles"].sum() * (avg_deviation - 1.2) / avg_deviation
    else:
        miles_saving_potential = 0
    
    # Calculate gap (handle case where already above target)
    on_time_gap = (0.90 - current_on_time) * 100
    gap_description = "above target" if on_time_gap < 0 else "to close"
    
    return {
        "current_on_time_rate": current_on_time * 100,
        "target_on_time_rate": 90.0,  # Industry target
        "on_time_gap": abs(on_time_gap),  # Always positive
        "on_time_gap_direction": gap_description,
        "current_efficiency": current_efficiency,
        "potential_efficiency_gain": improvement_potential,
        "trips_below_median": len(below_median),
        "estimated_miles_savings": miles_saving_potential,
    }


def generate_evaluation_report(df: pd.DataFrame) -> str:
    """Generate a text-based evaluation report."""
    stats = calculate_summary_stats(df)
    bottlenecks = identify_bottlenecks(df)
    improvements = calculate_improvement_potential(df)
    
    report = []
    report.append("=" * 60)
    report.append("NEMT EFFICIENCY EVALUATION REPORT")
    report.append("=" * 60)
    
    report.append("\n📊 SUMMARY STATISTICS")
    report.append("-" * 40)
    report.append(f"Total Trips: {stats['total_trips']:,}")
    report.append(f"Completed: {stats['completed_trips']:,} ({100 - stats['cancellation_rate']:.1f}%)")
    report.append(f"On-Time Rate: {stats['on_time_rate']:.1f}%")
    report.append(f"Avg Efficiency Index: {stats['avg_efficiency_index']:.1f}")
    report.append(f"Total Miles: {stats['total_miles']:,.0f}")
    
    report.append("\n⚠️ BOTTLENECKS")
    report.append("-" * 40)
    
    report.append("Worst Hours (by late rate):")
    for h in bottlenecks["worst_hours"]:
        report.append(f"  Hour {h['scheduled_hour']:02d}:00 - {h['is_late_pickup']*100:.1f}% late")
    
    report.append("Worst Regions (by efficiency):")
    for r in bottlenecks["worst_regions"]:
        report.append(f"  {r['region']} - Efficiency: {r['efficiency_index']:.1f}")
    
    report.append("\n📈 IMPROVEMENT POTENTIAL")
    report.append("-" * 40)
    report.append(f"Current On-Time: {improvements['current_on_time_rate']:.1f}%")
    report.append(f"Target On-Time: {improvements['target_on_time_rate']:.1f}%")
    gap_text = f"{improvements['on_time_gap']:.1f} percentage points {improvements['on_time_gap_direction']}"
    report.append(f"Gap: {gap_text}")
    report.append(f"Trips Below Median: {improvements['trips_below_median']:,}")
    report.append(f"Est. Miles Savings: {improvements['estimated_miles_savings']:,.0f}")
    
    report.append("\n" + "=" * 60)
    
    return "\n".join(report)


if __name__ == "__main__":
    # Load scored data
    df = pd.read_csv(PROCESSED_DIR / "trips_scored.csv")
    
    report = generate_evaluation_report(df)
    print(report)
    
    # Save report
    with open(PROCESSED_DIR / "evaluation_report.txt", "w") as f:
        f.write(report)
