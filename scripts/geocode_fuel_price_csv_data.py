import pandas as pd
import requests
import urllib.parse
import os
from pathlib import Path
from datetime import datetime

GOOGLE_API_KEY = ""

BASE_DIR = Path(__file__).parent.parent
input_csv  = BASE_DIR / "spotter" / "data" / "fuel-prices-for-be-assessment.csv"
output_csv = BASE_DIR / "spotter" / "data" / "fuel_prices_geocoded.csv"


def log(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def geocode_address(address, city, state):
    query = f"{address}, {city}, {state}"
    url = (
        f"https://maps.googleapis.com/maps/api/geocode/json"
        f"?address={urllib.parse.quote(query)}&key={GOOGLE_API_KEY}"
    )
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data["status"] == "OK" and data["results"]:
                loc = data["results"][0]["geometry"]["location"]
                return loc["lat"], loc["lng"]
            return None, f"API Status: {data.get('status')}"
        return None, f"HTTP Error: {response.status_code}"
    except Exception as e:
        return None, f"Exception: {str(e)}"


def main():
    chunk_size = 100

    if not GOOGLE_API_KEY:
        log("ERROR: GOOGLE_API_KEY is not set in config.")
        return

    if not input_csv.exists():
        log(f"ERROR: Cannot find {input_csv}")
        return

    log("Loading original CSV...")
    df = pd.read_csv(input_csv)
    total_original_rows = len(df)

    # --- DEDUPLICATE ---
    before = len(df)
    df = df.drop_duplicates(subset=["OPIS Truckstop ID", "Address", "City", "State"])
    log(f"Deduplication removed {before - len(df)} rows. {len(df)} unique stations remaining.")

    # --- NORMALIZE WHITESPACE ---
    str_cols = ["Address", "City", "State", "Truckstop Name"]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    log("Whitespace normalized.")

    # --- RESUME LOGIC ---
    processed_ids = set()
    if output_csv.exists():
        try:
            existing_df = pd.read_csv(output_csv)
            if "OPIS Truckstop ID" in existing_df.columns:
                processed_ids = set(existing_df["OPIS Truckstop ID"].unique())
                log(f"Resume state found. {len(processed_ids)} stations already geocoded.")
        except Exception as e:
            log(f"WARNING: Could not read existing output to resume: {e}")

    df_to_process = df[~df["OPIS Truckstop ID"].isin(processed_ids)]
    total_to_process = len(df_to_process)

    if total_to_process == 0:
        log("All stations already geocoded. Nothing to do.")
        return

    log(f"{total_to_process} stations remaining out of {total_original_rows} total.")

    buffer = []
    success_count = 0
    fail_count = 0

    for i, (index, row) in enumerate(df_to_process.iterrows(), start=1):
        lat, lng_or_err = geocode_address(row["Address"], row["City"], row["State"])

        if lat is not None:
            new_row = row.to_dict()
            new_row["Lat"] = lat
            new_row["Lng"] = lng_or_err
            buffer.append(new_row)
            success_count += 1
        else:
            log(f"FAILED: ID {row['OPIS Truckstop ID']} ({row['Address']}): {lng_or_err}")
            fail_count += 1

        if len(buffer) >= chunk_size or i == total_to_process:
            if buffer:
                chunk_df = pd.DataFrame(buffer)
                file_exists = output_csv.is_file()
                chunk_df.to_csv(output_csv, mode="a", header=not file_exists, index=False)
                buffer.clear()
            log(f"Progress: {i} / {total_to_process} processed.")

    log("Job complete.")
    log(f"Session summary: {success_count} succeeded, {fail_count} failed.")


if __name__ == "__main__":
    main()
