"""
chart.py v2 — BUGS CORREGIDOS:
  1. Scores a 0: se pasan correctamente swell_height/period al scorer
  2. Flechas viento: _wind_arrow() corregida
  3. Emojis rotos: sustituidos por texto ASCII
  4. Titulo en ingles: traduccion manual al espanol
  5. Isla incorrecta: se usa island real, no zona
"""

import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime

from scorer import score_spot, degrees_to_dir
from fetcher import get_tide_state

# Traduccion manual espanol (no depende de locale del servidor)
DIAS_ES  = ["Lunes","Martes","Miercoles","Jueves","Viernes","Sabado","Domingo"]
MESES_ES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
            "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

def _day_label_es(day_str):
    d = datetime.strptime(day_str, "%Y-%m-%d")
    return f"{DIAS_ES[d.weekday()]} {d.day} {MESES_ES[d.month]}"

# Paleta
BG          = "#0d1117"
BG_HEADER   = "#161b22"
BG_ROW_A    = "#0d1117"
BG_ROW_B    = "#111820"
TEXT_WHITE  = "#e6edf3"
TEXT_GREY   = "#8b949e"
BORDER      = "#30363d"
COLOR_GREEN  = "#2ea043"
COLOR_YELLOW = "#d29922"
COLOR_RED    = "#da3633"
COLOR_GREY   = "#21262d"
COLOR_WIND = {
    "calma":    "#58a6ff",
    "suave":    "#3fb950",
    "moderado": "#d29922",
    "fuerte":   "#f85149",
    "extremo":  "#ff0000",
}

HORAS = [6,7,8,9,10,11,12,13,14,15,16,17,18,19,20]

TIPO_LABEL = {
    "beach_break": "BB",
    "reef_break":  "RF",
    "point_break": "PT",
    "rock_break":  "RK",
}

def _score_color(s):
    if s >= 55: return COLOR_GREEN
    if s >= 30: return COLOR_YELLOW
    return COLOR_RED

def _score_alpha(s):
    return 0.35 + (s/100)*0.65

def _wind_color(kts):
    if kts is None: return COLOR_GREY
    if kts < 5:  return COLOR_WIND["calma"]
    if kts < 10: return COLOR_WIND["suave"]
    if kts < 15: return COLOR_WIND["moderado"]
    if kts < 20: return COLOR_WIND["fuerte"]
    return COLOR_WIND["extremo"]

def _wind_arrow(deg):
    """
    Flecha que indica HACIA DONDE sopla el viento.
    deg=0 (viento del N) -> sopla hacia S -> flecha apunta abajo
    FIX: arrows ordenadas correctamente, indice sin +180 extra.
    """
    arrows = ["v","\\","<","/","^","\\",">","/"]
    # Usamos caracteres ASCII simples y robustos:
    arrows = ["S","SW","W","NW","N","NE","E","SE"]
    idx = round(deg / 45) % 8
    # Devolver flecha unicode correcta segun destino del viento
    unicode_arrows = {
        "N":  "v",   # viene del N, va hacia S
        "NE": "\\",
        "E":  "<",
        "SE": "/",
        "S":  "^",   # viene del S, va hacia N
        "SW": "\\",
        "W":  ">",
        "NW": "/",
    }
    dirs_order = ["N","NE","E","SE","S","SW","W","NW"]
    direction = dirs_order[idx]
    return unicode_arrows.get(direction, "-")

def _swell_color(h):
    if h is None: return COLOR_GREY
    if h >= 2.0:  return "#58a6ff"
    if h >= 1.2:  return "#3fb950"
    if h >= 0.6:  return "#d29922"
    return "#8b949e"

def _tide_label(hour):
    t = get_tide_state(hour)
    return {"Pleamar":"PLE","Bajamar":"BAJ","Media":"MED"}[t]

def _tide_color(hour):
    t = get_tide_state(hour)
    return {"Pleamar":"#58a6ff","Bajamar":"#f0883e","Media":"#8b949e"}[t]

def _swell(e):
    sh = e.get("swell_height") or e.get("wave_height") or 0
    sp = e.get("swell_period") or e.get("wave_period") or 0
    sd = e.get("swell_direction") or e.get("wave_direction") or 0
    return sh, sp, sd

def _wind(e):
    return e.get("wind_speed") or 0, e.get("wind_direction") or 0

def _hour(entry):
    t = entry["time"]
    return int(t[11:13]) if "T" in t else int(t[8:10])


