
import requests
from datetime import datetime, timezone
import math

# ─── ZONAS DE CONSULTA API ───────────────────────────────────────────────────
# Máximo 4 llamadas Stormglass/día (límite gratuito = 10/día)
# En modo SMART solo se hace 1 llamada a la zona más prometedora

ZONAS = {
    "tenerife": {
        "anaga": (28.5719, -16.1929),   # Almáciga, Roque, Igueste
        "norte": (28.5756, -16.3289),   # El Callado
        "sur":   (28.0523, -16.7198),   # Gaviotas, Las Américas
    },
    "graciosa": (29.2500, -13.5100),    # Punto central único
}

SPOT_ZONA = {
    "Almáciga":                   ("tenerife", "anaga"),
    "Roque de las Bodegas":       ("tenerife", "anaga"),
    "Igueste":                    ("tenerife", "anaga"),
    "El Callado":                 ("tenerife", "norte"),
    "Las Gaviotas":               ("tenerife", "sur"),
    "La Derecha de Las Américas": ("tenerife", "sur"),
}

# Zonas donde funciona cada dirección de swell
SWELL_ZONA_MAP = {
    # Dirección swell (rango) → zonas de Tenerife que más se benefician
    "N":   ["anaga", "norte"],
    "NNE": ["anaga", "norte"],
    "NE":  ["anaga"],
    "ENE": ["anaga"],
    "NNO": ["anaga", "norte"],
    "NO":  ["norte", "sur"],
    "ONO": ["sur"],
    "O":   ["sur"],
    "S":   ["sur"],
    "SSO": ["sur"],
    "SO":  ["sur"],
}


# ─── OPEN-METEO (gratis, ilimitado, 7 días) ──────────────────────────────────

def get_openmeteo(lat, lon, days=7):
    """Datos horarios de Open-Meteo Marine + viento."""
    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "wave_height,wave_period,wave_direction,"
                  "swell_wave_height,swell_wave_period,swell_wave_direction",
        "timezone": "Atlantic/Canary",
        "forecast_days": days
    }
    wind_url = "https://api.open-meteo.com/v1/forecast"
    wind_params = {
        "latitude": lat, "longitude": lon,
        "hourly": "windspeed_10m,winddirection_10m",
        "timezone": "Atlantic/Canary",
        "forecast_days": days,
        "windspeed_unit": "kn"
    }
    try:
        r  = requests.get(url,      params=params,      timeout=10); r.raise_for_status()
        rw = requests.get(wind_url, params=wind_params, timeout=10); rw.raise_for_status()
        return _parse_openmeteo(r.json(), rw.json())
    except Exception as e:
        print(f"[Open-Meteo] Error: {e}")
        return None

def _parse_openmeteo(marine, wind):
    h, w = marine["hourly"], wind["hourly"]
    return [{
        "time":            t,
        "source":          "open-meteo",
        "wave_height":     h["wave_height"][i],
        "wave_period":     h["wave_period"][i],
        "wave_direction":  h["wave_direction"][i],
        "swell_height":    h["swell_wave_height"][i],
        "swell_period":    h["swell_wave_period"][i],
        "swell_direction": h["swell_wave_direction"][i],
        "wind_speed":      w["windspeed_10m"][i]    if i < len(w["windspeed_10m"])    else None,
        "wind_direction":  w["winddirection_10m"][i] if i < len(w["winddirection_10m"]) else None,
    } for i, t in enumerate(h["time"])]


# ─── STORMGLASS (hoy preciso, 10 llamadas/día gratis) ────────────────────────

# Códigos de error de Stormglass que indican límite agotado
_SG_QUOTA_ERRORS = {402, 429}

# Flag en memoria para saber si SG está agotado hoy
_stormglass_exhausted = False

def stormglass_available(api_key):
    """True si la key existe y no se ha agotado la cuota hoy."""
    return (
        bool(api_key)
        and api_key != "TU_API_KEY_AQUI"
        and not _stormglass_exhausted
    )

