"""Tests for routing simulation module."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.routing_simulation import (
    assign_fcfs,
    assign_nearest,
    assign_capacity_aware,
    simulate_strategy,
    SimulationResult,
)


@pytest.fixture
def sample_trips():
    """Create sample trip data for testing."""
    base_time = datetime(2025, 1, 15, 8, 0)
    
    return pd.DataFrame({
        "trip_id": ["T001", "T002", "T003", "T004", "T005"],
        "requested_pickup_time": [
            base_time,
            base_time + timedelta(minutes=15),
            base_time + timedelta(minutes=30),
            base_time + timedelta(minutes=45),
            base_time + timedelta(minutes=60),
        ],
        "scheduled_pickup_time": [
            base_time + timedelta(minutes=5),
            base_time + timedelta(minutes=20),
            base_time + timedelta(minutes=35),
            base_time + timedelta(minutes=50),
            base_time + timedelta(minutes=65),
        ],
        "pickup_lat": [33.4, 33.45, 33.5, 33.55, 33.6],
        "pickup_lng": [-112.0, -112.05, -112.1, -112.15, -112.2],
        "dropoff_lat": [33.42, 33.47, 33.52, 33.57, 33.62],
        "dropoff_lng": [-112.02, -112.07, -112.12, -112.17, -112.22],
        "distance_miles": [5, 6, 7, 8, 5],
        "trip_duration_minutes": [20, 25, 30, 35, 20],
        "num_passengers": [1, 2, 3, 1, 2],
        "capacity_utilization": [0.25, 0.5, 0.75, 0.25, 0.5],
        "pickup_delay_minutes": [0, 5, 10, 0, 5],
        "is_late_pickup": [False, False, True, False, False],
        "is_cancelled": [False, False, False, False, False],
    })


@pytest.fixture
def drivers():
    """Create sample driver list."""
    return ["DRV_0001", "DRV_0002", "DRV_0003"]


class TestFCFSAssignment:
    """Tests for FCFS assignment strategy."""
    
    def test_assigns_all_trips(self, sample_trips, drivers):
        """Test that all trips are assigned."""
        assignments = assign_fcfs(sample_trips, drivers)
        assert len(assignments) == len(sample_trips)
    
    def test_all_trips_have_driver(self, sample_trips, drivers):
        """Test that every trip has an assigned driver."""
        assignments = assign_fcfs(sample_trips, drivers)
        assert assignments["assigned_driver"].notna().all()
    
    def test_uses_available_drivers(self, sample_trips, drivers):
        """Test that drivers from the pool are used."""
        assignments = assign_fcfs(sample_trips, drivers)
        assert assignments["assigned_driver"].isin(drivers).all()


class TestNearestAssignment:
    """Tests for nearest-driver assignment strategy."""
    
    def test_assigns_all_trips(self, sample_trips, drivers):
        """Test that all trips are assigned."""
        driver_locations = {
            "DRV_0001": (33.4, -112.0),
            "DRV_0002": (33.5, -112.1),
            "DRV_0003": (33.6, -112.2),
        }
        assignments = assign_nearest(sample_trips, drivers, driver_locations)
        assert len(assignments) == len(sample_trips)
    
    def test_prefers_closer_drivers(self, sample_trips, drivers):
        """Test that closer drivers are preferred."""
        # Put driver 1 very close to first pickup
        driver_locations = {
            "DRV_0001": (33.4, -112.0),  # Very close to first trip
            "DRV_0002": (33.9, -112.5),  # Far away
            "DRV_0003": (33.9, -112.5),  # Far away
        }
        assignments = assign_nearest(sample_trips, drivers, driver_locations)
        
        first_trip_assignment = assignments[assignments["trip_id"] == "T001"]
        assert first_trip_assignment["assigned_driver"].iloc[0] == "DRV_0001"


class TestCapacityAwareAssignment:
    """Tests for capacity-aware assignment strategy."""
    
    def test_assigns_all_trips(self, sample_trips, drivers):
        """Test that all trips are assigned."""
        driver_capacities = {
            "DRV_0001": 2,
            "DRV_0002": 4,
            "DRV_0003": 6,
        }
        assignments = assign_capacity_aware(sample_trips, drivers, driver_capacities)
        assert len(assignments) == len(sample_trips)
    
    def test_prefers_appropriate_capacity(self, sample_trips, drivers):
        """Test that appropriate capacity vehicles are preferred."""
        driver_capacities = {
            "DRV_0001": 2,  # Small
            "DRV_0002": 4,  # Medium
            "DRV_0003": 6,  # Large
        }
        assignments = assign_capacity_aware(sample_trips, drivers, driver_capacities)
        
        # Trip with 3 passengers should NOT use smallest vehicle (DRV_0001 = 2 capacity)
        trip_3_pass = assignments[assignments["trip_id"] == "T003"]
        assert trip_3_pass["assigned_driver"].iloc[0] != "DRV_0001"  # Can't fit 3 in capacity 2


class TestSimulationResult:
    """Tests for SimulationResult dataclass."""
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = SimulationResult(
            strategy_name="Test",
            total_trips=100,
            on_time_rate=0.85,
            total_miles=500.0,
            avg_trip_duration=25.5,
            avg_idle_time=10.0,
            utilization_rate=0.75,
        )
        
        d = result.to_dict()
        
        assert d["strategy"] == "Test"
        assert d["total_trips"] == 100
        assert d["on_time_rate"] == 85.0  # Converted to percentage
        assert d["utilization_rate"] == 75.0


class TestSimulateStrategy:
    """Tests for strategy simulation."""
    
    def test_returns_simulation_result(self, sample_trips, drivers):
        """Test that simulation returns proper result object."""
        assignments = assign_fcfs(sample_trips, drivers)
        result = simulate_strategy(sample_trips, assignments)
        
        assert isinstance(result, SimulationResult)
        assert result.total_trips > 0
        assert 0 <= result.on_time_rate <= 1
