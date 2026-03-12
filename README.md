# 🤙 SurfBot — Guía de instalación

## Archivos del proyecto
```
surf-bot/
├── bot.py          # Bot principal de Telegram
├── scorer.py       # Motor de puntuación de spots
├── fetcher.py      # Conexión a Open-Meteo y Stormglass
├── spots.py        # Configuración de tus 15 spots
└── requirements.txt
```

---

## Paso 1 — Crear el bot en Telegram

1. Abre Telegram y busca **@BotFather**
2. Escribe `/newbot`
3. Dale un nombre (ej: "Marcos Surf Bot") y un username (ej: `marcossurf_bot`)
4. Copia el **token** que te da (parece: `123456789:ABCdef...`)

---

## Paso 2 — API key de Stormglass (gratis)

1. Ve a [stormglass.io](https://stormglass.io) y crea cuenta
2. En el dashboard copia tu **API key**
3. Plan gratuito: 10 requests/día — suficiente para el aviso diario

---

## Paso 3 — Obtener tu Chat ID de Telegram

1. Arranca el bot (paso 4)
2. Escribe `/start` en el chat con tu bot
3. Ve a: `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
4. Busca el campo `"id"` dentro de `"chat"` — ese es tu chat ID

---

## Paso 4 — Instalar y arrancar

```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
export TELEGRAM_TOKEN="tu_token_de_botfather"
export STORMGLASS_KEY="tu_api_key_de_stormglass"
export MARCOS_CHAT_ID="tu_chat_id"

# Arrancar el bot
python bot.py
```

---

## Paso 5 — Uso del bot

Una vez arrancado, en Telegram:

- **Tenerife / La Graciosa** → le dices dónde estás
- **📊 Report ahora** → semáforo de todos los spots de hoy
- **📅 Próximos 3 días** → previsión extendida
- El bot te manda el briefing **automáticamente a las 8:00** cada mañana

---

## Ejemplo de mensaje que recibirás

```
🌊 Surf Report — Jueves 12/03

📍 Tenerife

🟢 📍 Igueste
   ↗ 2.2m · 10s · NNE | 💨 N 8kts · Pleamar
   ⏰ Mejor: 15h🟢 17h🟡

🟡 🏖 Almáciga
   ↗ 1.4m · 9s · NE | 💨 SSO 12kts · Media
   ⏰ Mejor: 09h🟡

🔴 🏖 Roque de las Bodegas
   ↗ 2.2m · 8s · NE | 💨 ENE 20kts · Bajamar
   ⚠️ periodo corto (8s, mín 10s)
```

---

## Para dejarlo corriendo siempre (opcional)

En un servidor o en tu propio PC con:

```bash
# Con nohup (Linux/Mac)
nohup python bot.py &

# O con screen
screen -S surfbot
python bot.py
# Ctrl+A, D para dejar en background
```

Si quieres hospedarlo gratis en la nube: **Railway.app** o **Render.com**
tienen plan gratuito suficiente para este bot.