def get_stormglass(lat, lon, api_key):
    """
    Datos horarios de Stormglass para hoy.
    - Devuelve None si no hay key, cuota agotada o error de red.
    - Marca _stormglass_exhausted si recibe 402/429.
    """
    global _stormglass_exhausted
    if not stormglass_available(api_key):
        return None

    now   = datetime.now(timezone.utc)
    start = now.replace(hour=0,  minute=0,  second=0, microsecond=0)
    end   = now.replace(hour=23, minute=59, second=0, microsecond=0)

    try:
        r = requests.get(
            "https://api.stormglass.io/v2/weather/point",
            params={
                "lat": lat, "lng": lon,
                "params": "waveHeight,wavePeriod,waveDirection,"
                          "swellHeight,swellPeriod,swellDirection,"
                          "windSpeed,windDirection",
                "source": "sg",
                "start":  start.isoformat(),
                "end":    end.isoformat(),
            },
            headers={"Authorization": api_key},
            timeout=15
        )
        if r.status_code in _SG_QUOTA_ERRORS:
            _stormglass_exhausted = True
            print(f"[Stormglass] Cuota agotada (HTTP {r.status_code}). Usando solo Open-Meteo.")
            return None
        r.raise_for_status()
        return _parse_stormglass(r.json())
    except Exception as e:
        print(f"[Stormglass] Error: {e}. Fallback a Open-Meteo.")
        return None

def _parse_stormglass(data):
    def sg(h, key):
        val = h.get(key, {})
        return val.get("sg") or (list(val.values())[0] if val else None)

    result = []
    for h in data.get("hours", []):
        entry = {
            "time":             h["time"][:16].replace("T", " "),
            "source":           "stormglass",
            "wave_height":      sg(h, "waveHeight"),
            "wave_period":      sg(h, "wavePeriod"),
            "wave_direction":   sg(h, "waveDirection"),
            # Swell 1 (dominante)
            "swell_height":     sg(h, "swellHeight"),
            "swell_period":     sg(h, "swellPeriod"),
            "swell_direction":  sg(h, "swellDirection"),
            # Swell 2 (secundario)
            "swell2_height":    sg(h, "secondarySwellHeight"),
            "swell2_period":    sg(h, "secondarySwellPeriod"),
            "swell2_direction": sg(h, "secondarySwellDirection"),
            # Swell 3 (terciario)
            "swell3_height":    sg(h, "tertiarySwellHeight"),
            "swell3_period":    sg(h, "tertiarySwellPeriod"),
            "swell3_direction": sg(h, "tertiarySwellDirection"),
            "wind_speed":       sg(h, "windSpeed"),
            "wind_direction":   sg(h, "windDirection"),
        }
        # SG da viento en m/s → convertir a nudos
        if entry["wind_speed"]:
            entry["wind_speed"] *= 1.94384
        result.append(entry)
    return result


# ─── MAREAS (aproximación semidiurna) ────────────────────────────────────────

def get_tide_state(hour):
    """Ciclo semidiurno 12.4h. Para mayor precisión usar WorldTides API."""
    phase = (hour % 12.4) / 12.4
    height = math.cos(2 * math.pi * phase)
    if height > 0.4:   return "Pleamar"
    if height < -0.4:  return "Bajamar"
    return "Media"


# ─── FUSIÓN STORMGLASS + OPEN-METEO ──────────────────────────────────────────

def get_conditions_for_spot(lat, lon, stormglass_key):
    """
    Fusiona Stormglass (hoy, preciso) + Open-Meteo (7 días).
    Si SG no está disponible, usa solo Open-Meteo.
    """
    om_data = get_openmeteo(lat, lon, days=7)
    if not om_data:
        return []

    sg_data = get_stormglass(lat, lon, stormglass_key)
    if not sg_data:
        return om_data   # fallback limpio a Open-Meteo

    # Stormglass disponible: sustituye horas de hoy
    today      = datetime.now().strftime("%Y-%m-%d")
    sg_by_hour = {d["time"][:13]: d for d in sg_data}

    merged = []
    for entry in om_data:
        hour_key = entry["time"][:13]
        if entry["time"][:10] == today and hour_key in sg_by_hour:
            sg = sg_by_hour[hour_key].copy()
            sg["time"] = entry["time"]
            merged.append(sg)
        else:
            merged.append(entry)
    return merged


