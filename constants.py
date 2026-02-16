"""
HYFI Physical Constants and Hydrological Parameters
Khlong U-Tapao Basin - Hat Yai Flood Monitoring System
"""

import math
from datetime import timedelta

# =============================================================
# GEOGRAPHICAL & PHYSICAL CONSTANTS
# =============================================================

# Station Information
STATION_METADATA = {
    "HatYai": {
        "id": 2585,
        "code": "X.90",
        "name": "Hat Yai City",
        "location": "Economic Zone",
        "bank_full_capacity": 10.5,  # meters MSL
        "critical_threshold": 11.0,   # meters MSL
        "min_valid_level": -2.0,      # meters MSL (dry season)
        "lat": 7.0084,
        "lon": 100.4767
    },
    "Sadao": {
        "id": 2590,
        "code": "X.173", 
        "name": "Sadao",
        "location": "Upstream Station",
        "bank_full_capacity": 9.0,    # meters MSL
        "critical_threshold": 9.5,     # meters MSL
        "min_valid_level": -1.5,      # meters MSL
        "lat": 6.8500,
        "lon": 100.4200
    },
    "Kallayanamit": {
        "id": 2589,
        "code": "X.44",
        "name": "Bang Sala",
        "location": "Midstream Strategic Point",
        "bank_full_capacity": 10.0,    # meters MSL
        "critical_threshold": 10.5,   # meters MSL
        "min_valid_level": -1.8,      # meters MSL
        "lat": 6.9500,
        "lon": 100.4500
    }
}

# River Hydraulic Parameters
RIVER_HYDRAULICS = {
    # Khlong U-Tapao characteristics
    "sinuosity_factor": 1.4,          # River meandering factor (actual/straight distance)
    "straight_distance_km": 60.0,      # Sadao to Hat Yai straight-line distance
    "actual_distance_km": 84.0,        # Actual river path distance (60 * 1.4)
    "avg_cross_section_area": 150.0,  # m² (varies with water level)
    "mannings_n": 0.035,              # Manning's roughness coefficient
    "river_slope": 0.001,             # Average river gradient
    
    # Flow velocity parameters (m/s)
    "base_velocity_dry": 0.3,         # Base flow during dry season
    "base_velocity_normal": 0.8,      # Normal base flow
    "base_velocity_wet": 1.2,          # Base flow during wet season
    "max_velocity": 2.5,               # Maximum expected velocity
    
    # Lag time parameters
    "runoff_delay_hours": 8,          # Average runoff delay from upstream
    "min_lag_hours": 6,               # Minimum lag time
    "max_lag_hours": 12,              # Maximum lag time
}

# Rainfall Thresholds (mm)
RAINFALL_THRESHOLDS = {
    "light_daily": 10,                # < 10mm/day - light rain
    "moderate_daily": 30,              # 10-30mm/day - moderate
    "heavy_daily": 60,                 # 30-60mm/day - heavy
    "extreme_daily": 100,             # > 100mm/day - extreme
    "critical_24h": 150,              # Critical 24h accumulation
    "catastrophic_24h": 250,          # Catastrophic 24h accumulation
}

# Historical Flood Events (verified data)
HISTORICAL_EVENTS = {
    2010: {
        "rain_mm_24h": 520,
        "rain_mm_3d": 850,
        "peak_level": 12.5,
        "label": "2010 Great Flood",
        "severity": "CATASTROPHIC",
        "duration_hours": 72,
        "affected_areas": ["Hat Yai City", "Khlong R1", "PSU Campus"]
    },
    2017: {
        "rain_mm_24h": 280,
        "rain_mm_3d": 420,
        "peak_level": 10.8,
        "label": "2017 Severe Flood", 
        "severity": "SEVERE",
        "duration_hours": 48,
        "affected_areas": ["Hat Yai City Center", "Bang Sala"]
    },
    2022: {
        "rain_mm_24h": 180,
        "rain_mm_3d": 250,
        "peak_level": 10.2,
        "label": "2022 Flash Flood",
        "severity": "MODERATE", 
        "duration_hours": 24,
        "affected_areas": ["Low-lying areas", "Khlong U-Tapao banks"]
    }
}

