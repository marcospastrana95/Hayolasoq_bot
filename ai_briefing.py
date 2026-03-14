"""
ai_briefing.py v3 — Claude toma decisiones reales sobre el surf del día.

La IA recibe:
  - Datos horarios completos (6h-20h) de todos los spots
  - Conocimiento real de cada pico (swell óptimo, offshore, marea, nivel)
  - Scores calculados por spot

La IA decide:
  - Si merece la pena salir (SI/NO directo)
  - Cuál es el mejor spot y por qué
  - Hora exacta óptima
  - Qué tener en cuenta (seguridad, marea, viento)
"""

import os
import logging
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-haiku-4-5-20251001"

# ─── CONOCIMIENTO REAL DE CADA SPOT ──────────────────────────────────────────
# Fuente: documento Drive "02-Spots de surf" + spots.py
# Esto es lo que diferencia un análisis genérico de uno útil de verdad.

SPOT_KNOWLEDGE = {
    # ── TENERIFE ──────────────────────────────────────────────────────────────
    "Almáciga": {
        "zona": "Anaga", "tipo": "beach_break",
        "swell_optimo": "NW/N", "swell_grados": (270, 360),
        "periodo_min": 8, "offshore": "S/SW", "offshore_grados": (150, 240),
        "marea": "media-alta", "tam_min": 0.6, "tam_max": 1.8, "nivel": "intermedio",
        "nota": "Protegida de vientos del norte por acantilados de Anaga. Bancos de arena variables.",
    },
    "Roque de las Bodegas": {
        "zona": "Anaga", "tipo": "beach_break",
        "swell_optimo": "N/NW", "swell_grados": (280, 360),
        "periodo_min": 10, "offshore": "NE/E", "offshore_grados": (35, 110),
        "marea": "media-baja", "tam_min": 1.5, "tam_max": 2.2, "nivel": "avanzado",
        "nota": "Beach break increible pero exigente. Depende mucho de los bancos de arena.",
    },
    "Igueste": {
        "zona": "Anaga", "tipo": "point_break",
        "swell_optimo": "NNE/NE (rodea Anaga)", "swell_grados": (0, 60),
        "periodo_min": 8, "offshore": "NNE/N", "offshore_grados": (340, 60),
        "marea": "pleamar/media", "tam_min": 0.8, "tam_max": 10.0, "nivel": "avanzado",
        "nota": "Con NE entra con menos tamanio. Con mareas vivas (coef>70) la ola es mas potente. Spot secreto.",
    },
    "Las Gaviotas": {
        "zona": "Norte", "tipo": "beach_break",
        "swell_optimo": "S/SW", "swell_grados": (170, 240),
        "periodo_min": 10, "offshore": "NW/N", "offshore_grados": (290, 360),
        "marea": "media", "tam_min": 1.0, "tam_max": 2.0, "nivel": "intermedio",
        "nota": "Necesita swell del sur limpio. Muy expuesto al viento.",
    },
    "El Callado": {
        "zona": "Norte", "tipo": "point_break",
        "swell_optimo": "NW/N", "swell_grados": (270, 360),
        "periodo_min": 10, "offshore": "NE/E", "offshore_grados": (25, 115),
        "marea": "media", "tam_min": 1.5, "tam_max": 2.0, "nivel": "avanzado",
        "nota": "Point break largo. Aguanta mas tamanio que otros del norte.",
    },
    "La Derecha de Las Américas": {
        "zona": "Sur", "tipo": "reef_break",
        "swell_optimo": "NNO/NO/ONO", "swell_grados": (290, 350),
        "periodo_min": 14, "offshore": "E/SE", "offshore_grados": (80, 160),
        "marea": "bajamar/media", "tam_min": 1.5, "tam_max": 3.0, "nivel": "avanzado",
        "nota": "Mejor early session antes de las 10h. Con swell del sur NO funciona.",
    },
    # ── LA GRACIOSA ───────────────────────────────────────────────────────────
    "El Corral": {
        "zona": "Noroeste Graciosa", "tipo": "reef_break",
        "swell_optimo": "ONO/NO/O (groundswell)", "swell_grados": (270, 330),
        "periodo_min": 11, "offshore": "ESE/SE/E", "offshore_grados": (100, 155),
        "marea": "cualquiera", "tam_min": 0.8, "tam_max": 2.2, "nivel": "experto",
        "nota": "La mejor izquierda de Canarias. Fondo de arrecife peligroso. Solo con offshore del E/SE.",
    },
    "Medusa": {
        "zona": "Noroeste Graciosa", "tipo": "reef_break",
        "swell_optimo": "NO/NNO/ONO", "swell_grados": (280, 340),
        "periodo_min": 11, "offshore": "NE/E", "offshore_grados": (25, 90),
        "marea": "media-alta", "tam_min": 0.5, "tam_max": 1.5, "nivel": "avanzado",
        "nota": "Slab divertido para giros cuando esta pequeño.",
    },
    "Baja del Ganado": {
        "zona": "Noroeste Graciosa", "tipo": "point_break",
        "swell_optimo": "N/NNO/NO", "swell_grados": (320, 20),
        "periodo_min": 12, "offshore": "NE/E", "offshore_grados": (25, 90),
        "marea": "media-alta", "tam_min": 1.5, "tam_max": 2.0, "nivel": "experto",
        "nota": "Derecha muy larga. Mar del norte entra bien colocado.",
    },
    "La Francesa": {
        "zona": "Sur Graciosa", "tipo": "reef_break",
        "swell_optimo": "O/ONO/NO", "swell_grados": (260, 320),
        "periodo_min": 14, "offshore": "NO/NNO/N", "offshore_grados": (300, 360),
        "marea": "media-alta", "tam_min": 1.8, "tam_max": 10.0, "nivel": "experto",
        "nota": "Mejor con mareas vivas cuando esta grande. Cuanto mas sube mejor.",
    },
    "Montaña Amarilla": {
        "zona": "Suroeste Graciosa", "tipo": "reef_break",
        "swell_optimo": "ONO/NO/O", "swell_grados": (265, 315),
        "periodo_min": 13, "offshore": "NE/NNE", "offshore_grados": (15, 65),
        "marea": "bajamar-media", "tam_min": 1.5, "tam_max": 2.5, "nivel": "avanzado",
        "nota": "Sweet spot 13-15s. No necesita mucho tamanio pero si periodo.",
    },
    "Las Conchas": {
        "zona": "Norte Graciosa", "tipo": "beach_break",
        "swell_optimo": "NNE/N/NNO", "swell_grados": (340, 60),
        "periodo_min": 9, "offshore": "NE/E", "offshore_grados": (25, 90),
        "marea": "bajamar", "tam_min": 1.5, "tam_max": 3.0, "nivel": "avanzado",
        "nota": "Solo funciona cuando la playa esta plana (tras borrascas seguidas del oeste).",
    },
    "El Hueso": {
        "zona": "Norte Graciosa", "tipo": "reef_break",
        "swell_optimo": "N/NNO/NO", "swell_grados": (300, 20),
        "periodo_min": 10, "offshore": "SW/W", "offshore_grados": (210, 280),
        "marea": "media-baja", "tam_min": 1.5, "tam_max": 3.0, "nivel": "experto",
        "nota": "",
    },
    "El Basurero": {
        "zona": "Norte Graciosa", "tipo": "reef_break",
        "swell_optimo": "N/NNO/NO", "swell_grados": (300, 20),
        "periodo_min": 14, "offshore": "NE/E", "offshore_grados": (25, 90),
        "marea": "media-baja", "tam_min": 1.5, "tam_max": 2.4, "nivel": "experto",
        "nota": "Necesita periodo largo (>14s) para funcionar bien.",
    },
    "La Alambra": {
        "zona": "NE Graciosa", "tipo": "rock_break",
        "swell_optimo": "N/NNE/NNO/NO", "swell_grados": (310, 50),
        "periodo_min": 10, "offshore": "ONO/O/SW/S", "offshore_grados": (200, 300),
        "marea": "cualquiera", "tam_min": 1.5, "tam_max": 3.0, "nivel": "avanzado",
        "nota": "",
    },
}


