#!/usr/bin/env python3
"""
SurfBot para Marcos — Bot de Telegram
Flujo:
  /start → selección isla → briefing rápido Open-Meteo + mejor zona sugerida
         → selección zona → imagen heatmap + análisis detallado (SG + OM)
Briefing diario 8:00 AM → imagen + tendencia + texto smart
"""

import os
import logging
from datetime import datetime, time as dtime, timedelta

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

from spots import SPOTS
from fetcher import (
    get_best_zone_for_island, get_conditions_for_island, get_conditions_for_spot,
    get_hourly_for_spot, get_tide_state, stormglass_available,
    get_openmeteo, ZONAS, SPOT_ZONA
)
from scorer import score_spot, degrees_to_dir
from tides import get_tides, format_tides_block
from chart import generate_chart, analyze_trend

# ─── CONFIG ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
STORMGLASS_KEY = os.environ.get("STORMGLASS_KEY", "")
MARCOS_CHAT_ID = os.environ.get("MARCOS_CHAT_ID", "")
BRIEFING_HOUR  = 8

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_island = {}
user_zone   = {}

SEMAFORO   = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}
TIPO_EMOJI = {"beach_break": "🏖", "reef_break": "🪸", "point_break": "📍", "rock_break": "🪨"}

ZONAS_TENERIFE = {
    "anaga": {"label": "Anaga",  "emoji": "🏔", "spots": ["Almáciga", "Roque de las Bodegas", "Igueste"]},
    "norte": {"label": "Norte",  "emoji": "🌊", "spots": ["Las Gaviotas", "El Callado"]},
    "sur":   {"label": "Sur",    "emoji": "☀️", "spots": ["La Derecha de Las Américas"]},
}

def _ref_entry(hourly, day_str, hour=10):
    for h in hourly:
        if h["time"].startswith(f"{day_str}T{hour:02d}") or \
           h["time"].startswith(f"{day_str} {hour:02d}"):
            return h
    return next((h for h in hourly if h["time"].startswith(day_str)), None)

def get_best_hours(hourly, spot, day_str):
    scored = []
    for entry in (h for h in hourly if h["time"].startswith(day_str)):
        hour   = int(entry["time"][11:13]) if "T" in entry["time"] else int(entry["time"][8:10])
        result = score_spot(spot, {**entry, "tide_state": get_tide_state(hour)}, hora=hour)
        scored.append((hour, result["score"], result["semaforo"]))
    scored.sort(key=lambda x: -x[1])
    return scored[:3]

def wind_label(kts):
    if kts < 5:   return "calma 🪷"
    if kts < 10:  return "suave 😊"
    if kts < 15:  return "moderado"
    if kts < 20:  return "fuerte ⚠️"
    return "muy fuerte 🚨"

