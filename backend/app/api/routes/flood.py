from fastapi import APIRouter
from app.ml.flood_model import flood_ml_service
from app.schemas.domain import FloodPredictionResult, FloodScenarioInput
from app.services.geo_service import geo_service

router = APIRouter()

@router.get("/status")
def get_flood_status():
    default_pred = flood_ml_service.predict(rainfall_mm=18.5, water_level_m=2.8)
    return {
        "region": "Bengaluru & Karnataka River Basins",
        "data_mode": "trained_model_inference",
        "current_assessment": default_pred,
        "monitoring_stations_active": len(geo_service.get_karnataka_gauges()),
        "catchments_mapped": len(geo_service.get_catchments_geojson().get("features", [])),
    }

@router.post("/forecast", response_model=FloodPredictionResult)
def run_flood_scenario_forecast(scenario: FloodScenarioInput):
    return flood_ml_service.predict(
        rainfall_mm=scenario.rainfall_mm,
        water_level_m=scenario.water_level_m,
        humidity_pct=scenario.humidity_pct,
        temperature_c=scenario.temperature_c,
    )

@router.get("/catchments")
def get_catchments():
    return geo_service.get_catchments_geojson()

@router.get("/gauges")
def get_river_gauges():
    return {
        "count": len(geo_service.get_karnataka_gauges()),
        "items": geo_service.get_karnataka_gauges(),
    }
