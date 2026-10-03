import requests

LAT = 40.7812
LON = -73.9665

HEADERS = {
    "User-Agent": "kalshi-weather-research/0.1"
}

# Find the NWS gridpoint for Central Park
point_url = f"https://api.weather.gov/points/{LAT},{LON}"

point = requests.get(
    point_url,
    headers=HEADERS,
    timeout=10,
)

point.raise_for_status()

props = point.json()["properties"]

print("Forecast office:", props["gridId"])
print("Grid X:", props["gridX"])
print("Grid Y:", props["gridY"])
print("Forecast URL:", props["forecast"])
print("Hourly URL:", props["forecastHourly"])

# Pull hourly forecast
hourly = requests.get(
    props["forecastHourly"],
    headers=HEADERS,
    timeout=10,
)

hourly.raise_for_status()

periods = hourly.json()["properties"]["periods"]

print("\nNEXT 24 HOURS")
print("-" * 60)

for period in periods[:24]:
    print(
        period["startTime"],
        f"{period['temperature']}°{period['temperatureUnit']}",
        period["shortForecast"],
    )