def build_island_briefing(island, day_str=None):
    if day_str is None:
        day_str = datetime.now().strftime("%Y-%m-%d")
    day_label = datetime.strptime(day_str, "%Y-%m-%d").strftime("%A %d de %B").capitalize()

    if island == "graciosa":
        lat, lon  = ZONAS["graciosa"]
        hourly    = get_openmeteo(lat, lon, days=1)
        best_zona = "graciosa"
    else:
        hourly    = get_openmeteo(28.52, -16.30, days=1)
        best_zona = _calc_best_zona_tenerife(day_str)

    if not hourly:
        return ("❌ Sin datos de oleaje.", None)
    entry = _ref_entry(hourly, day_str)
    if not entry:
        return ("❌ Sin datos para hoy.", None)

    sh = entry.get("swell_height") or entry.get("wave_height") or 0
    sp = entry.get("swell_period") or entry.get("wave_period") or 0
    _d = entry.get("swell_direction") or entry.get("wave_direction") or 0
    sd = f"{degrees_to_dir(_d)} ({_d:.0f}°)"
    ws = entry.get("wind_speed") or 0
    wd = degrees_to_dir(entry.get("wind_direction") or 0)

    mañana = [e for e in hourly if e["time"].startswith(day_str) and
              6 <= (int(e["time"][11:13]) if "T" in e["time"] else 0) <= 12]
    tarde  = [e for e in hourly if e["time"].startswith(day_str) and
              13 <= (int(e["time"][11:13]) if "T" in e["time"] else 0) <= 20]

    def avg_sh(lst):
        vals = [e.get("swell_height") or e.get("wave_height") or 0 for e in lst]
        return sum(vals)/len(vals) if vals else 0

    diff = avg_sh(tarde) - avg_sh(mañana)
    if diff > 0.15:    trend = "📈 Swell subiendo a lo largo del día"
    elif diff < -0.15: trend = "📉 Swell bajando, mejor por la mañana"
    else:              trend = "➡️ Swell estable todo el día"

    if island == "graciosa":
        zona_label = "La Graciosa"; zona_emoji = "🏝"
    else:
        zona_info  = ZONAS_TENERIFE.get(best_zona, {})
        zona_label = zona_info.get("label", best_zona.capitalize())
        zona_emoji = zona_info.get("emoji", "📍")

    L = [
        f"🌊 *Condiciones hoy — {day_label}*", "",
        f"  `{sh:.1f}m · {sp:.0f}s · {sd}`",
        f"  💨 `{wd} {ws:.0f}kts` — {wind_label(ws)}", "",
        f"  {trend}", "",
        f"⭐ Mejor zona hoy: *{zona_emoji} {zona_label}*", "",
        "_Datos: Open-Meteo_",
    ]
    return ("\n".join(L), best_zona)

def _calc_best_zona_tenerife(day_str):
    best_zona = "anaga"; best_score = -1
    for zona, info in ZONAS_TENERIFE.items():
        lat, lon = ZONAS["tenerife"][zona]
        om = get_openmeteo(lat, lon, days=1)
        if not om: continue
        ref = _ref_entry(om, day_str)
        if not ref: continue
        zona_spots = [s for s in SPOTS["tenerife"] if s["name"] in info["spots"]]
        if not zona_spots: continue
        hour = int(ref["time"][11:13]) if "T" in ref["time"] else 10
        avg  = sum(score_spot(s, {**ref, "tide_state": get_tide_state(hour)}, hora=hour)["score"]
                   for s in zona_spots) / len(zona_spots)
        if avg > best_score:
            best_score = avg; best_zona = zona
    return best_zona

def zona_keyboard(island, best_zona):
    if island == "graciosa":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🏝 Ver La Graciosa", callback_data="zona_graciosa")
        ]])
    row = []
    for zona, info in ZONAS_TENERIFE.items():
        star  = "⭐ " if zona == best_zona else ""
        label = f"{star}{info['emoji']} {info['label']}"
        row.append(InlineKeyboardButton(label, callback_data=f"zona_{zona}"))
    return InlineKeyboardMarkup([row])

