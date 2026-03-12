
#!/usr/bin/env python3
"""
SurfBot para Marcos — Bot de Telegram
Modo SMART (briefing diario): 1 llamada Stormglass, mejor spot del día
Modo COMPLETO (bajo demanda): 4 llamadas, todos los spots
Fallback automático a Open-Meteo si Stormglass está agotado
"""

import os
import logging
from datetime import datetime, time as dtime, timedelta

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

from spots import SPOTS
from fetcher import (
    get_best_zone_for_island, get_conditions_for_island,
    get_hourly_for_spot, get_tide_state, stormglass_available
)
from scorer import score_spot, degrees_to_dir
from tides import get_tides, format_tides_block
from chart import generate_chart, analyze_trend

# ─── CONFIG ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "TU_TOKEN_AQUI")
STORMGLASS_KEY = os.environ.get("STORMGLASS_KEY", "TU_API_KEY_AQUI")
MARCOS_CHAT_ID = os.environ.get("MARCOS_CHAT_ID", "")
BRIEFING_HOUR  = 8

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_island = {}  # chat_id → "tenerife" | "graciosa"

SEMAFORO   = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}
TIPO_EMOJI = {"beach_break": "🏖", "reef_break": "🪸", "point_break": "📍", "rock_break": "🪨"}


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _ref_entry(hourly, day_str):
    """Entrada de referencia: 10h del día o la primera disponible."""
    for h in hourly:
        if h["time"].startswith(day_str + "T10") or h["time"].startswith(day_str + " 10"):
            return h
    return next((h for h in hourly if h["time"].startswith(day_str)), None)

def get_best_hours(hourly, spot, day_str):
    """Top 3 horas del día para un spot."""
    scored = []
    for entry in (h for h in hourly if h["time"].startswith(day_str)):
        hour   = int(entry["time"][11:13]) if "T" in entry["time"] else int(entry["time"][8:10])
        result = score_spot(spot, {**entry, "tide_state": get_tide_state(hour)}, hora=hour)
        scored.append((hour, result["score"], result["semaforo"]))
    scored.sort(key=lambda x: -x[1])
    return scored[:3]

def format_spot_block(spot, entry, hourly, day_str):
    """Bloque de texto de un spot para el report completo."""
    if not entry:
        return ""
    conds  = {**entry, "tide_state": get_tide_state(10)}
    res    = score_spot(spot, conds, hora=10)
    sh     = entry.get("swell_height")    or entry.get("wave_height")     or 0
    sp     = entry.get("swell_period")    or entry.get("wave_period")     or 0
    sd     = degrees_to_dir(entry.get("swell_direction") or entry.get("wave_direction") or 0)
    ws     = entry.get("wind_speed")      or 0
    wd     = degrees_to_dir(entry.get("wind_direction") or 0)
    icon   = SEMAFORO[res["semaforo"]]
    tipo   = TIPO_EMOJI.get(spot["type"], "🌊")
    lines  = [
        f"{icon} {tipo} *{spot['name']}*",
        f"   ↗ {sh:.1f}m · {sp:.0f}s · {sd} | 💨 {wd} {ws:.0f}kts · {conds['tide_state']}"
    ]
    best = get_best_hours(hourly, spot, day_str)
    if best and best[0][1] >= 35:
        horas_str = " ".join([f"{h:02d}h{SEMAFORO[s]}" for h, _, s in best[:2]])
        lines.append(f"   ⏰ Mejor: {horas_str}")
    if res["penalizaciones"]:
        lines.append(f"   ⚠️ _{res['penalizaciones'][0]}_")
    return "\n".join(lines)


# ─── MODO SMART: mejor spot del día (1 llamada SG) ───────────────────────────

