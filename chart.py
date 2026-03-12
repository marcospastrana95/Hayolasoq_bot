"""
chart.py — Genera imagen tipo Windguru con tabla horaria de todos los spots.
Devuelve bytes PNG listos para enviar por Telegram.
"""

import io
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import to_rgba
import numpy as np
from datetime import datetime

from scorer import score_spot, degrees_to_dir
from fetcher import get_tide_state

# ─── PALETA ──────────────────────────────────────────────────────────────────
BG          = "#0d1117"   # fondo general
BG_HEADER   = "#161b22"   # cabecera
BG_ROW_A    = "#0d1117"   # fila impar
BG_ROW_B    = "#111820"   # fila par
TEXT_WHITE  = "#e6edf3"
TEXT_GREY   = "#8b949e"
TEXT_DARK   = "#0d1117"
BORDER      = "#30363d"

# Colores semáforo (score)
COLOR_GREEN  = "#2ea043"
COLOR_YELLOW = "#d29922"
COLOR_RED    = "#da3633"
COLOR_GREY   = "#21262d"

# Colores viento
COLOR_WIND = {
    "calma":    "#58a6ff",
    "suave":    "#3fb950",
    "moderado": "#d29922",
    "fuerte":   "#f85149",
    "extremo":  "#ff0000",
}

HORAS = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _score_color(score):
    if score >= 55:  return COLOR_GREEN
    if score >= 30:  return COLOR_YELLOW
    return COLOR_RED

def _score_alpha(score):
    """Más opaco cuanto más alto el score."""
    return 0.35 + (score / 100) * 0.65

def _wind_color(kts):
    if kts is None: return COLOR_GREY
    if kts < 5:   return COLOR_WIND["calma"]
    if kts < 10:  return COLOR_WIND["suave"]
    if kts < 15:  return COLOR_WIND["moderado"]
    if kts < 20:  return COLOR_WIND["fuerte"]
    return COLOR_WIND["extremo"]

def _wind_arrow(degrees):
    """Flecha unicode según dirección del viento (de dónde viene)."""
    arrows = ["↓","↙","←","↖","↑","↗","→","↘"]
    idx = round(((degrees + 180) % 360) / 45) % 8
    return arrows[idx]

def _tide_label(hour):
    t = get_tide_state(hour)
    return {"Pleamar": "PLE", "Bajamar": "BAJ", "Media": "MED"}[t]

def _tide_color(hour):
    t = get_tide_state(hour)
    return {"Pleamar": "#58a6ff", "Bajamar": "#f0883e", "Media": "#8b949e"}[t]

def _swell_color(height):
    if height is None: return COLOR_GREY
    if height >= 2.0:  return "#58a6ff"
    if height >= 1.2:  return "#3fb950"
    if height >= 0.6:  return "#d29922"
    return "#8b949e"


# ─── GENERADOR PRINCIPAL ──────────────────────────────────────────────────────