async def send_zona_report(chat_id, island, zona, ctx):
    day_str = datetime.now().strftime("%Y-%m-%d")
    await ctx.bot.send_message(chat_id=chat_id, text="⏳ Consultando datos detallados...")

    if island == "graciosa":
        spots    = SPOTS["graciosa"]
        lat, lon = ZONAS["graciosa"]
    else:
        zona_info  = ZONAS_TENERIFE.get(zona, {})
        spot_names = zona_info.get("spots", [])
        spots      = [s for s in SPOTS["tenerife"] if s["name"] in spot_names]
        lat, lon   = ZONAS["tenerife"].get(zona, ZONAS["tenerife"]["anaga"])

    hourly = get_conditions_for_spot(lat, lon, STORMGLASS_KEY)
    if not hourly:
        await ctx.bot.send_message(chat_id=chat_id, text="❌ Sin datos para esta zona.")
        return

    hourly_by_spot = {s["name"]: hourly for s in spots}
    entry_ref      = _ref_entry(hourly, day_str) or {}
    swell_summary  = {
        "sh1": entry_ref.get("swell_height") or entry_ref.get("wave_height") or 0,
        "sp1": entry_ref.get("swell_period") or entry_ref.get("wave_period") or 0,
        "sd1": degrees_to_dir(entry_ref.get("swell_direction") or entry_ref.get("wave_direction") or 0),
        "ws":  entry_ref.get("wind_speed") or 0,
        "wd":  degrees_to_dir(entry_ref.get("wind_direction") or 0),
    }

    try:
        img_bytes  = generate_chart(
            island=island if island == "graciosa" else zona,
            spots=spots, hourly_by_spot=hourly_by_spot,
            day_str=day_str, swell_summary=swell_summary,
        )
        zona_label = ZONAS_TENERIFE.get(zona, {}).get("label", zona.capitalize()) \
                     if island != "graciosa" else "La Graciosa"
        await ctx.bot.send_photo(chat_id=chat_id, photo=img_bytes,
                                  caption=f"📊 {zona_label} — {day_str}")
    except Exception as e:
        logger.warning(f"Error imagen: {e}")

    try:
        trend_txt = analyze_trend(hourly, spots, day_str)
        if trend_txt:
            await ctx.bot.send_message(chat_id=chat_id, text=trend_txt, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Error tendencia: {e}")

    lines = []
    for spot in spots:
        entry = _ref_entry(hourly, day_str)
        if not entry: continue
        conds = {**entry, "tide_state": get_tide_state(10)}
        res   = score_spot(spot, conds, hora=10)
        sh    = entry.get("swell_height") or entry.get("wave_height") or 0
        sp    = entry.get("swell_period") or entry.get("wave_period") or 0
        sd    = degrees_to_dir(entry.get("swell_direction") or entry.get("wave_direction") or 0)
        ws    = entry.get("wind_speed") or 0
        wd    = degrees_to_dir(entry.get("wind_direction") or 0)
        sem   = SEMAFORO[res["semaforo"]]
        tipo  = TIPO_EMOJI.get(spot["type"], "🌊")
        best  = get_best_hours(hourly, spot, day_str)
        lines.append(f"{sem} {tipo} *{spot['name']}*")
        lines.append(f"   ↗ {sh:.1f}m · {sp:.0f}s · {sd} | 💨 {wd} {ws:.0f}kts")
        if best and best[0][1] >= 30:
            h_str = " ".join([f"{h:02d}h{SEMAFORO[s]}" for h, _, s in best[:2]])
            lines.append(f"   ⏰ Mejor: {h_str}")
        if res["penalizaciones"]:
            lines.append(f"   ⚠️ _{res['penalizaciones'][0]}_")
        lines.append("")

    if lines:
        source = "Open-Meteo" if not stormglass_available(STORMGLASS_KEY) else "Stormglass + Open-Meteo"
        lines.append(f"_Datos: {source}_")
        await ctx.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="Markdown")

