# ModivCare Rides Efficiency & Routing Simulation

## 1. Problem Overview

Non-emergency medical transport (NEMT) companies like ModivCare coordinate thousands of rides per day between patients, clinics, and drivers. 
Inefficient routing and trip assignment can lead to late arrivals, missed appointments, high costs, and poor member experience.

This project builds a synthetic but realistic dataset of NEMT rides and develops:
- An **efficiency scoring algorithm** for individual trips and routes.
- A **routing simulation engine** that tests different assignment strategies.
- A **visual analytics dashboard** to understand where and why efficiency breaks down.

The goal is to show how data-driven routing can improve on-time performance, reduce wasted miles, and optimize driver capacity.

---

## 2. Data Description (Synthetic)

The project uses synthetic data that mimics real NEMT operations:

| Column | Description |
|--------|-------------|
| `trip_id` | Unique trip identifier |
| `member_id` | Patient/member identifier |
| `driver_id` | Driver identifier |
| `pickup_lat`, `pickup_lng` | Pickup coordinates |
| `dropoff_lat`, `dropoff_lng` | Dropoff coordinates |
| `requested_pickup_time` | Member's requested pickup time |
| `scheduled_pickup_time` | Scheduled pickup time |
| `actual_pickup_time` | Actual pickup time |
| `actual_dropoff_time` | Actual dropoff time |
| `distance_miles` | Trip distance |
| `trip_type` | e.g., dialysis, follow-up, physical therapy |
| `vehicle_capacity` | Vehicle passenger capacity |
| `num_passengers` | Number of passengers |
| `late_pickup_flag` | Boolean: pickup was late |
| `late_dropoff_flag` | Boolean: dropoff was late |
| `cancellation_reason` | Reason for cancellation (if applicable) |
| `region` | Geographic region |

---

## 3. Methods & Approach

### 3.1 Data Generation & Cleaning
- Generate synthetic ride logs with realistic distributions for times, distances, and delays.
- Clean and standardize timestamps, derive distances, and label late/early trips.

### 3.2 Feature Engineering
- Compute distance-based metrics (planned vs actual miles).
- Compute time-based metrics (idle time, wait time, lateness).
- Compute capacity utilization per trip and per driver-day.

### 3.3 Efficiency Scoring Algorithm
Build an efficiency index that combines:
- Route deviation ratio
- Idle minutes per mile
- Capacity underutilization
- On-time performance

Score trips, drivers, and regions.

### 3.4 Routing Simulation
Simulate alternative routing strategies:
- Naive first-come-first-served assignment
- Shortest-distance-next assignment
- Time-window and capacity-aware assignment

Compare on-time % and total miles across strategies.

> **Note:** This is a conceptual comparison using historical durations/delays with light stochastic variation, not a full vehicle routing optimization model. Strategy differences reflect assignment logic; for production use, you would recalculate travel times based on actual driver positions after each trip.

### 3.5 Visualization & Dashboard
Interactive charts to:
- Compare efficiency by driver and region.
- Show distributions of late trips.
- Highlight top bottlenecks and improvement opportunities.

---

## 4. Business Value

This project demonstrates how a Business/Data Analyst can:
- Translate operational pain points into measurable metrics.
- Design scoring systems that reflect real-world efficiency trade-offs.
- Simulate policy changes (e.g., new routing rules) before rolling them out.
- Communicate opportunities for cost savings and service improvement.

The patterns here generalize to logistics, healthcare, rideshare, and any operation that coordinates time-windowed trips at scale.

---

## 5. Project Structure

```
modivcare-rides-efficiency/
├── README.md
├── requirements.txt
├── pyproject.toml
├── .gitignore
├── data/
│   ├── raw/                 # Raw generated data
│   ├── interim/             # Intermediate transformations
│   └── processed/           # Final cleaned datasets
├── models/                  # Saved scoring models/weights
├── notebooks/
│   ├── 01_data_generation.ipynb
│   ├── 02_exploration.ipynb
│   ├── 03_feature_engineering.ipynb
│   ├── 04_efficiency_scoring.ipynb
│   └── 05_routing_simulation.ipynb
├── reports/
│   └── figures/             # Generated charts and visuals
├── sql/                     # SQL transformations (optional)
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── utils.py
│   ├── data_generation.py
│   ├── data_cleaning.py
│   ├── feature_engineering.py
│   ├── efficiency_scoring.py
│   ├── routing_simulation.py
│   └── evaluation.py
├── app/
│   └── streamlit_app.py
└── tests/
    ├── __init__.py
    ├── test_efficiency_scoring.py
    └── test_routing_simulation.py
```

---

## 6. How to Run

### Installation

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Generate Data

```bash
python -m src.data_generation
```

### Run Dashboard

```bash
streamlit run app/streamlit_app.py
```

### Run Tests

```bash
pytest
```

---

## 7. License

MIT License