def build_smart_briefing(island, day_str=None):
    """
    Briefing matutino completo:
      — Condiciones del día (swells 1/2/3 + viento)
      — Mareas reales scrapeadas de tablademareas.com
      — Mejor spot del día + hora pico + frase de ánimo
    Gasta máximo 1 llamada Stormglass.
    """
    if day_str is None:
        day_str = datetime.now().strftime("%Y-%m-%d")

    day_label = datetime.strptime(day_str, "%Y-%m-%d").strftime("%A %d de %B").capitalize()

    # ── Fetch oleaje ──────────────────────────────────────────────────────────
    _, hourly = get_best_zone_for_island(island, STORMGLASS_KEY)
    if not hourly:
        return ("❌ Sin datos de oleaje. Intenta en unos minutos.", None)
    entry = _ref_entry(hourly, day_str)
    if not entry:
        return ("❌ Sin datos para hoy.", None)

    # ── Fetch mareas ──────────────────────────────────────────────────────────
    tide_data = get_tides(island)

    # ── Datos de oleaje ───────────────────────────────────────────────────────
    sh1  = entry.get("swell_height")      or entry.get("wave_height")    or 0
    sp1  = entry.get("swell_period")      or entry.get("wave_period")    or 0
    _d1  = entry.get("swell_direction")   or entry.get("wave_direction") or 0
    sd1  = f"{degrees_to_dir(_d1)} ({_d1:.0f}°)"
    sh2  = entry.get("swell2_height")
    sp2  = entry.get("swell2_period")
    _d2  = entry.get("swell2_direction")
    sd2  = f"{degrees_to_dir(_d2)} ({_d2:.0f}°)" if _d2 is not None else None
    sh3  = entry.get("swell3_height")
    sp3  = entry.get("swell3_period")
    _d3  = entry.get("swell3_direction")
    sd3  = f"{degrees_to_dir(_d3)} ({_d3:.0f}°)" if _d3 is not None else None
    ws  = entry.get("wind_speed")        or 0
    wd  = degrees_to_dir(entry.get("wind_direction") or 0)

    def wind_label(kts):
        if kts < 5:   return "calma 🪷"
        if kts < 10:  return "suave 😊"
        if kts < 15:  return "moderado"
        if kts < 20:  return "fuerte ⚠️"
        return "muy fuerte 🚨"

    # ── Mejor spot ────────────────────────────────────────────────────────────
    best_score, best_spot, best_entry = -1, None, None
    for spot in SPOTS[island]:
        ref = _ref_entry(hourly, day_str)
        if not ref:
            continue
        res = score_spot(spot, {**ref, "tide_state": get_tide_state(10)}, hora=10)
        if res["score"] > best_score:
            best_score, best_spot, best_entry = res["score"], spot, ref

    # ── Construir mensaje ─────────────────────────────────────────────────────
    L = []

    # Cabecera
    L.append(f"🏄 *SURF REPORT*")
    L.append(f"📅 _{day_label}_")
    L.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
    L.append("")

    # Oleaje
    L.append("🌊 *OLEAJE*")
    L.append(f"  1️⃣  `{sh1:.1f}m · {sp1:.0f}s · {sd1}`")
    if sh2 and sh2 > 0.3:
        L.append(f"  2️⃣  `{sh2:.1f}m · {sp2:.0f}s · {sd2}`")
    if sh3 and sh3 > 0.2:
        L.append(f"  3️⃣  `{sh3:.1f}m · {sp3:.0f}s · {sd3}`")
    L.append("")

    # Viento
    L.append(f"💨 *VIENTO*  `{wd} {ws:.0f}kts` — {wind_label(ws)}")
    L.append("")

    # Mareas
    L.append(format_tides_block(tide_data))
    L.append("")
    L.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
    L.append("")

    # Mejor spot + hype
    if best_spot:
        res  = score_spot(best_spot, {**best_entry, "tide_state": get_tide_state(10)}, hora=10)
        sem  = SEMAFORO[res["semaforo"]]
        tipo = TIPO_EMOJI.get(best_spot["type"], "🌊")
        best_h   = get_best_hours(hourly, best_spot, day_str)
        hora_str = f"⏰ *{best_h[0][0]:02d}:00h*" if best_h and best_h[0][1] >= 30 else ""

        if best_score >= 75:   hype = "🔥 *¡DÍA ÉPICO! Deja lo que sea*"
        elif best_score >= 55: hype = "✅ *Buenas condiciones — merece ir*"
        elif best_score >= 35: hype = "🟡 *Aceptable — tú decides*"
        else:                  hype = "😶 *Hoy el mar no regala mucho*"

        L.append(hype)
        L.append(f"{sem} {tipo} *{best_spot['name'].upper()}*")
        if hora_str:
            L.append(f"  ⏰ Mejor hora: {hora_str}")
        if res["penalizaciones"]:
            L.append(f"  ⚠️ _{res['penalizaciones'][0]}_")
        if tide_data and tide_data.get("coef") and tide_data["coef"] >= 70:
            if best_spot["name"] in ("Igueste", "La Francesa"):
                L.append(f"  🌊 _Mareas vivas — bonus para este spot_ 🙌")
    else:
        L.append("😶 *Hoy el mar no regala nada. Quizás mañana 🤙*")

    L.append("")
    source = "_(Open-Meteo · tablademareas.com)_" if not stormglass_available(STORMGLASS_KEY) \
             else "_(Stormglass · tablademareas.com)_"
    L.append(f"📡 {source}")

    return ("\n".join(L), best_spot["name"] if best_spot else None)