def build_smart_briefing(island, day_str=None):
    if day_str is None:
        day_str = datetime.now().strftime("%Y-%m-%d")
    day_label = datetime.strptime(day_str, "%Y-%m-%d").strftime("%A %d de %B").capitalize()

    _, hourly = get_best_zone_for_island(island, STORMGLASS_KEY)
    if not hourly: return ("❌ Sin datos de oleaje.", None)
    entry = _ref_entry(hourly, day_str)
    if not entry: return ("❌ Sin datos para hoy.", None)

    tide_data = get_tides(island)
    sh1 = entry.get("swell_height") or entry.get("wave_height") or 0
    sp1 = entry.get("swell_period") or entry.get("wave_period") or 0
    _d1 = entry.get("swell_direction") or entry.get("wave_direction") or 0
    sd1 = f"{degrees_to_dir(_d1)} ({_d1:.0f}°)"
    sh2 = entry.get("swell2_height"); sp2 = entry.get("swell2_period")
    _d2 = entry.get("swell2_direction")
    sd2 = f"{degrees_to_dir(_d2)} ({_d2:.0f}°)" if _d2 else None
    sh3 = entry.get("swell3_height"); sp3 = entry.get("swell3_period")
    _d3 = entry.get("swell3_direction")
    sd3 = f"{degrees_to_dir(_d3)} ({_d3:.0f}°)" if _d3 else None
    ws  = entry.get("wind_speed") or 0
    wd  = degrees_to_dir(entry.get("wind_direction") or 0)

    best_score, best_spot = -1, None
    for spot in SPOTS[island]:
        res = score_spot(spot, {**entry, "tide_state": get_tide_state(10)}, hora=10)
        if res["score"] > best_score:
            best_score, best_spot = res["score"], spot

    L = [f"🏄 *SURF REPORT*", f"📅 _{day_label}_",
         "━━━━━━━━━━━━━━━━━━━━━━━━━━", "",
         "🌊 *OLEAJE*", f"  1️⃣  `{sh1:.1f}m · {sp1:.0f}s · {sd1}`"]
    if sh2 and sh2 > 0.3: L.append(f"  2️⃣  `{sh2:.1f}m · {sp2:.0f}s · {sd2}`")
    if sh3 and sh3 > 0.2: L.append(f"  3️⃣  `{sh3:.1f}m · {sp3:.0f}s · {sd3}`")
    L += ["", f"💨 *VIENTO*  `{wd} {ws:.0f}kts` — {wind_label(ws)}", ""]
    L.append(format_tides_block(tide_data))
    L += ["", "━━━━━━━━━━━━━━━━━━━━━━━━━━", ""]

    if best_spot:
        res  = score_spot(best_spot, {**entry, "tide_state": get_tide_state(10)}, hora=10)
        sem  = SEMAFORO[res["semaforo"]]; tipo = TIPO_EMOJI.get(best_spot["type"], "🌊")
        best_h   = get_best_hours(hourly, best_spot, day_str)
        hora_str = f"⏰ *{best_h[0][0]:02d}:00h*" if best_h and best_h[0][1] >= 30 else ""
        if best_score >= 75:   hype = "🔥 *¡DÍA ÉPICO! Deja lo que sea*"
        elif best_score >= 55: hype = "✅ *Buenas condiciones — merece ir*"
        elif best_score >= 35: hype = "🟡 *Aceptable — tú decides*"
        else:                  hype = "😶 *Hoy el mar no regala mucho*"
        L += [hype, f"{sem} {tipo} *{best_spot['name'].upper()}*"]
        if hora_str: L.append(f"  {hora_str}")
        if res["penalizaciones"]: L.append(f"  ⚠️ _{res['penalizaciones'][0]}_")
        if tide_data and tide_data.get("coef") and tide_data["coef"] >= 70:
            if best_spot["name"] in ("Igueste", "La Francesa"):
                L.append("  🌊 _Mareas vivas — bonus para este spot_ 🙌")
    else:
        L.append("😶 *Hoy el mar no regala nada. Quizás mañana 🤙*")
    L.append("")
    source = "_(Open-Meteo · tablademareas.com)_" if not stormglass_available(STORMGLASS_KEY) \
             else "_(Stormglass · tablademareas.com)_"
    L.append(f"📡 {source}")
    return ("\n".join(L), best_spot["name"] if best_spot else None)

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤙 *SurfBot activo*\n\n¿Dónde estás hoy?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🌴 Tenerife",    callback_data="isla_tenerife"),
            InlineKeyboardButton("🏝 La Graciosa", callback_data="isla_graciosa"),
        ]])
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if text.startswith("/report"):   await cmd_report(update, ctx)
    elif text.startswith("/forecast"): await cmd_forecast(update, ctx)

async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    island  = user_island.get(chat_id)
    if not island:
        await update.message.reply_text("Primero dime dónde estás → /start"); return
    await show_zone_selector(chat_id, island, ctx)

