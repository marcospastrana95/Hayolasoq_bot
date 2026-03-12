"""
tides.py — Scraping de mareas desde tablademareas.com
Extrae: horas/alturas de pleamar/bajamar + coeficiente del día
"""

import requests
import re
from datetime import datetime

# ─── URLs por isla ────────────────────────────────────────────────────────────
TIDE_URLS = {
    "tenerife": "https://tablademareas.com/es/islas-canarias/santa-cruz-de-tenerife",
    "graciosa":  "https://tablademareas.com/es/islas-canarias/caleta-del-sebo",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SurfBot/1.0)"
}

# ─── SCRAPING PRINCIPAL ───────────────────────────────────────────────────────

def get_tides(island="tenerife"):
    """
    Devuelve dict con:
      - events: lista de {time, height, type}  (pleamar/bajamar del día)
      - coef: int  (coeficiente de mareas)
      - label: str ("VIVAS", "INTERMEDIAS", "MUERTAS")
      - emoji: str
    Devuelve None si falla el scraping.
    """
    url = TIDE_URLS.get(island, TIDE_URLS["tenerife"])
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        print(f"[Tides] Error fetching {url}: {e}")
        return None

    today = datetime.now().strftime("%-d")  # día sin cero: "12"

    # ── Extraer mareas del día de hoy desde la tabla mensual ──────────────────
    # Patrón de fila: "12  J | 1:30 h    -0,3 m | 7:59 h    0,1 m | ..."
    # La tabla tiene el formato: DÍA \n 1ªMAREA \n 2ªMAREA ...
    events = _parse_tide_table(html, today)

    # ── Extraer coeficiente ───────────────────────────────────────────────────
    coef = _parse_coef(html)

    if not events and coef is None:
        return None

    label, emoji = _coef_label(coef)

    return {
        "events": events,
        "coef":   coef,
        "label":  label,
        "emoji":  emoji,
    }


def _parse_tide_table(html, today_day):
    """
    Busca en la tabla mensual la fila del día de hoy y extrae
    hasta 4 eventos de marea con hora y altura.
    """
    events = []

    # Buscar el bloque del día: "12  J | 1:30 h    -0,3 m | ..."
    # La tabla renderizada tiene este patrón en el markdown:
    # | 12  J |  | 7:17 h  19:11 h | 1:30 h    -0,3 m | 7:59 h    0,1 m | ...
    # Necesitamos buscar la celda que empieza con "12  " seguida de letras de día
    
    # Patrón: número de día al inicio de celda de tabla
    day_pattern = rf'\|\s*{today_day}\s+[LMXJVSD]\s*\|'
    
    # Buscar en el HTML directamente (más fiable que el markdown)
    # El HTML tiene: <td>12  J</td> o similar, pero es JS-rendered...
    # En realidad tablademareas carga las mareas de forma estática en el HTML
    # Vamos a buscar el patrón numérico directamente
    
    # Patrón más robusto: buscar "today_day  L/M/X/J/V/S/D" seguido de datos
    # En el HTML plano buscamos secuencias de hora + altura
    
    # Buscar todas las ocurrencias de "H:MM h    X,X m" cerca del día de hoy
    # Primero localizar posición del día en el HTML
    day_markers = [
        f'| {today_day}  L |', f'| {today_day}  M |', f'| {today_day}  X |',
        f'| {today_day}  J |', f'| {today_day}  V |', f'| {today_day}  S |',
        f'| {today_day}  D |',
    ]
    
    # Buscar en el texto parseado (markdown ya extraído)
    # Usamos el HTML original con regex
    
    # Patrón HTML para fila de la tabla con el día
    # <td>12  J</td> ... <td>1:30 h    -0,3 m</td>
    row_pattern = rf'(?s){today_day}\s+[LMXJVSD].*?(?=\n.*?\d{{1,2}}\s+[LMXJVSD]|\Z)'
    
    # Buscar horas y alturas en el bloque completo del HTML para hoy
    # Estrategia: encontrar el día en el HTML y extraer los datos de la fila
    
    # Buscar todas las parejas hora-altura del documento
    all_pairs = re.findall(r'(\d{1,2}:\d{2})\s+h\s+([-\d,]+)\s+m', html)
    
    if not all_pairs:
        return []
    
    # Encontrar posición del día en el HTML para filtrar solo los datos de hoy
    # Buscamos el patrón del día actual y el siguiente día
    today_int = int(today_day)
    next_day = str(today_int + 1)
    
    # Buscar posición del día en el HTML
    pos_today = _find_day_pos(html, today_day)
    pos_next  = _find_day_pos(html, next_day)
    
    if pos_today == -1:
        # Fallback: usar el texto completo buscando el patrón de la tabla
        return _parse_from_text_description(html, today_day)
    
    # Extraer el fragmento del HTML entre hoy y mañana
    fragment = html[pos_today: pos_next if pos_next > pos_today else pos_today + 2000]
    
    pairs = re.findall(r'(\d{1,2}:\d{2})\s+h\s+([-\d,]+)\s+m', fragment)
    
    for time_str, height_str in pairs[:4]:  # max 4 mareas por día
        height = float(height_str.replace(',', '.'))
        tide_type = "Pleamar" if height >= 0 else "Bajamar"
        events.append({
            "time":   time_str,
            "height": height,
            "type":   tide_type,
        })
    
    return events