# ─── MODO COMPLETO: todos los spots (4 llamadas SG) ──────────────────────────

def build_full_report(island, day_str=None):
    if day_str is None:
        day_str = datetime.now().strftime("%Y-%m-%d")

    day_label  = datetime.strptime(day_str, "%Y-%m-%d").strftime("%A %d/%m").capitalize()
    all_conds  = get_conditions_for_island(island, STORMGLASS_KEY)
    lines      = [f"🌊 *Report completo — {day_label}*", f"📍 _{island.capitalize()}_\n"]
    any_green  = False

    for spot in SPOTS[island]:
        hourly = get_hourly_for_spot(spot["name"], island, all_conds)
        entry  = _ref_entry(hourly, day_str)
        block  = format_spot_block(spot, entry, hourly, day_str)
        if "🟢" in block:
            any_green = True
        lines.append(block)
        lines.append("")

    if not any_green:
        lines.append("😶 Nada verde hoy. Quizás mañana 🤙")

    source = "Open-Meteo" if not stormglass_available(STORMGLASS_KEY) else "Stormglass + Open-Meteo"
    lines.append(f"_Datos: {source}_")
    return "\n".join(lines)


# ─── HANDLERS ────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("🌴 Estoy en Tenerife"), KeyboardButton("🏝 Estoy en La Graciosa")],
        [KeyboardButton("📊 Report ahora"),       KeyboardButton("📅 Próximos 3 días")]
    ]
    await update.message.reply_text(
        "🤙 *SurfBot activo*\n\n¿Dónde estás hoy?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text    = update.message.text or ""

    if "Tenerife" in text:
        user_island[chat_id] = "tenerife"
        await update.message.reply_text("📍 Tenerife anotado 🤙", parse_mode="Markdown")

    elif "Graciosa" in text:
        user_island[chat_id] = "graciosa"
        await update.message.reply_text("📍 La Graciosa anotada 🤙", parse_mode="Markdown")

    elif "Report ahora" in text or text.startswith("/report"):
        await send_full_report(update, ctx, days=1)

    elif "Próximos 3 días" in text or text.startswith("/forecast"):
        await send_full_report(update, ctx, days=3)

async def send_full_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE, days=1):
    """Report completo bajo demanda (gasta hasta 4 llamadas SG)."""
    chat_id = update.effective_chat.id
    island  = user_island.get(chat_id)
    if not island:
        await update.message.reply_text("¿Dónde estás? Pulsa Tenerife o La Graciosa primero.")
        return

    await update.message.reply_text("⏳ Consultando todos los spots...")
    for d in range(days):
        day = (datetime.now() + timedelta(days=d)).strftime("%Y-%m-%d")
        await update.message.reply_text(build_full_report(island, day), parse_mode="Markdown")