async def cmd_forecast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    island  = user_island.get(chat_id, "tenerife")
    await show_zone_selector(chat_id, island, ctx)

async def show_zone_selector(chat_id, island, ctx):
    briefing_txt, best_zona = build_island_briefing(island)
    await ctx.bot.send_message(chat_id=chat_id, text=briefing_txt, parse_mode="Markdown")
    await ctx.bot.send_message(
        chat_id      = chat_id,
        text         = "📍 *¿Qué zona quieres ver?*",
        parse_mode   = "Markdown",
        reply_markup = zona_keyboard(island, best_zona),
    )

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    data    = query.data or ""
    chat_id = query.message.chat_id

    if data.startswith("isla_"):
        island = data.replace("isla_", "")
        user_island[chat_id] = island
        try: await query.edit_message_reply_markup(reply_markup=None)
        except Exception: pass
        await show_zone_selector(chat_id, island, ctx)

    elif data.startswith("zona_"):
        zona   = data.replace("zona_", "")
        island = user_island.get(chat_id, "tenerife")
        user_zone[chat_id] = zona
        try: await query.edit_message_reply_markup(reply_markup=None)
        except Exception: pass
        await send_zona_report(chat_id, island, zona, ctx)

    elif data == "ver_todos":
        island = user_island.get(chat_id, "tenerife")
        try: await query.edit_message_reply_markup(reply_markup=None)
        except Exception: pass
        await show_zone_selector(chat_id, island, ctx)

    elif data == "no_gracias":
        await query.message.reply_text("👌 Hasta mañana 🤙")
        try: await query.edit_message_reply_markup(reply_markup=None)
        except Exception: pass

async def daily_briefing(ctx: ContextTypes.DEFAULT_TYPE):
    if not MARCOS_CHAT_ID: return
    chat_id  = int(MARCOS_CHAT_ID)
    island   = user_island.get(chat_id, "tenerife")
    day_str  = datetime.now().strftime("%Y-%m-%d")

    _, hourly      = get_best_zone_for_island(island, STORMGLASS_KEY)
    hourly_by_spot = {spot["name"]: hourly for spot in SPOTS[island]}
    entry_ref      = _ref_entry(hourly, day_str) if hourly else {}
    swell_summary  = {
        "sh1": entry_ref.get("swell_height") or entry_ref.get("wave_height") or 0,
        "sp1": entry_ref.get("swell_period") or entry_ref.get("wave_period") or 0,
        "sd1": degrees_to_dir(entry_ref.get("swell_direction") or entry_ref.get("wave_direction") or 0),
        "ws":  entry_ref.get("wind_speed") or 0,
        "wd":  degrees_to_dir(entry_ref.get("wind_direction") or 0),
    }

    try:
        img_bytes = generate_chart(island=island, spots=SPOTS[island],
                                    hourly_by_spot=hourly_by_spot,
                                    day_str=day_str, swell_summary=swell_summary)
        await ctx.bot.send_photo(chat_id=chat_id, photo=img_bytes,
                                  caption=f"📊 {island.capitalize()} — {day_str}")
    except Exception as e:
        logger.warning(f"Error imagen: {e}")

    try:
        trend_txt = analyze_trend(hourly, SPOTS[island], day_str)
        if trend_txt:
            await ctx.bot.send_message(chat_id=chat_id, text=trend_txt, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Error tendencia: {e}")

    msg, _ = build_smart_briefing(island)
    await ctx.bot.send_message(
        chat_id=chat_id, text=msg, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Ver todos los spots", callback_data="ver_todos"),
            InlineKeyboardButton("👌 No gracias",          callback_data="no_gracias"),
        ]])
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("report",   cmd_report))
    app.add_handler(CommandHandler("forecast", cmd_forecast))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.job_queue.run_daily(daily_briefing, time=dtime(hour=BRIEFING_HOUR, minute=0), name="daily_briefing")
    logger.info("SurfBot arrancado 🤙")
    app.run_polling()

if __name__ == "__main__":
    main()
