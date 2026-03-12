
import math

# Convierte grados a nombre de dirección (16 puntos)
def degrees_to_dir(deg):
    if deg is None:
        return None
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
            "S","SSO","SO","OSO","O","ONO","NO","NNO"]
    idx = round(deg / 22.5) % 16
    return dirs[idx]

# Diferencia angular entre dos direcciones en grados
def angle_diff(a, b):
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)

# Convierte nombre de dirección a grados
def dir_to_degrees(name):
    dirs = {"N":0,"NNE":22.5,"NE":45,"ENE":67.5,"E":90,"ESE":112.5,
            "SE":135,"SSE":157.5,"S":180,"SSO":202.5,"SO":225,
            "OSO":247.5,"O":270,"ONO":292.5,"NO":315,"NNO":337.5}
    return dirs.get(name, 0)

def score_spot(spot, conditions, hora=None):
    """
    Evalúa un spot dado unas condiciones y devuelve:
    - score: 0-100
    - semaforo: verde / amarillo / rojo
    - detalles: dict con razones
    """
    score = 0
    detalles = {}
    penalizaciones = []

    wave_h = conditions.get("wave_height", 0)
    wave_p = conditions.get("wave_period", 0)
    wave_dir_deg = conditions.get("wave_direction", 0)
    wind_dir_deg = conditions.get("wind_direction", 0)
    wind_speed = conditions.get("wind_speed", 0)  # nudos
    swell_h = conditions.get("swell_height", wave_h)
    swell_p = conditions.get("swell_period", wave_p)
    swell_dir_deg = conditions.get("swell_direction", wave_dir_deg)
    tide_state = conditions.get("tide_state", "Media")  # Pleamar / Media / Bajamar

    swell_dir = degrees_to_dir(swell_dir_deg)
    wind_dir = degrees_to_dir(wind_dir_deg)

    # ─── 1. ALTURA ───────────────────────────────────────────
    h_min = spot["height_min"]
    h_max = spot["height_max"]

    # Lógica especial Igueste: NE entra con menos
    if spot.get("special") == "igueste_logic" and swell_dir in ["NE","ENE","NNE"]:
        h_min = max(0.8, h_min - 0.8)

    if swell_h < h_min:
        penalizaciones.append(f"muy pequeño ({swell_h}m, mín {h_min}m)")
        detalles["altura"] = "insuficiente"
        score -= 40
    elif swell_h > h_max:
        penalizaciones.append(f"demasiado grande ({swell_h}m, máx {h_max}m)")
        detalles["altura"] = "excesivo"
        score -= 20
    else:
        # Puntuación proporcional dentro del rango óptimo
        rango = h_max - h_min
        centro = h_min + rango * 0.55
        dist = abs(swell_h - centro) / (rango / 2)
        pts = int(25 * (1 - min(dist, 1)))
        score += pts
        detalles["altura"] = f"ok ({swell_h}m)"

    # ─── 2. PERIODO ───────────────────────────────────────────
    p_min = spot["period_min"]
    p_max = spot["period_max"]

    # Montaña Amarilla: sweet spot 13-15s
    if spot.get("name") == "Montaña Amarilla" and 13 <= swell_p <= 15:
        score += 5

    if swell_p < p_min:
        penalizaciones.append(f"periodo corto ({swell_p}s, mín {p_min}s)")
        detalles["periodo"] = "insuficiente"
        score -= 25
    elif swell_p > p_max:
        detalles["periodo"] = f"ok largo ({swell_p}s)"
        score += 20
    else:
        pts = int(20 * ((swell_p - p_min) / max(p_max - p_min, 1)))
        score += pts
        detalles["periodo"] = f"ok ({swell_p}s)"

    # ─── 3. DIRECCIÓN DE SWELL ───────────────────────────────
    if swell_dir in spot["swell_dirs"]:
        score += 25
        detalles["swell"] = f"óptimo ({swell_dir})"
    else:
        # Penalización proporcional a la diferencia angular
        best_diff = min(
            angle_diff(swell_dir_deg, dir_to_degrees(d))
            for d in spot["swell_dirs"]
        )
        if best_diff <= 22.5:
            score += 12
            detalles["swell"] = f"aceptable ({swell_dir})"
        elif best_diff <= 45:
            score += 0
            detalles["swell"] = f"marginal ({swell_dir})"
            penalizaciones.append(f"swell {swell_dir} no ideal")
        else:
            score -= 30
            detalles["swell"] = f"dirección mala ({swell_dir})"
            penalizaciones.append(f"swell {swell_dir} no entra")

    # ─── 4. VIENTO ────────────────────────────────────────────
    if wind_dir in spot["wind_offshore"]:
        if wind_speed <= 10:
            score += 20
            detalles["viento"] = f"offshore perfecto ({wind_dir} {wind_speed:.0f}kts)"
        elif wind_speed <= 18:
            score += 12
            detalles["viento"] = f"offshore moderado ({wind_dir} {wind_speed:.0f}kts)"
        else:
            score += 5
            detalles["viento"] = f"offshore fuerte ({wind_dir} {wind_speed:.0f}kts)"
            penalizaciones.append("viento offshore demasiado fuerte")
    else:
        wind_diff = min(
            angle_diff(wind_dir_deg, dir_to_degrees(d))
            for d in spot["wind_offshore"]
        )
        if wind_speed <= 5:
            score += 10
            detalles["viento"] = f"calma ({wind_speed:.0f}kts)"
        elif wind_diff <= 45:
            score += 0
            detalles["viento"] = f"cruzado ({wind_dir} {wind_speed:.0f}kts)"
        elif wind_diff >= 135:
            penalty = min(25, int(wind_speed * 1.5))
            score -= penalty
            detalles["viento"] = f"onshore ({wind_dir} {wind_speed:.0f}kts)"
            penalizaciones.append(f"viento onshore {wind_dir}")
        else:
            score -= 8
            detalles["viento"] = f"lateral ({wind_dir} {wind_speed:.0f}kts)"

    # ─── 5. MAREA ─────────────────────────────────────────────
    if tide_state in spot["tides"]:
        score += 10
        detalles["marea"] = f"ok ({tide_state})"
    elif "Indiferente" in spot["tides"]:
        score += 10
        detalles["marea"] = "indiferente"
    else:
        score -= 10
        detalles["marea"] = f"no ideal ({tide_state})"
        penalizaciones.append(f"marea {tide_state} no es la mejor")

    # ─── 6. HORA (bonus morning para La Derecha) ──────────────
    if spot.get("special") == "morning_only" and hora is not None:
        if hora < 10:
            score += 10
            detalles["hora"] = "morning session ideal"
        elif hora >= 10:
            score -= 10
            detalles["hora"] = "mejor por la mañana temprano"

    # ─── SEMÁFORO ─────────────────────────────────────────────
    score = max(0, min(100, score))
    if score >= 65:
        semaforo = "verde"
    elif score >= 35:
        semaforo = "amarillo"
    else:
        semaforo = "rojo"

    return {
        "score": score,
        "semaforo": semaforo,
        "detalles": detalles,
        "penalizaciones": penalizaciones
    }