# Risk Assessment Parameters
RISK_CALCULATION = {
    # Sigmoid function parameters for smooth risk calculation
    "sigmoid_k": 0.8,                 # Steepness factor
    "sigmoid_x0": 9.5,                # Inflection point (water level)
    
    # Weight factors for combined risk
    "water_level_weight": 0.6,        # 60% weight to water level
    "rainfall_weight": 0.4,           # 40% weight to rainfall
    
    # Risk level thresholds (percentage)
    "normal_max": 30,
    "warning_max": 70,
    "critical_min": 71,
}

# Emergency Response
EMERGENCY_CONTACTS = {
    "disaster_prevention": "1467",
    "hatyai_municipality": "074-236-111",
    "water_resources": "074-244-111",
    "hospital_emergency": "1669",
    "psu_security": "074-286-111"
}

EVACUATION_ZONES = {
    "high_priority": [
        "PSU Pumpkin Building Area",
        "Hat Yai City Center", 
        "Khlong R1 Riverside",
        "Bang Sala Low-lying Areas"
    ],
    "medium_priority": [
        "Residential Areas near Khlong U-Tapao",
        "Commercial District",
        "Industrial Zones"
    ],
    "safe_zones": [
        "PSU Main Campus (Elevated)",
        "Hat Yai Municipal Building",
        "Higher Ground Areas"
    ]
}

# API Configuration
API_CONFIG = {
    "thaiwater": {
        "url": "https://api-v3.thaiwater.net/api/v1/thaiwater30/public/waterlevel_load",
        "timeout": 5,
        "cache_minutes": 15
    },
    "rid": {
        "url": "http://119.110.213.190/rid/stations.php?IdCode=08:STN04",
        "timeout": 10,
        "cache_minutes": 10
    },
    "openmeteo": {
        "url": "https://api.open-meteo.com/v1/forecast",
        "timeout": 3,
        "cache_minutes": 60
    }
}

# System Configuration
SYSTEM_CONFIG = {
    "timezone": "Asia/Bangkok",
    "prediction_hours": 3,
    "historical_comparison_years": 5,
    "data_retention_days": 30,
    "alert_cooldown_minutes": 30
}

# Utility Functions
def calculate_actual_distance(straight_km: float, sinuosity: float) -> float:
    """Calculate actual river distance considering meandering."""
    return straight_km * sinuosity

def calculate_flow_velocity(water_level: float, bank_full: float, base_velocity: float) -> float:
    """
    Calculate flow velocity based on water level relative to bank full capacity.
    Uses Manning's equation simplified approach.
    """
    if water_level <= 0:
        return base_velocity * 0.5
    
    # Hydraulic radius increases with water level
    depth_ratio = min(water_level / bank_full, 1.5)
    velocity_factor = math.sqrt(depth_ratio)
    
    velocity = base_velocity * velocity_factor
    return min(velocity, RIVER_HYDRAULICS["max_velocity"])

def sigmoid_risk(water_level: float, k: float = None, x0: float = None) -> float:
    """
    Calculate risk using sigmoid function for smooth transitions.
    Returns risk percentage (0-100).
    """
    k = k or RISK_CALCULATION["sigmoid_k"]
    x0 = x0 or RISK_CALCULATION["sigmoid_x0"]
    
    # Normalize water level for sigmoid
    normalized_level = (water_level - 5.0) / 10.0  # Normalize around 5-15m range
    risk = 100 / (1 + math.exp(-k * (normalized_level - x0/10.0)))
    return max(0, min(100, risk))

def calculate_eta_hours(distance_km: float, velocity_ms: float, lag_hours: int = None) -> float:
    """Calculate estimated time of arrival in hours."""
    lag_hours = lag_hours or RIVER_HYDRAULICS["runoff_delay_hours"]
    
    # Convert distance to meters and calculate travel time
    distance_m = distance_km * 1000
    travel_time_hours = (distance_m / velocity_ms) / 3600
    
    return travel_time_hours + lag_hours
