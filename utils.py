"""
HYFI Utility Functions
"""
import base64, os
from constants import STATION_METADATA

# Default thresholds from HatYai
_HATYAI = STATION_METADATA.get('HatYai', {})
CRITICAL_LEVEL = _HATYAI.get('critical_threshold', 8.88)
WARNING_LEVEL = _HATYAI.get('warning_threshold', 7.38)

_ICON_DIR = os.path.join(os.path.dirname(__file__), "static", "icons")
_ICON_CACHE = {}

def icon_b64(name):
    """Return base64-encoded data URI for an icon in static/icons/."""
    if name not in _ICON_CACHE:
        path = os.path.join(_ICON_DIR, name)
        try:
            with open(path, "rb") as f:
                _ICON_CACHE[name] = f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
        except Exception:
            _ICON_CACHE[name] = ""
    return _ICON_CACHE[name]

def fmt(v):
    """Safe formatting for sensor values that may be None."""
    return f"{v:.2f}" if v is not None else "—"

def _dot_html(color):
    return f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{color};margin-right:4px;vertical-align:middle;"></span>'

def dot(v, station_name=None):
    """Status indicator dot for a sensor value, station-aware."""
    if v is None: return _dot_html("#cbd5e1")
    
    crit = CRITICAL_LEVEL
    warn = WARNING_LEVEL
    
    if station_name and station_name in STATION_METADATA:
        meta = STATION_METADATA[station_name]
        crit = meta.get('critical_threshold', crit)
        warn = meta.get('warning_threshold', warn)
    
    if v > crit: return _dot_html("#ef4444")
    if v > warn: return _dot_html("#eab308")
    return _dot_html("#22c55e")
