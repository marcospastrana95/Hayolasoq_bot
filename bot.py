
#!/usr/bin/env python3
"""
SurfBot para Marcos - Bot de Telegram
Combina Open-Meteo (7 días) + Stormglass (hoy preciso)
"""

import os
import asyncio
import logging
from datetime import datetime, time as dtime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, JobQueue
)

from spots import SPOTS
from fetcher import get_conditions_for_spot, get_tide_state
from scorer import score_spot, degrees_to_dir

# ─── CONFIG ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "TU_TOKEN_AQUI")
STORMGLASS_KEY = os.environ.get("STORMGLASS_KEY", "TU_API_KEY_AQUI")
MARCOS_CHAT_ID = os.environ.get("MARCOS_CHAT_ID", "")  # Tu chat ID de Telegram
BRIEFING_HOUR  = 8   # Hora del aviso diario (8:00 AM)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Estado en memoria (qué isla está Marcos)
user_island = {}

# ─── EMOJIS ──────────────────────────────────────────────────────────────────
SEMAFORO = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}
TIPO_EMOJI = {
    "beach_break": "🏖", "reef_break": "🪸",
    "point_break": "📍", "rock_break": "🪨"
}

# ─── LÓGICA PRINCIPAL ─────────────────────────────────────────────────────────

def get_best_hours(hourly_data, spot, day_str):
    """Devuelve las 3 mejores horas del día para un spot."""
    day_hours = [h for h in hourly_data if h["time"].startswith(day_str)]
    scored = []
    for entry in day_hours:
        hour = int(entry["time"][11:13])
        tide = get_tide_state(hour)
        conds = {**entry, "tide_state": tide}
        result = score_spot(spot, conds, hora=hour)
        scored.append((hour, result["score"], result["semaforo"]))
    scored.sort(key=lambda x: -x[1])
    return scored[:3]

def build_briefing(island, hourly_data, day_str=None):
    """Construye el mensaje de briefing para una isla."""
    if day_str is None:
        day_str = datetime.now().strftime("%Y-%m-%d")

    day_label = datetime.strptime(day_str, "%Y-%m-%d").strftime("%A %d/%m").capitalize()
    spots = SPOTS[island]

    lines = [f"🌊 *Surf Report — {day_label}*"]
    lines.append(f"📍 _{island.capitalize()}_\n")

    any_green = False
    for spot in spots:
        # Coger condiciones de la hora pico del día (10:00 como referencia)
        ref_entries = [h for h in hourly_data if h["time"].startswith(day_str + "T10")]
        if not ref_entries:
            ref_entries = [h for h in hourly_data if h["time"].startswith(day_str)]
        if not ref_entries:
            continue

        entry = ref_entries[0]
        hour = 10
        tide = get_tide_state(hour)
        conds = {**entry, "tide_state": tide}
        result = score_spot(spot, conds, hora=hour)

        sem = result["semaforo"]
        if sem == "verde":
            any_green = True

        icon = SEMAFORO[sem]
        tipo = TIPO_EMOJI.get(spot["type"], "🌊")
        name = spot["name"]

        # Datos clave
        sh = entry.get("swell_height") or entry.get("wave_height") or 0
        sp = entry.get("swell_period") or entry.get("wave_period") or 0
        sd = degrees_to_dir(entry.get("swell_direction") or entry.get("wave_direction") or 0)
        ws = entry.get("wind_speed") or 0
        wd = degrees_to_dir(entry.get("wind_direction") or 0)

        lines.append(f"{icon} {tipo} *{name}*")
        lines.append(f"   ↗ {sh:.1f}m · {sp:.0f}s · {sd} | 💨 {wd} {ws:.0f}kts · {tide}")

        # Mejores horas
        best = get_best_hours(hourly_data, spot, day_str)
        if best and best[0][1] >= 35:
            horas_str = " ".join([f"{h:02d}h{SEMAFORO[s]}" for h, _, s in best[:2]])
            lines.append(f"   ⏰ Mejor: {horas_str}")

        if result["penalizaciones"]:
            lines.append(f"   ⚠️ _{result['penalizaciones'][0]}_")
        lines.append("")

    if not any_green:
        lines.append("😶 Hoy no hay nada verde. Quizás mañana 🤙")

    lines.append("_Datos: Stormglass + Open-Meteo_")
    return "\n".join(lines)


# ─── HANDLERS DE TELEGRAM ────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    keyboard = [
        [KeyboardButton("🌴 Estoy en Tenerife"), KeyboardButton("🏝 Estoy en La Graciosa")],
        [KeyboardButton("📊 Report ahora"), KeyboardButton("📅 Próximos 3 días")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🤙 *SurfBot activo*\n\n¿Dónde estás hoy?",
        parse_mode="Markdown",
        reply_markup=markup
    )

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text

    if "Tenerife" in text:
        user_island[chat_id] = "tenerife"
        await update.message.reply_text("📍 Tenerife anotado. Escribe /report para ver las condiciones.")

    elif "Graciosa" in text:
        user_island[chat_id] = "graciosa"
        await update.message.reply_text("📍 La Graciosa anotada. Escribe /report para ver las condiciones.")

    elif "Report ahora" in text or "/report" in text:
        await send_report(update, ctx, days=1)

    elif "Próximos 3 días" in text or "/forecast" in text:
        await send_report(update, ctx, days=3)

async def send_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE, days=1):
    chat_id = update.effective_chat.id
    island = user_island.get(chat_id)

    if not island:
        await update.message.reply_text("¿Dónde estás? Pulsa Tenerife o La Graciosa primero.")
        return

    await update.message.reply_text("⏳ Consultando oleaje...")

    # Coordenadas representativas de cada isla
    coords = {
        "tenerife": (28.52, -16.17),
        "graciosa": (29.24, -13.52)
    }
    lat, lon = coords[island]

    # Fetch de datos (Stormglass hoy + Open-Meteo resto)
    hourly = get_conditions_for_spot(lat, lon, STORMGLASS_KEY)
    if not hourly:
        await update.message.reply_text("❌ Error obteniendo datos. Intenta de nuevo.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    msgs = []
    for d in range(days):
        from datetime import timedelta
        day = (datetime.now() + timedelta(days=d)).strftime("%Y-%m-%d")
        msgs.append(build_briefing(island, hourly, day))

    for msg in msgs:
        await update.message.reply_text(msg, parse_mode="Markdown")


# ─── BRIEFING DIARIO AUTOMÁTICO ───────────────────────────────────────────────

async def daily_briefing(ctx: ContextTypes.DEFAULT_TYPE):
    """Se ejecuta cada mañana a las 8:00."""
    if not MARCOS_CHAT_ID:
        return

    island = user_island.get(int(MARCOS_CHAT_ID), "tenerife")
    coords = {
        "tenerife": (28.52, -16.17),
        "graciosa": (29.24, -13.52)
    }
    lat, lon = coords[island]
    hourly = get_conditions_for_spot(lat, lon, STORMGLASS_KEY)
    if not hourly:
        return

    msg = build_briefing(island, hourly)
    await ctx.bot.send_message(
        chat_id=MARCOS_CHAT_ID,
        text=msg,
        parse_mode="Markdown"
    )


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", handle_message))
    app.add_handler(CommandHandler("forecast", handle_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Job diario a las 8:00
    job_queue = app.job_queue
    job_queue.run_daily(
        daily_briefing,
        time=dtime(hour=BRIEFING_HOUR, minute=0),
        name="daily_briefing"
    )

    logger.info("SurfBot arrancado. Esperando mensajes...")
    app.run_polling()

if __name__ == "__main__":
    main()
