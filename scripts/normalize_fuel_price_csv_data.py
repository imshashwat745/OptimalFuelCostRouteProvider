import pandas as pd
from pathlib import Path

data_dir = Path(__file__).parent.parent / "spotter" / "data"
csv_path = data_dir / "fuel_prices_geocoded.csv"

df = pd.read_csv(csv_path)
print(f"Loaded {len(df)} rows from {csv_path}")

str_cols = ["Address", "City", "State", "Truckstop Name"]
for col in str_cols:
    if col in df.columns:
        df[col] = df[col].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)

df.to_csv(csv_path, index=False)
print("Normalized and saved in place.")
