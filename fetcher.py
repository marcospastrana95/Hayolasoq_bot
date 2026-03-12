
import requests
from datetime import datetime, timezone
import math

# ─── OPEN-METEO (previsión 7 días, gratis) ──────────────────────────────────

def get_openmeteo(lat, lon, days=7):
    """Devuelve datos horarios de Open-Meteo Marine para los próximos días."""
    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wave_height,wave_period,wave_direction,swell_wave_height,swell_wave_period,swell_wave_direction,wind_wave_height",
        "timezone": "Atlantic/Canary",
        "forecast_days": days
    }
    # Viento desde la API de tiempo estándar
    wind_url = "https://api.open-meteo.com/v1/forecast"
    wind_params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "windspeed_10m,winddirection_10m",
        "timezone": "Atlantic/Canary",
        "forecast_days": days,
        "windspeed_unit": "kn"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        marine = r.json()

        rw = requests.get(wind_url, params=wind_params, timeout=10)
        rw.raise_for_status()
        wind = rw.json()

        return parse_openmeteo(marine, wind)
    except Exception as e:
        print(f"[Open-Meteo] Error: {e}")
        return None

def parse_openmeteo(marine, wind):
    h = marine["hourly"]
    w = wind["hourly"]
    result = []
    for i, t in enumerate(h["time"]):
        result.append({
            "time": t,
            "source": "open-meteo",
            "wave_height": h["wave_height"][i],
            "wave_period": h["wave_period"][i],
            "wave_direction": h["wave_direction"][i],
            "swell_height": h["swell_wave_height"][i],
            "swell_period": h["swell_wave_period"][i],
            "swell_direction": h["swell_wave_direction"][i],
            "wind_speed": w["windspeed_10m"][i] if i < len(w["windspeed_10m"]) else None,
            "wind_direction": w["winddirection_10m"][i] if i < len(w["winddirection_10m"]) else None,
        })
    return result


# ─── STORMGLASS (hoy con precisión, requiere API key) ───────────────────────

def get_stormglass(lat, lon, api_key, date=None):
    """Devuelve datos horarios de Stormglass para hoy (más precisos)."""
    if not api_key or api_key == "TU_API_KEY_AQUI":
        print("[Stormglass] Sin API key, usando solo Open-Meteo.")
        return None

    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=0, microsecond=0)

    url = "https://api.stormglass.io/v2/weather/point"
    params = {
        "lat": lat,
        "lng": lon,
        "params": "waveHeight,wavePeriod,waveDirection,swellHeight,swellPeriod,swellDirection,windSpeed,windDirection",
        "source": "sg",
        "start": start.isoformat(),
        "end": end.isoformat()
    }
    headers = {"Authorization": api_key}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        return parse_stormglass(r.json())
    except Exception as e:
        print(f"[Stormglass] Error: {e}. Usando Open-Meteo.")
        return None

def parse_stormglass(data):
    result = []
    for h in data.get("hours", []):
        def sg(key):
            val = h.get(key, {})
            return val.get("sg") or (list(val.values())[0] if val else None)
        result.append({
            "time": h["time"][:16].replace("T", " "),
            "source": "stormglass",
            "wave_height": sg("waveHeight"),
            "wave_period": sg("wavePeriod"),
            "wave_direction": sg("waveDirection"),
            "swell_height": sg("swellHeight"),
            "swell_period": sg("swellPeriod"),
            "swell_direction": sg("swellDirection"),
            "wind_speed": sg("windSpeed"),      # m/s desde SG
            "wind_direction": sg("windDirection"),
        })
    # Convertir viento de m/s a nudos
    for r in result:
        if r["wind_speed"]:
            r["wind_speed"] = r["wind_speed"] * 1.94384
    return result


# ─── MAREAS (Open-Meteo no las da, cálculo aproximado) ──────────────────────

def get_tide_state(hour):
    """
    Aproximación simple de marea basada en ciclo semidiurno (12.4h).
    Para producción usar WorldTides API o tablademareas.com.
    """
    cycle = 12.4
    phase = (hour % cycle) / cycle
    height = math.cos(2 * math.pi * phase)
    if height > 0.4:
        return "Pleamar"
    elif height < -0.4:
        return "Bajamar"
    else:
        return "Media"


# ─── FUSIÓN DE DATOS ─────────────────────────────────────────────────────────

def get_conditions_for_spot(lat, lon, stormglass_key="TU_API_KEY_AQUI"):
    """
    Fusiona Stormglass (hoy, preciso) + Open-Meteo (resto de días).
    Devuelve lista de condiciones horarias.
    """
    openmeteo_data = get_openmeteo(lat, lon, days=7)
    stormglass_data = get_stormglass(lat, lon, stormglass_key)

    if not openmeteo_data:
        return []

    # Si tenemos Stormglass, sustituye las horas de hoy
    if stormglass_data:
        today = datetime.now().strftime("%Y-%m-%d")
        sg_by_hour = {d["time"][:13]: d for d in stormglass_data}

        result = []
        for entry in openmeteo_data:
            hour_key = entry["time"][:13]
            if entry["time"][:10] == today and hour_key in sg_by_hour:
                sg = sg_by_hour[hour_key].copy()
                sg["time"] = entry["time"]
                result.append(sg)
            else:
                result.append(entry)
        return result

    return openmeteo_data