def _find_day_pos(html, day_str):
    """Encuentra la posición en el HTML donde aparece el día en la tabla."""
    # Busca patrones como ">12  J<" o "| 12  J |"
    patterns = [
        rf'>{day_str}\s+[LMXJVSD]<',
        rf'\b{day_str}\s+[LMXJVSD]\b',
    ]
    for p in patterns:
        m = re.search(p, html)
        if m:
            return m.start()
    return -1


def _parse_from_text_description(html, today_day):
    """
    Fallback: extrae mareas del texto descriptivo que siempre aparece en la página.
    Ejemplo: "la primera bajamar fue a la 1:30 h y la siguiente bajamar a las 14:09 h"
    """
    events = []
    
    # Buscar en el texto descriptivo
    # "primera pleamar fue a las HH:MM h" / "primera bajamar fue a la HH:MM h"
    patterns = [
        (r'primera bajamar fue a las? (\d{1,2}:\d{2})', "Bajamar"),
        (r'primera pleamar fue a las? (\d{1,2}:\d{2})', "Pleamar"),
        (r'siguiente bajamar a las (\d{1,2}:\d{2})', "Bajamar"),
        (r'siguiente pleamar (?:será )?a las (\d{1,2}:\d{2})', "Pleamar"),
    ]
    
    for pattern, tide_type in patterns:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            events.append({
                "time":   m.group(1),
                "height": None,
                "type":   tide_type,
            })
    
    # Ordenar por hora
    events.sort(key=lambda x: _time_to_minutes(x["time"]))
    return events


def _parse_coef(html):
    """Extrae el coeficiente de mareas del día."""
    # Patrón: "coeficiente de mareas de 25" o "coef. 0:00 h\n25"
    patterns = [
        r'coeficiente de mareas de\s+(\d+)',
        r'coef\.\s+0:00 h\s+(\d+)',
        r'Coeficiente\s+12 DE [A-Z]+ DE \d{4}\s+(\d+)',
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            return int(m.group(1))
    
    # Buscar en la tabla mensual el coeficiente del día actual
    today = datetime.now().day
    # Patrón: número de día seguido eventualmente de coeficiente
    pattern = rf'{today}\s+[LMXJVSD].*?(\d{{2,3}})\s+(?:muy alto|alto|medio|bajo)'
    m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if m:
        return int(m.group(1))
    
    return None


def _coef_label(coef):
    """Clasifica el coeficiente en VIVAS / INTERMEDIAS / MUERTAS."""
    if coef is None:
        return ("DESCONOCIDAS", "🌊")
    if coef >= 70:
        return ("VIVAS 🔥", "🌊🌊")
    if coef >= 40:
        return ("INTERMEDIAS", "🌊")
    return ("MUERTAS", "😴")


def _time_to_minutes(time_str):
    """Convierte 'HH:MM' a minutos para ordenar."""
    try:
        h, m = map(int, time_str.split(':'))
        return h * 60 + m
    except Exception:
        return 0


# ─── FORMATO PARA TELEGRAM ────────────────────────────────────────────────────

def format_tides_block(tide_data):
    """
    Genera el bloque de mareas para el briefing de Telegram.
    Ejemplo:
    〰️ MAREAS · coef. 25 · MUERTAS 😴
    ↓ 01:30  -0.3m   ↑ 07:59  +0.1m
    ↓ 14:09  -0.3m   ↑ 20:40  +0.2m
    """
    if not tide_data:
        return "〰️ _Mareas no disponibles_"

    coef  = tide_data["coef"]
    label = tide_data["label"]
    coef_str = f"coef. {coef} · " if coef else ""

    lines = [f"〰️ *MAREAS* · {coef_str}{label}"]

    events = tide_data["events"]
    # Formatear en parejas (2 por línea)
    row = []
    for ev in events:
        arrow  = "↑" if ev["type"] == "Pleamar" else "↓"
        height = f"{ev['height']:+.1f}m" if ev["height"] is not None else ""
        row.append(f"{arrow} {ev['time']}  {height}")
        if len(row) == 2:
            lines.append(f"  {row[0]}   {row[1]}")
            row = []
    if row:
        lines.append(f"  {row[0]}")

    return "\n".join(lines)
