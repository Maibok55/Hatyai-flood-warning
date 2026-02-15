import sys
import os
sys.path.append(os.getcwd())

from models.flood_predictor import FloodPredictor
import pandas as pd
import time

def test_system():
    print("--- Starting System Test ---")
    
    # 1. Initialize
    try:
        predictor = FloodPredictor()
        print("[PASS] FloodPredictor initialized.")
    except Exception as e:
        print(f"[FAIL] Initialization failed: {e}")
        return

    # 2. Fetch Data
    print("\n--- Testing Data Fetching ---")
    try:
        data = predictor.fetch_and_store_data()
        print(f"Fetched Data: {data}")
        if data:
            print("[PASS] Data fetching successful (at least some data).")
        else:
            print("[WARN] Data fetching returned empty dict (might be network or parsing issue).")
    except Exception as e:
        print(f"[FAIL] Data fetching failed: {e}")

    # 3. Check Database
    print("\n--- Testing Database Storage ---")
    if os.path.exists("data/flood_data.db"):
        print("[PASS] Database file exists.")
        try:
            df = predictor.get_latest_data()
            print(f"Rows in DB (last 24h): {len(df)}")
            if not df.empty:
                print(df.head())
        except Exception as e:
            print(f"[FAIL] Database read failed: {e}")
    else:
        print("[FAIL] Database file not found.")

    # 4. Calculation & Prediction
    print("\n--- Testing Analytics ---")
    try:
        roc = predictor.calculate_rate_of_change()
        print(f"Rate of Change: {roc}")
        
        preds = predictor.predict_next_hours()
        print(f"Predictions: {preds}")
        print("[PASS] Analytics methods ran without error.")
    except Exception as e:
        print(f"[FAIL] Analytics failed: {e}")

if __name__ == "__main__":
    test_system()
