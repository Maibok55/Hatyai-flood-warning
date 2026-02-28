"""
HYFI Quality Assurance / Quality Control Module
================================================
Validates sensor data for: staleness, implausible jumps,
offline sensors, datum consistency, and logical errors.
Returns per-station QA flags + overall confidence score.
"""

from datetime import datetime, timezone, timedelta
from constants import STATION_METADATA


# ── QA Flag Constants ──────────────────────────────────────────
STALE_THRESHOLD_HOURS = 6       # Data older than this = stale
MAX_JUMP_M_PER_HOUR = 2.0      # Max plausible rise/fall per hour
MAX_DROP_M_PER_HOUR = 3.0      # Max plausible drop (faster than rise)


def compute_qa_flags(
    sensor_data: dict,
    rate_of_change: dict,
    last_update: datetime | None = None,
) -> dict:
    """
    Compute QA flags for all stations.
    
    Args:
        sensor_data:    result from fetch_and_store_data()
        rate_of_change: dict of {station_name: rate_m_per_h}
        last_update:    timestamp of most recent data
    
    Returns:
        {
            "stations": {
                "HatYai": {
                    "flags": ["ok"] | ["stale", "jump", ...],
                    "confidence": 0-100,
                    "details": "human-readable"
                }, ...
            },
            "overall_confidence": 0-100,
            "overall_status": "ok" | "degraded" | "critical"
        }
    """
    all_data = sensor_data.get("all_data", {})
    bank_info = sensor_data.get("bank_info", {})
    
    now_utc = datetime.now(timezone.utc)
    results = {"stations": {}, "overall_confidence": 100, "overall_status": "ok"}
    
    station_scores = []
    
    for station_name, meta in STATION_METADATA.items():
        flags = []
        details = []
        confidence = 100
        
        level = all_data.get(station_name)
        roc = rate_of_change.get(station_name, 0)
        
        # ── 1. Offline check ──
        if level is None:
            flags.append("offline")
            details.append(f"{station_name}: ไม่มีข้อมูล (sensor offline)")
            confidence = 0
            results["stations"][station_name] = {
                "flags": flags, "confidence": confidence, "details": "; ".join(details)
            }
            station_scores.append(confidence)
            continue
        
        # ── 2. Staleness check ──
        if last_update is not None:
            if last_update.tzinfo is None:
                # Assume Bangkok timezone
                import pytz
                bkk = pytz.timezone("Asia/Bangkok")
                last_update_aware = bkk.localize(last_update)
            else:
                last_update_aware = last_update
            
            age = now_utc - last_update_aware.astimezone(timezone.utc)
            if age > timedelta(hours=STALE_THRESHOLD_HOURS):
                flags.append("stale")
                hours_old = age.total_seconds() / 3600
                details.append(f"ข้อมูลเก่า {hours_old:.1f} ชม. (> {STALE_THRESHOLD_HOURS} ชม.)")
                confidence -= 30
        
        # ── 3. Implausible jump check ──
        if abs(roc) > MAX_JUMP_M_PER_HOUR:
            flags.append("jump")
            details.append(f"ระดับน้ำเปลี่ยน {roc:+.2f} m/h (เกิน ±{MAX_JUMP_M_PER_HOUR} m/h)")
            confidence -= 25
        
        # ── 4. Range validation ──
        min_valid = meta.get("min_valid_level", -5)
        max_valid = meta.get("bank_full_capacity", 20) + 5  # Allow 5m over bank
        if level < min_valid or level > max_valid:
            flags.append("out_of_range")
            details.append(f"ค่า {level:.2f}m อยู่นอกช่วง [{min_valid}, {max_valid}]")
            confidence -= 40
        
        # ── 5. Logical consistency: rising while situation_level says normal ──
        bi = bank_info.get(station_name, {})
        sit_level = bi.get("situation_level")
        if sit_level is not None and sit_level <= 1 and roc > 0.5:
            flags.append("logic_warn")
            details.append(f"API บอก situation={sit_level} (ปกติ) แต่น้ำเพิ่ม {roc:+.2f} m/h")
            confidence -= 10
        
        # ── 6. Datum check: ground_level from API vs constants ──
        api_ground = bi.get("ground_level")
        const_ground = meta.get("ground_level")
        if api_ground is not None and const_ground is not None:
            try:
                diff = abs(float(api_ground) - float(const_ground))
                if diff > 0.5:
                    flags.append("datum_mismatch")
                    details.append(
                        f"ground_level: API={api_ground}m ≠ config={const_ground}m (ต่าง {diff:.2f}m)"
                    )
                    confidence -= 20
            except (ValueError, TypeError):
                pass
        
        # ── Summarize ──
        if not flags:
            flags.append("ok")
            details.append("ข้อมูลปกติ")
        
        confidence = max(0, min(100, confidence))
        results["stations"][station_name] = {
            "flags": flags,
            "confidence": confidence,
            "details": "; ".join(details),
        }
        station_scores.append(confidence)
    
    # ── Overall ──
    if station_scores:
        results["overall_confidence"] = round(sum(station_scores) / len(station_scores))
    else:
        results["overall_confidence"] = 0
    
    if results["overall_confidence"] >= 80:
        results["overall_status"] = "ok"
    elif results["overall_confidence"] >= 50:
        results["overall_status"] = "degraded"
    else:
        results["overall_status"] = "critical"
    
    return results


def qa_badge(flags: list) -> str:
    """Return a single emoji badge for a list of QA flags."""
    if "offline" in flags:
        return "⚫"
    if "out_of_range" in flags or "datum_mismatch" in flags:
        return "🔴"
    if "stale" in flags or "jump" in flags:
        return "🟡"
    if "logic_warn" in flags:
        return "🟠"
    return "🟢"


def qa_summary_text(qa_result: dict, lang: str = "th") -> str:
    """One-line summary suitable for dashboard display."""
    conf = qa_result.get("overall_confidence", 0)
    status = qa_result.get("overall_status", "?")
    
    if lang == "th":
        status_map = {"ok": "ปกติ", "degraded": "คุณภาพลดลง", "critical": "มีปัญหา"}
        return f"คุณภาพข้อมูล: {status_map.get(status, status)} ({conf}%)"
    else:
        return f"Data Quality: {status.upper()} ({conf}%)"