def generate_chart(island, spots, hourly_by_spot, day_str, swell_summary):
    n_spots = len(spots)
    N_HEADER_ROWS = 2
    N_DATA_ROWS   = n_spots
    N_FOOTER_ROWS = 3
    N_ROWS        = N_HEADER_ROWS + N_DATA_ROWS + 1 + N_FOOTER_ROWS
    n_horas       = len(HORAS)

    COL_W   = 0.72
    COL_H   = 0.44
    LABEL_W = 2.4
    fig_w   = LABEL_W + n_horas * COL_W + 0.3
    fig_h   = N_ROWS * COL_H + 0.7

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, fig_w); ax.set_ylim(0, fig_h); ax.axis("off")
    fig.patch.set_facecolor(BG)

    def col_x(i): return LABEL_W + (i+0.5)*COL_W
    def row_y(r): return fig_h - (r+0.5)*COL_H - 0.35

    def cell_rect(r, i, color, alpha=1.0):
        x = LABEL_W + i*COL_W
        y = fig_h - (r+1)*COL_H - 0.35
        ax.add_patch(mpatches.FancyBboxPatch(
            (x+0.02, y+0.02), COL_W-0.04, COL_H-0.04,
            boxstyle="round,pad=0.02", facecolor=color, alpha=alpha,
            edgecolor="none", zorder=2))

    def label_rect(r, color=BG_HEADER):
        y = fig_h - (r+1)*COL_H - 0.35
        ax.add_patch(plt.Rectangle((0,y), LABEL_W, COL_H,
                                    facecolor=color, edgecolor="none", zorder=1))

    # Fondo
    ax.add_patch(plt.Rectangle((0,0), fig_w, fig_h, facecolor=BG, edgecolor="none"))

    # Fila 0: Titulo
    island_str = "TENERIFE" if island == "tenerife" else "LA GRACIOSA"
    day_label  = _day_label_es(day_str)
    sh1 = swell_summary.get("sh1",0)
    sp1 = swell_summary.get("sp1",0)
    sd1 = swell_summary.get("sd1","")
    ws  = swell_summary.get("ws",0)
    wd  = swell_summary.get("wd","")

    ax.add_patch(plt.Rectangle((0, fig_h-COL_H-0.35), fig_w, COL_H+0.35,
                                facecolor=BG_HEADER, edgecolor="none"))
    ax.text(0.15, fig_h-0.20, f"SURF  {island_str}  -  {day_label}",
            color=TEXT_WHITE, fontsize=9.5, fontweight="bold", va="top", ha="left", zorder=3)
    ax.text(fig_w-0.15, fig_h-0.20, f"{sh1:.1f}m {sp1:.0f}s {sd1}   {ws:.0f}kts {wd}",
            color=TEXT_GREY, fontsize=7.5, va="top", ha="right", zorder=3)
    ax.plot([0,fig_w],[fig_h-COL_H-0.35]*2, color=BORDER, linewidth=0.5, zorder=3)

    # Fila 1: Cabecera horas
    r = 1
    label_rect(r, BG_HEADER)
    ax.text(LABEL_W/2, row_y(r), "SPOT", color=TEXT_GREY, fontsize=7,
            fontweight="bold", va="center", ha="center", zorder=3)
    for i,h in enumerate(HORAS):
        ax.text(col_x(i), row_y(r), f"{h:02d}h", color=TEXT_GREY, fontsize=7,
                fontweight="bold", va="center", ha="center", zorder=3)
    ax.plot([0,fig_w],[fig_h-2*COL_H-0.35]*2, color=BORDER, linewidth=0.5, zorder=3)

    # Filas de spots
    for s_idx, spot in enumerate(spots):
        r  = N_HEADER_ROWS + s_idx
        bg = BG_ROW_A if s_idx%2==0 else BG_ROW_B
        label_rect(r, bg)

        tipo_lbl = TIPO_LABEL.get(spot["type"], "??")
        name = spot["name"][:20]
        ax.text(0.10, row_y(r), tipo_lbl, color=TEXT_GREY, fontsize=6,
                fontweight="bold", va="center", ha="left", zorder=3)
        ax.text(0.52, row_y(r), name, color=TEXT_WHITE, fontsize=7,
                va="center", ha="left", zorder=3)

        hourly   = hourly_by_spot.get(spot["name"], [])
        hour_map = {}
        for entry in hourly:
            try: hour_map[_hour(entry)] = entry
            except: pass

        for i,h in enumerate(HORAS):
            entry = hour_map.get(h)
            if not entry:
                cell_rect(r, i, BG_ROW_B, alpha=0.5)
                ax.text(col_x(i), row_y(r), "-", color=TEXT_GREY, fontsize=6.5,
                        va="center", ha="center", zorder=3)
                continue

            sh, sp, sd = _swell(entry)
            ws_e, wd_e = _wind(entry)
            tide       = get_tide_state(h)

            # FIX CRITICO: pasar todos los campos que scorer.py necesita
            conds = {
                "swell_height":    sh,
                "swell_period":    sp,
                "swell_direction": sd,
                "wave_height":     entry.get("wave_height", sh),
                "wave_period":     entry.get("wave_period", sp),
                "wave_direction":  entry.get("wave_direction", sd),
                "wind_speed":      ws_e,
                "wind_direction":  wd_e,
                "tide_state":      tide,
            }
            result = score_spot(spot, conds, hora=h)
            score  = result["score"]
            color  = _score_color(score)
            alpha  = _score_alpha(score)

            cell_rect(r, i, color, alpha=alpha)
            ax.text(col_x(i), row_y(r)+0.07, str(score),
                    color=TEXT_WHITE, fontsize=6.5, fontweight="bold",
                    va="center", ha="center", zorder=3)
            sem_color = {"verde":COLOR_GREEN,"amarillo":COLOR_YELLOW,"rojo":COLOR_RED}[result["semaforo"]]
            ax.add_patch(plt.Circle((col_x(i), row_y(r)-0.10), 0.055,
                                     facecolor=sem_color, edgecolor="none", alpha=0.9, zorder=4))

        y_sep = fig_h - (r+1)*COL_H - 0.35
        ax.plot([0,fig_w],[y_sep,y_sep], color=BORDER, linewidth=0.3, alpha=0.5, zorder=2)

    # Separador footer
    r_sep = N_HEADER_ROWS + N_DATA_ROWS
    y_sep = fig_h - r_sep*COL_H - 0.35
    ax.plot([0,fig_w],[y_sep,y_sep], color=BORDER, linewidth=0.8, zorder=3)

    # Datos generales para footer
    general_hourly = next(iter(hourly_by_spot.values()), [])
    gen_map = {}
    for entry in general_hourly:
        try: gen_map[_hour(entry)] = entry
        except: pass

    # Footer: Swell
    r = r_sep
    label_rect(r, BG_HEADER)
    ax.text(LABEL_W/2, row_y(r), "SWELL", color=TEXT_GREY, fontsize=6.5,
            fontweight="bold", va="center", ha="center", zorder=3)
    for i,h in enumerate(HORAS):
        entry = gen_map.get(h)
        if not entry:
            ax.text(col_x(i), row_y(r), "-", color=TEXT_GREY, fontsize=6,
                    va="center", ha="center", zorder=3)
            continue
        sh,sp,_ = _swell(entry)
        cell_rect(r, i, _swell_color(sh), alpha=0.4)
        ax.text(col_x(i), row_y(r)+0.07, f"{sh:.1f}m", color=TEXT_WHITE, fontsize=6,
                va="center", ha="center", zorder=3)
        ax.text(col_x(i), row_y(r)-0.09, f"{sp:.0f}s", color=TEXT_GREY, fontsize=5.5,
                va="center", ha="center", zorder=3)

    # Footer: Viento
    r = r_sep+1
    label_rect(r, BG_HEADER)
    ax.text(LABEL_W/2, row_y(r), "VIENTO", color=TEXT_GREY, fontsize=6.5,
            fontweight="bold", va="center", ha="center", zorder=3)
    for i,h in enumerate(HORAS):
        entry = gen_map.get(h)
        if not entry:
            ax.text(col_x(i), row_y(r), "-", color=TEXT_GREY, fontsize=6,
                    va="center", ha="center", zorder=3)
            continue
        ws_h, wd_h = _wind(entry)
        # Flecha apunta HACIA DONDE SOPLA (destino = origen + 180)
        dest_deg   = (wd_h + 180) % 360
        arrow_list = ["↑","↗","→","↘","↓","↙","←","↖"]   # N NE E SE S SW W NW
        arrow      = arrow_list[round(dest_deg / 45) % 8]
        cell_rect(r, i, _wind_color(ws_h), alpha=0.35)
        ax.text(col_x(i), row_y(r)+0.07, f"{ws_h:.0f}kt", color=TEXT_WHITE, fontsize=6,
                va="center", ha="center", zorder=3)
        ax.text(col_x(i), row_y(r)-0.09, arrow, color=TEXT_GREY, fontsize=8,
                va="center", ha="center", zorder=3)

    # Footer: Marea
    r = r_sep+2
    label_rect(r, BG_HEADER)
    ax.text(LABEL_W/2, row_y(r), "MAREA", color=TEXT_GREY, fontsize=6.5,
            fontweight="bold", va="center", ha="center", zorder=3)
    for i,h in enumerate(HORAS):
        t_label = _tide_label(h)
        t_color = _tide_color(h)
        cell_rect(r, i, t_color, alpha=0.25)
        ax.text(col_x(i), row_y(r), t_label, color=t_color, fontsize=6.5,
                fontweight="bold", va="center", ha="center", zorder=3)

    # Leyenda
    ax.plot([0,fig_w],[COL_H*0.85]*2, color=BORDER, linewidth=0.5, zorder=3)
    legend_items = [
        (COLOR_GREEN,  "Bueno (>=55)"),
        (COLOR_YELLOW, "Regular (30-54)"),
        (COLOR_RED,    "Malo (<30)"),
    ]
    x_leg = 0.2
    for color, lbl in legend_items:
        ax.add_patch(plt.Circle((x_leg, COL_H*0.42), 0.05,
                                facecolor=color, edgecolor="none", zorder=4))
        ax.text(x_leg+0.13, COL_H*0.42, lbl, color=TEXT_GREY, fontsize=6,
                va="center", ha="left", zorder=3)
        x_leg += 1.6

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


