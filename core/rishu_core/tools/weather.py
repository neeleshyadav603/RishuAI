"""Weather from Open-Meteo (free, no key; data under CC BY 4.0)."""

from __future__ import annotations

import httpx

from .registry import ToolResult

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"

_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    80: "rain showers",
    81: "rain showers",
    82: "heavy rain showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with hail",
}


def weather(place: str, transport: httpx.BaseTransport | None = None) -> ToolResult:
    place = place.strip()
    if not place:
        return ToolResult(False, "Which city?")
    try:
        with httpx.Client(transport=transport, timeout=12) as client:
            geo = client.get(
                GEOCODE, params={"name": place, "count": 1, "language": "en", "format": "json"}
            )
            geo.raise_for_status()
            results = geo.json().get("results") or []
            if not results:
                return ToolResult(False, f"I could not find a place called '{place}'.")
            spot = results[0]
            forecast = client.get(
                FORECAST,
                params={
                    "latitude": spot["latitude"],
                    "longitude": spot["longitude"],
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "auto",
                    "forecast_days": 2,
                },
            )
            forecast.raise_for_status()
            data = forecast.json()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return ToolResult(False, f"Weather service not reachable ({type(exc).__name__}).")
    now = data.get("current", {})
    daily = data.get("daily", {})
    name = ", ".join(x for x in (spot.get("name"), spot.get("admin1"), spot.get("country")) if x)

    def first(key: str, index: int = 0) -> str:
        values = daily.get(key) or []
        return str(values[index]) if len(values) > index and values[index] is not None else "?"

    text = (
        f"Weather in {name}: {_CODES.get(int(now.get('weather_code', -1)), 'unknown')}, "
        f"{now.get('temperature_2m', '?')}°C (feels like {now.get('apparent_temperature', '?')}°C), "
        f"humidity {now.get('relative_humidity_2m', '?')}%, wind {now.get('wind_speed_10m', '?')} km/h. "
        f"Today {first('temperature_2m_min')}–{first('temperature_2m_max')}°C, rain chance "
        f"{first('precipitation_probability_max')}%. Tomorrow {first('temperature_2m_min', 1)}–"
        f"{first('temperature_2m_max', 1)}°C, rain chance {first('precipitation_probability_max', 1)}%. "
        "Source: Open-Meteo."
    )
    return ToolResult(True, text, data={"place": name})