def generate_chart(island, spots, hourly_by_spot, day_str, swell_summary):
    """
    Genera la imagen de la tabla y devuelve bytes PNG.

    island          : "tenerife" | "graciosa"
    spots           : lista de dicts de spots (de spots.py)
    hourly_by_spot  : dict {spot_name: [hourly_entries...]}
    day_str         : "2026-03-12"
    swell_summary   : dict con sh1, sd1, sp1, ws, wd del día
    """
    n_spots = len(spots)
    n_horas = len(HORAS)

    # ── Layout ────────────────────────────────────────────────────────────────
    # Filas: cabecera + hora + spots + separador + swell + viento + marea
    N_HEADER_ROWS = 2    # título + horas
    N_DATA_ROWS   = n_spots
    N_FOOTER_ROWS = 3    # swell + viento + marea
    N_ROWS        = N_HEADER_ROWS + N_DATA_ROWS + 1 + N_FOOTER_ROWS

    COL_W   = 0.7    # ancho columna hora (inches)
    COL_H   = 0.42   # alto fila (inches)
    LABEL_W = 2.2    # ancho columna nombre spot

    fig_w = LABEL_W + n_horas * COL_W + 0.3
    fig_h = N_ROWS * COL_H + 0.6

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis("off")
    fig.patch.set_facecolor(BG)

    # ── Funciones de posición ─────────────────────────────────────────────────
    def col_x(i):
        """Centro X de columna de hora i (0-based)."""
        return LABEL_W + (i + 0.5) * COL_W

    def row_y(r):
        """Centro Y de fila r (0=top)."""
        return fig_h - (r + 0.5) * COL_H - 0.3

    def cell_rect(r, i, color, alpha=1.0):
        x = LABEL_W + i * COL_W
        y = fig_h - (r + 1) * COL_H - 0.3
        ax.add_patch(mpatches.FancyBboxPatch(
            (x + 0.02, y + 0.02), COL_W - 0.04, COL_H - 0.04,
            boxstyle="round,pad=0.02",
            facecolor=color, alpha=alpha,
            edgecolor="none", zorder=2
        ))

    def label_rect(r, color=BG_HEADER):
        y = fig_h - (r + 1) * COL_H - 0.3
        ax.add_patch(plt.Rectangle(
            (0, y), LABEL_W, COL_H,
            facecolor=color, edgecolor="none", zorder=1
        ))

    # ── Fondo general ─────────────────────────────────────────────────────────
    ax.add_patch(plt.Rectangle((0, 0), fig_w, fig_h,
                                facecolor=BG, edgecolor="none"))

    # ── Fila 0: Título ────────────────────────────────────────────────────────
    day_label = datetime.strptime(day_str, "%Y-%m-%d").strftime("%A %d %B").capitalize()
    island_str = "Tenerife" if island == "tenerife" else "La Graciosa"
    sh1 = swell_summary.get("sh1", 0)
    sp1 = swell_summary.get("sp1", 0)
    sd1 = swell_summary.get("sd1", "")
    ws  = swell_summary.get("ws", 0)
    wd  = swell_summary.get("wd", "")

    ax.add_patch(plt.Rectangle((0, fig_h - COL_H - 0.3), fig_w, COL_H + 0.3,
                                facecolor=BG_HEADER, edgecolor="none"))
    ax.text(0.15, fig_h - 0.18, f"🏄  {island_str.upper()}  ·  {day_label}",
            color=TEXT_WHITE, fontsize=9.5, fontweight="bold",
            va="top", ha="left", zorder=3)
    ax.text(fig_w - 0.15, fig_h - 0.18,
            f"🌊 {sh1:.1f}m {sp1:.0f}s {sd1}   💨 {wd} {ws:.0f}kts",
            color=TEXT_GREY, fontsize=7.5,
            va="top", ha="right", zorder=3)

    # Línea separadora bajo título
    ax.plot([0, fig_w], [fig_h - COL_H - 0.3, fig_h - COL_H - 0.3],
            color=BORDER, linewidth=0.5, zorder=3)

    # ── Fila 1: Cabecera horas ────────────────────────────────────────────────
    r = 1
    label_rect(r, BG_HEADER)
    ax.text(LABEL_W / 2, row_y(r), "SPOT",
            color=TEXT_GREY, fontsize=7, fontweight="bold",
            va="center", ha="center", zorder=3)
    for i, h in enumerate(HORAS):
        ax.text(col_x(i), row_y(r), f"{h:02d}h",
                color=TEXT_GREY, fontsize=7, fontweight="bold",
                va="center", ha="center", zorder=3)

    ax.plot([0, fig_w], [fig_h - 2 * COL_H - 0.3] * 2,
            color=BORDER, linewidth=0.5, zorder=3)

    # ── Filas de spots ────────────────────────────────────────────────────────
    TIPO_ICON = {"beach_break": "🏖", "reef_break": "🪸",
                 "point_break": "📍", "rock_break": "🪨"}

    for s_idx, spot in enumerate(spots):
        r = N_HEADER_ROWS + s_idx
        bg = BG_ROW_A if s_idx % 2 == 0 else BG_ROW_B
        label_rect(r, bg)

        # Nombre del spot (truncado)
        icon = TIPO_ICON.get(spot["type"], "🌊")
        name = spot["name"]
        if len(name) > 18: name = name[:16] + "…"
        ax.text(0.12, row_y(r), icon, fontsize=7.5,
                va="center", ha="left", zorder=3)
        ax.text(0.55, row_y(r), name,
                color=TEXT_WHITE, fontsize=7,
                va="center", ha="left", zorder=3)

        # Celdas por hora
        hourly = hourly_by_spot.get(spot["name"], [])
        hour_map = {}
        for entry in hourly:
            t = entry["time"]
            try:
                h = int(t[11:13]) if "T" in t else int(t[8:10])
                hour_map[h] = entry
            except Exception:
                pass

        for i, h in enumerate(HORAS):
            entry = hour_map.get(h)
            if not entry:
                cell_rect(r, i, BG_ROW_B, alpha=0.5)
                ax.text(col_x(i), row_y(r), "—",
                        color=TEXT_GREY, fontsize=6.5,
                        va="center", ha="center", zorder=3)
                continue

            tide   = get_tide_state(h)
            conds  = {**entry, "tide_state": tide}
            result = score_spot(spot, conds, hora=h)
            score  = result["score"]
            color  = _score_color(score)
            alpha  = _score_alpha(score)

            cell_rect(r, i, color, alpha=alpha)
            ax.text(col_x(i), row_y(r) + 0.06, f"{score}",
                    color=TEXT_WHITE, fontsize=6.5, fontweight="bold",
                    va="center", ha="center", zorder=3)
            # Semáforo pequeño
            sem_color = {"verde": COLOR_GREEN, "amarillo": COLOR_YELLOW,
                         "rojo": COLOR_RED}[result["semaforo"]]
            ax.add_patch(plt.Circle(
                (col_x(i), row_y(r) - 0.10), 0.055,
                facecolor=sem_color, edgecolor="none",
                alpha=0.9, zorder=4
            ))

        # Línea separadora fina entre spots
        y_sep = fig_h - (r + 1) * COL_H - 0.3
        ax.plot([0, fig_w], [y_sep, y_sep],
                color=BORDER, linewidth=0.3, alpha=0.5, zorder=2)

    # ── Separador antes del footer ────────────────────────────────────────────
    r_sep = N_HEADER_ROWS + N_DATA_ROWS
    y_sep = fig_h - r_sep * COL_H - 0.3
    ax.plot([0, fig_w], [y_sep, y_sep],
            color=BORDER, linewidth=0.8, zorder=3)

    # ── Footer row: Swell ─────────────────────────────────────────────────────
    r = r_sep
    label_rect(r, BG_HEADER)
    ax.text(LABEL_W / 2, row_y(r), "🌊 SWELL",
            color=TEXT_GREY, fontsize=6.5, fontweight="bold",
            va="center", ha="center", zorder=3)

    # Necesitamos datos horarios generales — usamos el primer spot con datos
    general_hourly = next(iter(hourly_by_spot.values()), [])
    gen_map = {}
    for entry in general_hourly:
        t = entry["time"]
        try:
            h = int(t[11:13]) if "T" in t else int(t[8:10])
            gen_map[h] = entry
        except Exception:
            pass

    for i, h in enumerate(HORAS):
        entry = gen_map.get(h)
        if not entry:
            ax.text(col_x(i), row_y(r), "—",
                    color=TEXT_GREY, fontsize=6, va="center", ha="center", zorder=3)
            continue
        sh = entry.get("swell_height") or entry.get("wave_height") or 0
        sp = entry.get("swell_period") or entry.get("wave_period") or 0
        cell_rect(r, i, _swell_color(sh), alpha=0.4)
        ax.text(col_x(i), row_y(r) + 0.06, f"{sh:.1f}m",
                color=TEXT_WHITE, fontsize=6, va="center", ha="center", zorder=3)
        ax.text(col_x(i), row_y(r) - 0.09, f"{sp:.0f}s",
                color=TEXT_GREY, fontsize=5.5, va="center", ha="center", zorder=3)

    # ── Footer row: Viento ────────────────────────────────────────────────────
    r = r_sep + 1
    label_rect(r, BG_HEADER)
    ax.text(LABEL_W / 2, row_y(r), "💨 VIENTO",
            color=TEXT_GREY, fontsize=6.5, fontweight="bold",
            va="center", ha="center", zorder=3)

    for i, h in enumerate(HORAS):
        entry = gen_map.get(h)
        if not entry:
            ax.text(col_x(i), row_y(r), "—",
                    color=TEXT_GREY, fontsize=6, va="center", ha="center", zorder=3)
            continue
        ws_h = entry.get("wind_speed") or 0
        wd_h = entry.get("wind_direction") or 0
        arrow = _wind_arrow(wd_h)
        cell_rect(r, i, _wind_color(ws_h), alpha=0.35)
        ax.text(col_x(i), row_y(r) + 0.06, f"{ws_h:.0f}kt",
                color=TEXT_WHITE, fontsize=6, va="center", ha="center", zorder=3)
        ax.text(col_x(i), row_y(r) - 0.09, arrow,
                color=TEXT_GREY, fontsize=7, va="center", ha="center", zorder=3)

    # ── Footer row: Marea ─────────────────────────────────────────────────────
    r = r_sep + 2
    label_rect(r, BG_HEADER)
    ax.text(LABEL_W / 2, row_y(r), "〰️ MAREA",
            color=TEXT_GREY, fontsize=6.5, fontweight="bold",
            va="center", ha="center", zorder=3)

    for i, h in enumerate(HORAS):
        t_label = _tide_label(h)
        t_color = _tide_color(h)
        cell_rect(r, i, t_color, alpha=0.25)
        ax.text(col_x(i), row_y(r), t_label,
                color=t_color, fontsize=6.5, fontweight="bold",
                va="center", ha="center", zorder=3)

    # ── Leyenda ───────────────────────────────────────────────────────────────
    ax.plot([0, fig_w], [COL_H * 0.85, COL_H * 0.85],
            color=BORDER, linewidth=0.5, zorder=3)
    legend_items = [
        (COLOR_GREEN,  "Bueno (≥55)"),
        (COLOR_YELLOW, "Regular (30-54)"),
        (COLOR_RED,    "Malo (<30)"),
    ]
    x_leg = 0.2
    for color, label in legend_items:
        ax.add_patch(plt.Circle((x_leg, COL_H * 0.42), 0.05,
                                facecolor=color, edgecolor="none", zorder=4))
        ax.text(x_leg + 0.12, COL_H * 0.42, label,
                color=TEXT_GREY, fontsize=6, va="center", ha="left", zorder=3)
        x_leg += 1.5

    # ── Exportar a bytes ──────────────────────────────────────────────────────
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150,
                bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