# Analisis de tendencia
def analyze_trend(hourly, spots, day_str):
    day_entries = []
    for e in hourly:
        if not e["time"].startswith(day_str): continue
        try:
            h = _hour(e)
            if 6 <= h <= 20: day_entries.append(e)
        except: pass
    if not day_entries: return ""

    heights = []
    for e in day_entries:
        try:
            h  = _hour(e)
            sh = e.get("swell_height") or e.get("wave_height") or 0
            heights.append((h,sh))
        except: pass
    if not heights: return ""

    heights.sort()
    horas_list = [x[0] for x in heights]
    vals       = [x[1] for x in heights]
    max_val    = max(vals)
    max_hora   = horas_list[vals.index(max_val)]
    mid        = len(vals)//2
    avg_f      = sum(vals[:mid])/mid if mid else 0
    avg_s      = sum(vals[mid:])/(len(vals)-mid) if len(vals)-mid else 0
    diff       = avg_s - avg_f

    if diff > 0.15:   trend = f"Swell en aumento, pico {max_hora:02d}h ({max_val:.1f}m)"
    elif diff < -0.15: trend = f"Swell bajando, mejor manana ({vals[0]:.1f}m)"
    else:              trend = f"Swell estable (~{sum(vals)/len(vals):.1f}m)"

    lines = [trend]
    bw = _find_best_window(day_entries, spots[0] if spots else None)
    if bw: lines.append(f"Mejor ventana: {bw[0]:02d}h-{bw[1]:02d}h")

    wind_vals = []
    for e in day_entries:
        try: wind_vals.append((_hour(e), e.get("wind_speed") or 0))
        except: pass
    wind_vals.sort()
    calm = [h for h,w in wind_vals if w < 8]
    if calm: lines.append(f"Viento suave: {calm[0]:02d}h-{calm[-1]:02d}h")
    return "\n".join(lines)


def _find_best_window(day_entries, spot, min_window=2):
    if not spot or not day_entries: return None
    scored = []
    for e in day_entries:
        try:
            h = _hour(e)
            if not (6 <= h <= 20): continue
            sh,sp,sd = _swell(e)
            ws,wd    = _wind(e)
            tide     = get_tide_state(h)
            conds = {
                "swell_height":sh,"swell_period":sp,"swell_direction":sd,
                "wave_height":sh,"wave_period":sp,"wave_direction":sd,
                "wind_speed":ws,"wind_direction":wd,"tide_state":tide,
            }
            r = score_spot(spot, conds, hora=h)
            scored.append((h, r["score"]))
        except: pass
    scored.sort()
    if not scored: return None
    best_avg = best_start = best_end = None
    for i in range(len(scored)-min_window+1):
        w   = scored[i:i+min_window]
        avg = sum(s for _,s in w)/len(w)
        if best_avg is None or avg > best_avg:
            best_avg = avg; best_start = w[0][0]; best_end = w[-1][0]
    return (best_start, best_end) if best_avg and best_avg >= 25 else None
