"""
HYFI Data Ingestion & Provenance Module
========================================
Tracks every API call: source, endpoint, status, raw payload backup.
Immutable log — raw payloads saved to data/raw/{source}_{utc_ts}.json
Latest provenance summary in data/last_fetch.json
"""

import json
import os
import hashlib
from datetime import datetime, timezone

# ── Paths ──────────────────────────────────────────────────────
DATA_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PROV_PATH  = os.path.join(DATA_DIR, "last_fetch.json")
RAW_DIR    = os.path.join(DATA_DIR, "raw")

# ── Provenance Writer ──────────────────────────────────────────

def write_provenance(
    source: str,
    endpoint: str,
    station_ids: list | str,
    payload: dict | list | None,
    status: str = "ok",
    extra: dict | None = None,
) -> str:
    """
    Record a data fetch event.
    
    Args:
        source:      e.g. "thaiwater", "openmeteo"
        endpoint:    full URL called
        station_ids: station ID(s) fetched
        payload:     raw API response (saved to raw/)
        status:      "ok" | "error" | "timeout" | "cached"
        extra:       any extra metadata (e.g. {"cache_age_min": 12})
    
    Returns:
        Path to the saved raw payload file (or "" if payload was None).
    """
    os.makedirs(RAW_DIR, exist_ok=True)
    utc_now = datetime.now(timezone.utc)
    ts_iso  = utc_now.strftime("%Y-%m-%dT%H:%M:%SZ")
    ts_file = utc_now.strftime("%Y%m%dT%H%M%SZ")

    # ── Save raw payload (immutable) ──
    raw_path = ""
    if payload is not None:
        raw_path = os.path.join(RAW_DIR, f"{source}_{ts_file}.json")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, default=str, ensure_ascii=False, indent=2)

    # ── Compute payload fingerprint (for dedup / integrity check) ──
    fingerprint = ""
    if payload is not None:
        payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode()
        fingerprint = hashlib.sha256(payload_bytes).hexdigest()[:16]

    # ── Update provenance summary (last_fetch.json) ──
    prov = _read_provenance_file()

    record = {
        "source":       source,
        "endpoint":     endpoint,
        "station_ids":  station_ids if isinstance(station_ids, list) else [station_ids],
        "fetched_utc":  ts_iso,
        "status":       status,
        "fingerprint":  fingerprint,
        "raw_file":     os.path.basename(raw_path) if raw_path else None,
    }
    if extra:
        record["extra"] = extra

    prov[source] = record

    with open(PROV_PATH, "w", encoding="utf-8") as f:
        json.dump(prov, f, default=str, ensure_ascii=False, indent=2)

    return raw_path


# ── Provenance Reader ──────────────────────────────────────────

def read_provenance() -> dict:
    """Read the latest provenance summary. Returns {} if none yet."""
    return _read_provenance_file()


def _read_provenance_file() -> dict:
    if os.path.exists(PROV_PATH):
        try:
            with open(PROV_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


# ── Raw Payload Cleanup (optional, keep last N per source) ──

def cleanup_raw(source: str, keep_last: int = 48):
    """
    Keep only the most recent `keep_last` raw files per source.
    Default 48 = ~2 days if fetching every hour.
    """
    if not os.path.isdir(RAW_DIR):
        return
    files = sorted(
        [f for f in os.listdir(RAW_DIR) if f.startswith(f"{source}_") and f.endswith(".json")],
        reverse=True,
    )
    for old in files[keep_last:]:
        try:
            os.remove(os.path.join(RAW_DIR, old))
        except OSError:
            pass
