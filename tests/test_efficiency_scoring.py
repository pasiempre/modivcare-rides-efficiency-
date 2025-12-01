"""Tests for efficiency scoring module."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.efficiency_scoring import (
    calculate_on_time_score,
    calculate_route_deviation_score,
    calculate_capacity_score,
    calculate_efficiency_index,
)


@pytest.fixture
def sample_trips():
    """Create sample trip data for testing."""
    return pd.DataFrame({
        "trip_id": ["T001", "T002", "T003", "T004"],
        "pickup_delay_minutes": [0, 5, 15, -5],  # On-time, slightly late, late, early
        "trip_duration_minutes": [30, 45, 60, 25],
        "distance_miles": [10, 10, 10, 10],
        "capacity_utilization": [1.0, 0.5, 0.25, 0.75],
        "daily_minutes": [480, 240, 120, 360],
        "is_cancelled": [False, False, False, False],
    })


class TestOnTimeScore:
    """Tests for on-time score calculation."""
    
    def test_perfect_on_time(self, sample_trips):
        """Test that 0 delay gives high score."""
        scores = calculate_on_time_score(sample_trips)
        # Formula: (100 - ((delay + 10) / 40 * 100)), so 0 delay = 75
        assert scores.iloc[0] >= 70  # First trip has 0 delay
    
    def test_late_pickup_lower_score(self, sample_trips):
        """Test that late pickups have lower scores."""
        scores = calculate_on_time_score(sample_trips)
        assert scores.iloc[2] < scores.iloc[0]  # 15 min late < on-time
    
    def test_early_pickup_high_score(self, sample_trips):
        """Test that early pickups still get good scores."""
        scores = calculate_on_time_score(sample_trips)
        # Early pickup (-5 min) scores higher than late
        assert scores.iloc[3] >= 80  # Early pickup


class TestRouteDeviationScore:
    """Tests for route deviation score calculation."""
    
    def test_efficient_route_high_score(self, sample_trips):
        """Test that efficient routes score higher."""
        scores = calculate_route_deviation_score(sample_trips)
        # 10 miles at 25 mph = 24 min expected
        # Trip with 25 min duration should score well
        assert scores.iloc[3] > 50
    
    def test_inefficient_route_lower_score(self, sample_trips):
        """Test that inefficient routes score lower."""
        scores = calculate_route_deviation_score(sample_trips)
        # Trip with 60 min duration for 10 miles is inefficient
        assert scores.iloc[2] < scores.iloc[3]


class TestCapacityScore:
    """Tests for capacity utilization score calculation."""
    
    def test_full_capacity_max_score(self, sample_trips):
        """Test that 100% utilization gives max score."""
        scores = calculate_capacity_score(sample_trips)
        assert scores.iloc[0] == 100.0
    
    def test_partial_capacity_proportional_score(self, sample_trips):
        """Test that partial utilization gives proportional score."""
        scores = calculate_capacity_score(sample_trips)
        assert scores.iloc[1] == 50.0  # 50% utilization
        assert scores.iloc[2] == 25.0  # 25% utilization


class TestEfficiencyIndex:
    """Tests for overall efficiency index calculation."""
    
    def test_returns_all_score_columns(self, sample_trips):
        """Test that all score columns are created."""
        result = calculate_efficiency_index(sample_trips)
        
        assert "score_on_time" in result.columns
        assert "score_route" in result.columns
        assert "score_capacity" in result.columns
        assert "score_idle" in result.columns
        assert "efficiency_index" in result.columns
    
    def test_efficiency_index_in_range(self, sample_trips):
        """Test that efficiency index is within valid range."""
        result = calculate_efficiency_index(sample_trips)
        
        assert result["efficiency_index"].min() >= 0
        assert result["efficiency_index"].max() <= 100
    
    def test_custom_weights(self, sample_trips):
        """Test that custom weights are applied."""
        equal_weights = {
            "on_time_performance": 0.25,
            "route_deviation": 0.25,
            "capacity_utilization": 0.25,
            "idle_time": 0.25,
        }
        
        result = calculate_efficiency_index(sample_trips, weights=equal_weights)
        
        # Verify index is computed
        assert result["efficiency_index"].notna().all()