# ─── CALLBACK INLINE (botones del briefing smart) ────────────────────────────

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    data    = query.data or ""
    chat_id = query.message.chat_id
    island  = user_island.get(chat_id, "tenerife")

    if data == "ver_todos":
        await query.message.reply_text("⏳ Consultando todos los spots...")
        await query.message.reply_text(build_full_report(island), parse_mode="Markdown")

    elif data == "no_gracias":
        await query.message.reply_text("👌 Hasta mañana 🤙")

    # Quitar los botones del mensaje original
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass


# ─── BRIEFING DIARIO AUTOMÁTICO (MODO SMART) ─────────────────────────────────

async def daily_briefing(ctx: ContextTypes.DEFAULT_TYPE):
    """
    8:00 AM — Briefing completo en 3 pasos:
      1. Imagen heatmap (tabla spots × horas)
      2. Texto con tendencia de swell + ventana óptima
      3. Texto smart briefing (condiciones + mareas + mejor spot) + botones
    """
    if not MARCOS_CHAT_ID:
        return

    chat_id  = int(MARCOS_CHAT_ID)
    island   = user_island.get(chat_id, "tenerife")
    day_str  = datetime.now().strftime("%Y-%m-%d")

    # ── 1. Fetch datos (1 llamada SG) ─────────────────────────────────────────
    _, hourly_general = get_best_zone_for_island(island, STORMGLASS_KEY)

    # Mapa spot → hourly (reutilizamos los mismos datos para no gastar llamadas)
    hourly_by_spot = {
        spot["name"]: hourly_general
        for spot in SPOTS[island]
    }

    # Datos de swell del día para el título de la imagen
    entry_ref = _ref_entry(hourly_general, day_str) if hourly_general else {}
    swell_summary = {
        "sh1": entry_ref.get("swell_height")    or entry_ref.get("wave_height")    or 0,
        "sp1": entry_ref.get("swell_period")    or entry_ref.get("wave_period")    or 0,
        "sd1": degrees_to_dir(entry_ref.get("swell_direction") or entry_ref.get("wave_direction") or 0),
        "ws":  entry_ref.get("wind_speed")      or 0,
        "wd":  degrees_to_dir(entry_ref.get("wind_direction") or 0),
    }

    # ── 2. Imagen heatmap ─────────────────────────────────────────────────────
    try:
        img_bytes = generate_chart(
            island        = island,
            spots         = SPOTS[island],
            hourly_by_spot= hourly_by_spot,
            day_str       = day_str,
            swell_summary = swell_summary,
        )
        await ctx.bot.send_photo(
            chat_id   = chat_id,
            photo     = img_bytes,
            caption   = f"📊 Tabla horaria — {island.capitalize()}",
        )
    except Exception as e:
        logger.warning(f"No se pudo generar la imagen: {e}")

    # ── 3. Análisis de tendencia ──────────────────────────────────────────────
    try:
        trend_txt = analyze_trend(hourly_general, SPOTS[island], day_str)
        if trend_txt:
            await ctx.bot.send_message(
                chat_id    = chat_id,
                text       = trend_txt,
                parse_mode = "Markdown",
            )
    except Exception as e:
        logger.warning(f"No se pudo calcular tendencia: {e}")

    # ── 4. Briefing smart + botones ───────────────────────────────────────────
    msg, _ = build_smart_briefing(island)

    await ctx.bot.send_message(
        chat_id      = chat_id,
        text         = msg,
        parse_mode   = "Markdown",
        reply_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Ver todos los spots", callback_data="ver_todos"),
            InlineKeyboardButton("👌 No gracias",          callback_data="no_gracias"),
        ]])
    )


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("report",   handle_message))
    app.add_handler(CommandHandler("forecast", handle_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    app.job_queue.run_daily(
        daily_briefing,
        time=dtime(hour=BRIEFING_HOUR, minute=0),
        name="daily_briefing"
    )

    logger.info("SurfBot arrancado 🤙")
    app.run_polling()

if __name__ == "__main__":
    main()