# ─── ANÁLISIS DE TENDENCIA ────────────────────────────────────────────────────

def analyze_trend(hourly, spots, day_str):
    """
    Analiza tendencia del swell y ventana óptima del día.
    Devuelve string de texto para incluir en el briefing.
    """
    # Datos horarios del día
    day_entries = [e for e in hourly if e["time"].startswith(day_str)]
    if not day_entries:
        return ""

    heights = []
    for e in day_entries:
        try:
            h    = int(e["time"][11:13]) if "T" in e["time"] else int(e["time"][8:10])
            sh   = e.get("swell_height") or e.get("wave_height") or 0
            heights.append((h, sh))
        except Exception:
            pass

    if not heights:
        return ""

    heights.sort(key=lambda x: x[0])
    horas_list = [x[0] for x in heights]
    vals       = [x[1] for x in heights]

    # Encontrar pico
    max_val  = max(vals)
    max_hora = horas_list[vals.index(max_val)]
    min_val  = min(vals)

    # Tendencia general
    first_half = vals[:len(vals)//2]
    second_half = vals[len(vals)//2:]
    avg_first  = sum(first_half) / len(first_half) if first_half else 0
    avg_second = sum(second_half) / len(second_half) if second_half else 0
    diff = avg_second - avg_first

    if diff > 0.15:
        trend_txt = f"📈 Swell *en aumento* a lo largo del día, pico a las *{max_hora:02d}h* ({max_val:.1f}m)"
    elif diff < -0.15:
        trend_txt = f"📉 Swell *bajando* durante el día, mejor por la mañana ({vals[0]:.1f}m)"
    else:
        trend_txt = f"➡️ Swell *estable* todo el día (~{sum(vals)/len(vals):.1f}m)"

    # Ventana óptima: horas consecutivas con el mejor score promedio
    # Usar el primer spot disponible como referencia
    best_spot   = spots[0] if spots else None
    best_window = _find_best_window(day_entries, best_spot)

    lines = [trend_txt]
    if best_window:
        h_start, h_end = best_window
        lines.append(f"⭐ Mejor ventana: *{h_start:02d}h – {h_end:02d}h*")

    # Nota de viento
    wind_vals = [(int(e["time"][11:13]) if "T" in e["time"] else int(e["time"][8:10]),
                  e.get("wind_speed") or 0)
                 for e in day_entries]
    wind_vals.sort()
    calm_hours = [h for h, w in wind_vals if w < 8]
    if calm_hours:
        lines.append(f"🪷 Viento suave: *{calm_hours[0]:02d}h – {calm_hours[-1]:02d}h*")

    return "\n".join(lines)


def _find_best_window(day_entries, spot, min_window=2):
    """Encuentra la ventana de horas consecutivas con mejor score promedio."""
    if not spot or not day_entries:
        return None

    scored = []
    for e in day_entries:
        try:
            h      = int(e["time"][11:13]) if "T" in e["time"] else int(e["time"][8:10])
            tide   = get_tide_state(h)
            result = score_spot(spot, {**e, "tide_state": tide}, hora=h)
            scored.append((h, result["score"]))
        except Exception:
            pass

    scored.sort(key=lambda x: x[0])
    if not scored:
        return None

    # Sliding window de min_window horas
    best_avg   = -1
    best_start = None
    best_end   = None

    for i in range(len(scored) - min_window + 1):
        window  = scored[i:i + min_window]
        avg     = sum(s for _, s in window) / len(window)
        if avg > best_avg:
            best_avg   = avg
            best_start = window[0][0]
            best_end   = window[-1][0]

    if best_avg < 25:
        return None
    return (best_start, best_end)