# ─── CONSTRUCCIÓN DEL PROMPT ──────────────────────────────────────────────────

def _build_prompt(island, day_str, spots_data, hourly, tide_data=None):
    day_label    = datetime.strptime(day_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    dias_es      = ["Lunes","Martes","Miercoles","Jueves","Viernes","Sabado","Domingo"]
    meses_es     = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
                    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    d            = datetime.strptime(day_str, "%Y-%m-%d")
    day_label    = f"{dias_es[d.weekday()]} {d.day} {meses_es[d.month]}"
    island_label = "Tenerife" if island == "tenerife" else "La Graciosa"

    # ── Bloque conocimiento spots ─────────────────────────────────────────────
    k_lines = []
    for s in spots_data:
        k = _get_knowledge(s["name"])
        if not k:
            continue
        k_lines.append(
            f"  [{s['name']}] zona={k['zona']} tipo={k['tipo']} "
            f"swell_optimo={k['swell_optimo']} periodo_min={k['periodo_min']}s "
            f"offshore={k['offshore']} marea_optima={k['marea']} "
            f"tam={k['tam_min']}-{k['tam_max']}m nivel={k['nivel']}"
            + (f" | NOTA: {k['nota']}" if k['nota'] else "")
        )
    k_block = "\n".join(k_lines) or "  (sin info)"

    # ── Bloque condiciones actuales ───────────────────────────────────────────
    c_lines = []
    for s in spots_data:
        pens = " / ".join(s.get("penalizaciones", [])[:3]) or "ninguna"
        c_lines.append(
            f"  [{s['name']}] score={s['score']}/100 ({s['semaforo']}) "
            f"olas={s['sh']:.1f}m {s['sp']:.0f}s dir={s['sd']} "
            f"viento={s['ws']:.0f}kts dir={s['wd']} "
            f"marea={s.get('marea','?')} | penalizaciones: {pens}"
        )
    c_block = "\n".join(c_lines) or "  (sin datos)"

    # ── Bloque horario 6h-20h ─────────────────────────────────────────────────
    h_lines = []
    for e in sorted(hourly, key=lambda x: x.get("time","")):
        if not e["time"].startswith(day_str):
            continue
        try:
            t  = e["time"]
            hh = int(t[11:13]) if "T" in t else int(t[8:10])
            if not (6 <= hh <= 20):
                continue
            sh = e.get("swell_height") or e.get("wave_height") or 0
            sp = e.get("swell_period") or e.get("wave_period") or 0
            sd = e.get("swell_direction") or e.get("wave_direction") or 0
            ws = e.get("wind_speed") or 0
            wd = e.get("wind_direction") or 0
            h_lines.append(
                f"  {hh:02d}h: {sh:.1f}m {sp:.0f}s swell={sd:.0f}deg "
                f"viento={ws:.0f}kts dir={wd:.0f}deg"
            )
        except Exception:
            pass
    h_block = "\n".join(h_lines) or "  (sin datos horarios)"

    # ── Bloque mareas ─────────────────────────────────────────────────────────
    tide_block = ""
    if tide_data:
        coef = tide_data.get("coef", "?")
        label = tide_data.get("label", "")
        events = tide_data.get("events", [])
        ev_str = " / ".join(
            f"{ev['type']} {ev['time']}" for ev in events
        ) if events else "no disponible"
        tide_block = f"\nMAREAS: coef={coef} {label} | eventos: {ev_str}"

    return f"""Eres el mejor surfero de Canarias. Conoces cada spot al dedillo.
Tu trabajo: leer los datos del dia y dar una decision clara y util.
Responde en espanol informal. Directo. Sin pajas mentales.

=== {island_label} — {day_label} ==={tide_block}

CONOCIMIENTO DE LOS SPOTS:
{k_block}

CONDICIONES HOY POR SPOT (scores calculados):
{c_block}

EVOLUCION HORARIA (6h-20h):
{h_block}

=== TU DECISION ===

Responde EXACTAMENTE con este formato (sin asteriscos, sin markdown, texto plano):

MERECE LA PENA: SI / NO
MEJOR SPOT: [nombre del spot o "ninguno"]
HORA IDEAL: [ej: 09h-12h, o "no hay ventana buena"]
POR QUE: [2-3 frases maximo — razona con datos: swell, viento, marea, periodo]
OJO: [1 aviso importante — seguridad, cambio de viento, marea, tamanio — o "Sin avisos"]
RESUMEN: [1 frase potente que resume el dia — motivadora si es bueno, honesta si no]

Reglas:
- Si el mejor score de todos los spots es menor de 35, MERECE LA PENA = NO
- Si el viento es onshore en todos los spots, dilo claro
- Si hay un spot claramente mejor que el resto, destacalo
- No inventes condiciones que no estan en los datos
- Maximo 10 lineas en total"""


def _get_knowledge(name):
    """Busca el conocimiento del spot con matching flexible."""
    if name in SPOT_KNOWLEDGE:
        return SPOT_KNOWLEDGE[name]
    for key, val in SPOT_KNOWLEDGE.items():
        if key.lower() in name.lower() or name.lower() in key.lower():
            return val
    return None


# ─── LLAMADA A LA API ────────────────────────────────────────────────────────

async def generate_ai_briefing(
    island: str,
    day_str: str,
    spots_data: list,
    hourly: list,
    tide_data: dict = None,
) -> str:
    """
    Genera el briefing completo con decisión de la IA.

    spots_data: lista de dicts con:
        name, score, semaforo, penalizaciones, sh, sp, sd, ws, wd, marea (opcional)
    tide_data: dict de tides.py (opcional pero mejora el análisis)
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY no configurada — usando fallback")
        return _fallback(spots_data)

    prompt = _build_prompt(island, day_str, spots_data, hourly, tide_data)

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": MODEL,
                    "max_tokens": 450,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        resp.raise_for_status()
        data = resp.json()
        text = data["content"][0]["text"].strip()
        logger.info(f"AI briefing OK — {island} {day_str} spots={len(spots_data)}")
        return text

    except httpx.HTTPStatusError as e:
        logger.error(f"Claude API {e.response.status_code}: {e.response.text[:200]}")
        return _fallback(spots_data)
    except httpx.TimeoutException:
        logger.error("Claude API timeout")
        return _fallback(spots_data)
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return _fallback(spots_data)


# ─── FALLBACK SIN IA ─────────────────────────────────────────────────────────

def _fallback(spots_data: list) -> str:
    if not spots_data:
        return "Sin datos suficientes para el analisis de hoy."

    best  = max(spots_data, key=lambda x: x.get("score", 0))
    score = best.get("score", 0)
    name  = best.get("name", "?")
    sh    = best.get("sh", 0)
    ws    = best.get("ws", 0)
    wd    = best.get("wd", "")

    merece = "SI" if score >= 35 else "NO"

    if score >= 75:   estado = f"Dia epico — {name} esta on fire con {sh:.1f}m"
    elif score >= 55: estado = f"Buenas condiciones en {name} ({sh:.1f}m)"
    elif score >= 35: estado = f"Aceptable — {name} es la mejor opcion"
    else:             estado = "El mar no regala nada hoy"

    if ws < 8:    viento = "viento suave"
    elif ws > 18: viento = f"viento fuerte {ws:.0f}kts {wd} — cuidado"
    else:         viento = f"viento moderado {ws:.0f}kts {wd}"

    k    = _get_knowledge(name) or {}
    nota = k.get("nota", "")

    lines = [
        f"MERECE LA PENA: {merece}",
        f"MEJOR SPOT: {name}",
        f"POR QUE: {estado}, {viento}",
    ]
    if nota:
        lines.append(f"OJO: {nota[:120]}")
    lines.append(f"RESUMEN: {estado}")
    return "\n".join(lines)
