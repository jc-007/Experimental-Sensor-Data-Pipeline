"""Reproducible sensor ETL pipeline: simulation → validation → risk → SQL."""
from __future__ import annotations
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

LIMITS = {"temperature": (-20.0, 100.0), "pressure": (80.0, 120.0), "voltage": (0.0, 5.0)}
NORMAL = {"temperature": (15.0, 35.0), "pressure": (95.0, 105.0), "voltage": (3.0, 4.2)}
COLUMNS = ["sensor_id", "timestamp", "temperature", "pressure", "voltage"]


def generate(n: int = 1000, seed: int = 42) -> pd.DataFrame:
    if n < 1:
        raise ValueError("n must be >= 1")
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "sensor_id": [f"S{(i % 12) + 1:02d}" for i in range(n)],
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC"),
        "temperature": rng.normal(25, 5, n),
        "pressure": rng.normal(100, 3, n),
        "voltage": rng.normal(3.7, 0.25, n),
    })
    # Deliberately inject quality failures and abnormal-but-valid examples.
    if n >= 10:
        df.loc[0, "temperature"] = 120  # physically invalid
        df.loc[1, "pressure"] = np.nan  # missing
        df.loc[2, "voltage"] = -1  # physically invalid
        df.loc[3, "temperature"] = 48  # valid but abnormal
        df.loc[4, "voltage"] = 4.8  # valid but abnormal
    return df


def process(df: pd.DataFrame) -> pd.DataFrame:
    missing_cols = set(COLUMNS) - set(df.columns)
    if missing_cols:
        raise ValueError(f"Missing required columns: {sorted(missing_cols)}")
    out = df[COLUMNS].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out["sensor_id"] = out["sensor_id"].astype("string")
    reasons = []
    scores = []
    statuses = []
    for record in out.to_dict("records"):
        invalid = []
        abnormal = []
        if pd.isna(record["sensor_id"]) or not str(record["sensor_id"]).strip():
            invalid.append("missing_sensor_id")
        if pd.isna(record["timestamp"]):
            invalid.append("invalid_timestamp")
        for col, (low, high) in LIMITS.items():
            try:
                value = float(record[col])
                if not np.isfinite(value):
                    invalid.append(f"missing_or_nonfinite_{col}")
                elif not (low <= value <= high):
                    invalid.append(f"out_of_range_{col}")
                elif not (NORMAL[col][0] <= value <= NORMAL[col][1]):
                    abnormal.append(f"abnormal_{col}")
            except (TypeError, ValueError):
                invalid.append(f"non_numeric_{col}")
        if invalid:
            statuses.append("invalid")
            scores.append(None)  # not a trustworthy physical-risk estimate
        elif abnormal:
            statuses.append("abnormal")
            scores.append(min(100, 30 * len(abnormal)))
        else:
            statuses.append("normal")
            scores.append(0)
        reasons.append(";".join(invalid + abnormal))
    out["status"] = statuses
    out["risk_score"] = pd.array(scores, dtype="Int64")
    out["reasons"] = reasons
    return out


def persist(
    df: pd.DataFrame, db_path: str | Path, *, batch_id: str | None = None
) -> None:
    """Store readings, skipping a batch ID that has already been committed."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = df.copy()
    data["timestamp"] = data["timestamp"].astype(str)
    data["risk_score"] = data["risk_score"].astype(object).where(data["risk_score"].notna(), None)
    for col in LIMITS:
        data[col] = pd.to_numeric(data[col], errors="coerce").astype(object)
        data[col] = data[col].where(pd.notna(data[col]), None)
    with sqlite3.connect(path) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id TEXT, timestamp TEXT, temperature REAL,
            pressure REAL, voltage REAL, status TEXT NOT NULL,
            risk_score INTEGER, reasons TEXT NOT NULL)''')
        if batch_id is not None:
            conn.execute("CREATE TABLE IF NOT EXISTS ingested_batches (batch_id TEXT PRIMARY KEY)")
            claimed = conn.execute(
                "INSERT INTO ingested_batches (batch_id) VALUES (?) ON CONFLICT(batch_id) DO NOTHING",
                (batch_id,),
            )
            if claimed.rowcount == 0:
                return
        conn.executemany('''INSERT INTO readings
            (sensor_id,timestamp,temperature,pressure,voltage,status,risk_score,reasons)
            VALUES (?,?,?,?,?,?,?,?)''', data.itertuples(index=False, name=None))
        conn.execute("CREATE INDEX IF NOT EXISTS idx_readings_status ON readings(status)")


def summary(df: pd.DataFrame) -> dict:
    counts = df["status"].value_counts().to_dict()
    return {"total": len(df), "normal": counts.get("normal", 0),
            "abnormal": counts.get("abnormal", 0), "invalid": counts.get("invalid", 0),
            "invalid_pct": round(100 * counts.get("invalid", 0) / len(df), 2) if len(df) else 0.0}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the reproducible sensor data pipeline")
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--db", default="output/readings.sqlite")
    parser.add_argument("--csv", default="output/processed.csv")
    args = parser.parse_args()
    processed = process(generate(args.n, args.seed))
    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_data = processed.to_csv(index=False, lineterminator="\n").encode("utf-8")
    batch_id = hashlib.sha256(csv_data).hexdigest()
    persist(processed, args.db, batch_id=batch_id)
    csv_path.write_bytes(csv_data)
    print(json.dumps(summary(processed), indent=2))
    print(f"CSV: {csv_path} | SQLite: {args.db}")

if __name__ == "__main__":
    main()
