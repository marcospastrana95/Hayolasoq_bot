# Coordenadas marcadas como None = ubicación desconocida, usar punto central de isla como fallback
GRACIOSA_CENTER = (29.2500, -13.5100)

SPOTS = {
    "tenerife": [
        {
            "name": "Almáciga",
            "type": "beach_break",
            "coords": (28.5719, -16.1929),  # verificada
            "swell_dirs": ["N", "NNE", "NNO", "NO", "ONO"],
            "wind_offshore": ["S", "SSO", "SSE", "SO"],
            "tides": ["Media", "Pleamar", "Bajamar"],
            "period_min": 8, "period_max": 14,
            "height_min": 0.6, "height_max": 1.8,
            "notes": "Efecto montaña puede bloquear viento norte. Bancos de arena variables.",
            "special": "low_height_threshold"
        },
        {
            "name": "Roque de las Bodegas",
            "type": "beach_break",
            "coords": (28.5740, -16.1850),  # verificada, junto a Almáciga
            "swell_dirs": ["N", "NNE", "NNO"],
            "wind_offshore": ["NE", "ENE", "E", "ESE"],
            "tides": ["Media", "Bajamar"],
            "period_min": 10, "period_max": 15,
            "height_min": 1.5, "height_max": 2.2,
            "notes": "Beach break increíble pero difícil. Depende de bancos de arena.",
            "special": "sandbars_dependent"
        },
        {
            "name": "Igueste",
            "type": "point_break",
            "coords": (28.5233, -16.1525),  # verificada GPS 28°31'24"N 16°09'09"O
            "swell_dirs": ["NNE", "NE", "N", "NNO"],
            "wind_offshore": ["NNE", "N", "NNO", "NE"],
            "tides": ["Pleamar", "Media"],
            "period_min": 8, "period_max": 30,
            "height_min": 2.0, "height_max": 10.0,
            "notes": "NE entra con menos periodo/tamaño. N/NO necesita mucho periodo.",
            "special": "igueste_logic"
        },
        {
            "name": "Las Gaviotas",
            "type": "beach_break",
            "coords": None,
            "swell_dirs": ["S", "SSO", "SO"],
            "wind_offshore": ["NO", "NNO", "ONO", "N"],
            "tides": ["Media"],
            "period_min": 10, "period_max": 20,
            "height_min": 1.0, "height_max": 2.0,
            "notes": "Ola orillera potente. Necesita sur limpio con fuerza."
        },
        {
            "name": "El Callado",
            "type": "point_break",
            "coords": None,
            "swell_dirs": ["N", "NNE", "NNO", "NO", "ONO"],
            "wind_offshore": ["NE", "ENE", "E", "NNE"],
            "tides": ["Media"],
            "period_min": 10, "period_max": 18,
            "height_min": 1.5, "height_max": 2.0,
            "notes": "Marea baja babosa si está grande. Marea alta muy pegada a las piedras."
        },
        {
            "name": "La Derecha de Las Américas",
            "type": "reef_break",
            "coords": None,
            "swell_dirs": ["NNO", "NO", "ONO"],
            "wind_offshore": ["E", "ESE", "SE"],
            "tides": ["Bajamar", "Media"],
            "period_min": 14, "period_max": 18,
            "height_min": 1.5, "height_max": 3.0,
            "notes": "Mañanas glassy hasta las 10h. Mejor early session.",
            "special": "morning_only"
        },
    ],
    "graciosa": [
        {
            "name": "El Corral",
            "type": "reef_break",
            "coords": (29.241549038375638, -13.526698649147137),  # verificada
            "swell_dirs": ["ONO", "NO", "O", "NNO"],
            "wind_offshore": ["ESE", "SE", "E", "SSE"],
            "tides": ["Media", "Pleamar", "Bajamar"],
            "period_min": 11, "period_max": 16,
            "height_min": 0.8, "height_max": 2.2,
            "notes": "Se pone grande muy rápido. Más oeste = entra más de lleno."
        },
        {
            "name": "Medusa",
            "type": "reef_break",
            "coords": None,
            "swell_dirs": ["NO", "NNO", "ONO", "O"],
            "wind_offshore": ["NE", "ENE", "E"],
            "tides": ["Media", "Pleamar"],
            "period_min": 11, "period_max": 16,
            "height_min": 0.5, "height_max": 1.5,
            "notes": "Slab divertido para giros cuando está pequeño."
        },
        {
            "name": "Baja del Ganado",
            "type": "point_break",
            "coords": None,
            "swell_dirs": ["N", "NNO", "NO", "NNE"],
            "wind_offshore": ["NE", "ENE", "E"],
            "tides": ["Media", "Pleamar"],
            "period_min": 12, "period_max": 15,
            "height_min": 1.5, "height_max": 2.0,
            "notes": "Derecha muy larga. Mar del norte entra menos pero mejor colocado."
        },
        {
            "name": "La Francesa",
            "type": "reef_break",
            "coords": (29.221221611957557, -13.527528047478562),  # verificada
            "swell_dirs": ["O", "ONO", "NO"],
            "wind_offshore": ["NO", "NNO", "N", "ONO"],
            "tides": ["Media", "Pleamar"],
            "period_min": 14, "period_max": 30,
            "height_min": 1.8, "height_max": 10.0,
            "notes": "Mejor con mareas vivas cuando está grande. Cuanto más sube mejor.",
            "special": "spring_tide_bonus"
        },
        {
            "name": "Montaña Amarilla",
            "type": "reef_break",
            "coords": (29.221184157957225, -13.536669015873851),  # verificada
            "swell_dirs": ["ONO", "NO", "O"],
            "wind_offshore": ["NE", "NNE", "ENE"],
            "tides": ["Bajamar", "Media"],
            "period_min": 13, "period_max": 16,
            "height_min": 1.5, "height_max": 2.5,
            "notes": "Funciona mejor con periodos 13-15s. No necesita mucho tamaño."
        },
        {
            "name": "Las Conchas",
            "type": "beach_break",
            "coords": (29.27572690781255, -13.515877472811287),  # verificada
            "swell_dirs": ["NNE", "N", "NNO", "NE"],
            "wind_offshore": ["ENE", "E", "ESE", "NE"],
            "tides": ["Bajamar"],
            "period_min": 9, "period_max": 14,
            "height_min": 1.5, "height_max": 3.0,
            "notes": "Solo funciona cuando la playa está plana (tras borrascas de oeste seguidas).",
            "special": "beach_condition_dependent"
        },
        {
            "name": "El Hueso",
            "type": "reef_break",
            "coords": None,
            "swell_dirs": ["N", "NNO", "NO"],
            "wind_offshore": ["SO", "OSO", "O"],
            "tides": ["Media", "Bajamar"],
            "period_min": 10, "period_max": 16,
            "height_min": 1.5, "height_max": 3.0,
            "notes": ""
        },
        {
            "name": "El Basurero",
            "type": "reef_break",
            "coords": None,
            "swell_dirs": ["N", "NNO", "NO"],
            "wind_offshore": ["ENE", "NE", "E"],
            "tides": ["Media", "Bajamar"],
            "period_min": 14, "period_max": 18,
            "height_min": 1.5, "height_max": 2.4,
            "notes": ""
        },
        {
            "name": "La Alambra",
            "type": "rock_break",
            "coords": (29.27986524427511, -13.495733778041632),  # verificada (playa lambra)
            "swell_dirs": ["N", "NNE", "NNO", "NO"],
            "wind_offshore": ["ONO", "O", "OSO", "SO", "SSO", "S"],
            "tides": ["Media", "Pleamar", "Bajamar"],
            "period_min": 10, "period_max": 16,
            "height_min": 1.5, "height_max": 3.0,
            "notes": ""
        },
    ]
}
