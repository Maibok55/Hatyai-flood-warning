from models.flood_predictor import FloodPredictor

def main():
    print("--- [DIAGNOSTIC] HAT YAI FLOOD SENTINEL ---")
    predictor = FloodPredictor()
    
    # 1. Fetch Rain Forecast
    print("\n[1] Testing Rain Forecast (Open-Meteo)...")
    rain_data = predictor.fetch_rain_forecast()
    print(f"    Rain Forecast (3 Days): {rain_data.get('rain_sum_3d', 'N/A')} mm")

    # 2. Fetch Sensor Data
    print("\n[2] Testing Sensor Data (ID-based matching)...")
    sensor_data = predictor.fetch_and_store_data()
    print(f"    Primary Station: {sensor_data.get('station_name', 'N/A')}")
    print(f"    Primary Level: {sensor_data.get('level', 'N/A')} m")
    print(f"    Is Fallback: {sensor_data.get('is_fallback', 'N/A')}")
    print(f"    All Data: {sensor_data.get('all_data', {})}")
    
    # 3. Analyze Risk
    print("\n[3] Testing Risk Intelligence Engine...")
    risk_report = predictor.analyze_flood_risk(sensor_data, rain_data)
    print(f"    Alert Level: {risk_report['alert_level']}")
    print(f"    Risk: {risk_report['primary_risk']}%")
    print(f"    Message: {risk_report['main_message']}")
    print(f"    Source: {risk_report['data_source']}")
    print(f"    Confidence: {risk_report['confidence_score']}%")
    
    print("\n--- DIAGNOSTIC COMPLETE ---")

if __name__ == "__main__":
    main()