# ─── MODO SMART: solo 1 llamada Stormglass ───────────────────────────────────

def get_best_zone_for_island(island, stormglass_key):
    """
    MODO SMART (briefing diario):
    1. Consulta Open-Meteo gratis para ver el swell actual
    2. Deduce qué zona de la isla tiene más papeletas
    3. Hace 1 sola llamada a Stormglass para esa zona
    Devuelve (zona_nombre, hourly_data)
    """
    from scorer import score_spot, degrees_to_dir
    from spots import SPOTS

    if island == "graciosa":
        lat, lon = ZONAS["graciosa"]
        data = get_conditions_for_spot(lat, lon, stormglass_key)
        return ("La Graciosa", data)

    # 1. Sondeo rápido con Open-Meteo en punto central de Tenerife
    probe_lat, probe_lon = 28.52, -16.30
    probe_data = get_openmeteo(probe_lat, probe_lon, days=1)
    if not probe_data:
        # Sin datos, usar anaga por defecto
        lat, lon = ZONAS["tenerife"]["anaga"]
        return ("anaga", get_conditions_for_spot(lat, lon, stormglass_key))

    # 2. Coger condiciones de las 10:00
    today = datetime.now().strftime("%Y-%m-%d")
    ref = next((e for e in probe_data if e["time"].startswith(today + "T10")), probe_data[0])
    swell_dir_deg = ref.get("swell_direction") or ref.get("wave_direction") or 0
    swell_dir_str = degrees_to_dir(swell_dir_deg)

    # 3. Determinar qué zonas reciben mejor ese swell
    candidate_zonas = SWELL_ZONA_MAP.get(swell_dir_str, ["anaga"])

    # 4. Score rápido de cada zona candidata con Open-Meteo (sin gastar SG)
    best_zona = candidate_zonas[0]
    best_score = -1
    for zona in candidate_zonas:
        lat, lon = ZONAS["tenerife"][zona]
        om = get_openmeteo(lat, lon, days=1)
        if not om:
            continue
        ref2 = next((e for e in om if e["time"].startswith(today + "T10")), om[0])
        # Score rápido: solo el primer spot de esa zona
        zona_spots = [s for s in SPOTS["tenerife"]
                      if SPOT_ZONA.get(s["name"], ("", ""))[1] == zona]
        if zona_spots:
            from scorer import score_spot
            hour = int(ref2["time"][11:13]) if "T" in ref2["time"] else 10
            r = score_spot(zona_spots[0], {**ref2, "tide_state": get_tide_state(hour)}, hora=hour)
            if r["score"] > best_score:
                best_score = r["score"]
                best_zona  = zona

    # 5. Ahora sí, 1 sola llamada Stormglass para la mejor zona
    lat, lon = ZONAS["tenerife"][best_zona]
    data = get_conditions_for_spot(lat, lon, stormglass_key)
    return (best_zona, data)


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def get_conditions_for_island(island, stormglass_key):
    """
    MODO COMPLETO: 4 llamadas Stormglass (bajo demanda del usuario).
    Tenerife = 3 zonas, La Graciosa = 1 punto central.
    """
    if island == "graciosa":
        lat, lon = ZONAS["graciosa"]
        return {"central": get_conditions_for_spot(lat, lon, stormglass_key)}
    result = {}
    for zona, (lat, lon) in ZONAS["tenerife"].items():
        result[zona] = get_conditions_for_spot(lat, lon, stormglass_key)
    return result

def get_hourly_for_spot(spot_name, island, all_conditions):
    """Devuelve los datos horarios correctos para un spot."""
    if island == "graciosa":
        return all_conditions.get("central", [])
    zona_key = SPOT_ZONA.get(spot_name, ("tenerife", "anaga"))
    return all_conditions.get(zona_key[1], [])
