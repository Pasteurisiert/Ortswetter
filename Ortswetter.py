import requests
import datetime as dt
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

# ---------- Hilfsfunktionen ----------

def geocode_location(name, country=None):
    """Ort über Open-Meteo Geocoding-API auflösen."""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": name,
        "count": 1,
        "language": "de",
        "format": "json"
    }
    if country:
        params["country"] = country

    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data.get("results"):
        raise ValueError(f"Ort '{name}' nicht gefunden")

    loc = data["results"][0]
    return {
        "name": loc["name"],
        "lat": loc["latitude"],
        "lon": loc["longitude"],
        "country": loc.get("country"),
        "timezone": loc.get("timezone", "auto")
    }

def fetch_weather(lat, lon, timezone, past_days=8, forecast_days=16):
    """Stündliche Daten für T/Taupunkt/Niederschlag + tägliche Daten für Wind."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join([
            "temperature_2m",
            "dew_point_2m",
            "precipitation",
            "rain",
            "snowfall"
        ]),
        "daily": ",".join([
            "wind_speed_10m_max",
            "wind_speed_10m_min",
            "wind_gusts_10m_max"
        ]),  # tägliche Windwerte[web:3][web:53]
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": timezone
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    # stündlich
    hourly = pd.DataFrame(data["hourly"])
    hourly["time"] = pd.to_datetime(hourly["time"])
    hourly.set_index("time", inplace=True)

    # täglich (Wind)
    daily = pd.DataFrame(data["daily"])
    daily["time"] = pd.to_datetime(daily["time"])
    daily.set_index("time", inplace=True)

    return hourly, daily

def aggregate_daily_precip(df_hourly):
    """24h-Summen von Niederschlag / Regen / Schneefall."""
    daily = df_hourly[["precipitation", "rain", "snowfall"]].resample("1D").sum()
    return daily

def daily_min_max_temp_and_dew(df_hourly):
    """Tagesweises Tmin/Tmax und mittlerer Taupunkt."""
    agg = pd.DataFrame()
    agg["tmin"] = df_hourly["temperature_2m"].resample("1D").min()
    agg["tmax"] = df_hourly["temperature_2m"].resample("1D").max()
    agg["dew_mean"] = df_hourly["dew_point_2m"].resample("1D").mean()
    return agg


def select_location():
    print("Bitte Ort auswählen:")
    for i, (name, country) in enumerate(PRESET_LOCATIONS, start=1):
        print(f"{i:2d}) {name}, {country}")
    print("11) Freie Eingabe")

    while True:
        choice = input("Auswahl (1–11): ").strip()
        try:
            num = int(choice)
        except ValueError:
            print("Bitte eine Zahl eingeben.")
            continue

        if 1 <= num <= 10:
            name, country = PRESET_LOCATIONS[num - 1]
            return name, country
        elif num == 11:
            ort = input("Ort eingeben (z.B. 'Fislisbach'): ").strip()
            land = input("Optional: Ländercode (z.B. 'CH', leer für automatisch): ").strip() or None
            return ort, land
        else:
            print("Ungültige Auswahl, bitte erneut versuchen.")

def streamlit_select_location():
    st.sidebar.header("Standortwahl")
    options = [f"{name}, {country}" for name, country in PRESET_LOCATIONS] + ["Freie Eingabe"]
    choice = st.sidebar.selectbox("Ort auswählen", options)  # Dropdown im Sidebar[web:124][web:130]

    if choice != "Freie Eingabe":
        idx = options.index(choice)
        name, country = PRESET_LOCATIONS[idx]
        return name, country
    else:
        ort = st.sidebar.text_input("Ort (z.B. 'Fislisbach')", "")
        land = st.sidebar.text_input("Ländercode (z.B. 'CH', optional)", "")
        if not ort:
            st.stop()  # warten, bis Ort eingetragen ist
        return ort, (land or None)



# ---------- Hauptlogik ----------

def main():
    # ort, land = select_location()

    # loc = geocode_location(ort, land)
    # label = f"{loc['name']}, {loc.get('country', '')} (lat={loc['lat']:.3f}, lon={loc['lon']:.3f})"
    # print("Verwende Standort:", label)

    # df_hourly, df_daily_wind = fetch_weather(loc["lat"], loc["lon"], loc["timezone"])
    
    st.title("Open-Meteo Wetterübersicht (10 Tage zurück, 16 Tage voraus)")

    ort, land = streamlit_select_location()

    try:
        loc = geocode_location(ort, land)
    except Exception as e:
        st.error(f"Fehler bei Geocoding: {e}")
        st.stop()

    label = f"{loc['name']}, {loc.get('country', '')} (lat={loc['lat']:.3f}, lon={loc['lon']:.3f})"
    st.markdown(f"**Verwendeter Standort:** {label}")

    try:
        df_hourly, df_daily_wind = fetch_weather(loc["lat"], loc["lon"], loc["timezone"])
    except Exception as e:
        st.error(f"Fehler beim Abrufen der Wetterdaten: {e}")
        st.stop()

    # Tagesaggregation aus stündlichen Daten
    daily_temp_dew = daily_min_max_temp_and_dew(df_hourly)
    daily_precip = aggregate_daily_precip(df_hourly)

    # Heutiges Datum (ohne Zeit)
    today = pd.Timestamp(dt.date.today())

    # 1x3 Subplots mit gemeinsamer x-Achse
    fig, axes = plt.subplots(1, 3, figsize=(13, 7), sharex=True)
    ax1, ax2, ax3 = axes

    # ---- Plot 1: Temperatur & Taupunkt ----
    ax1.plot(daily_temp_dew.index, daily_temp_dew["tmin"], label="Tmin [°C]")
    ax1.plot(daily_temp_dew.index, daily_temp_dew["tmax"], label="Tmax [°C]")
    ax1.plot(daily_temp_dew.index, daily_temp_dew["dew_mean"], label="Taupunkt Mittel [°C]")
    ax1.axvline(today, color="red", linestyle="--", linewidth=2, label="Heute")
    ax1.set_ylabel("Temperatur [°C]")
    ax1.set_title("Min/Max Temperatur & Taupunkt")
    ax1.grid(True, alpha=0.3)
    ax1.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.25),   # unterhalb der x-Achse, zentriert im Subplot[web:87][web:88][web:97]
        borderaxespad=0.0,
        ncol=2,
        fontsize=8,
        frameon=False
    )

    # ---- Plot 2: Niederschlag/Schnee (24h) ----
    x = daily_precip.index
    rain = daily_precip["rain"]
    snow = daily_precip["snowfall"]
    total = daily_precip["precipitation"]

    ax2.bar(x, rain, label="Regen [mm]", color="tab:blue")
    ax2.bar(x, snow, bottom=rain, label="Schneefall [mm]", color="tab:cyan")
    ax2.plot(x, total, color="black", linestyle="--", label="Gesamt [mm]")
    ax2.axvline(today, color="red", linestyle="--", linewidth=2, label="Heute")
    ax2.set_ylabel("Niederschlag [mm]")
    ax2.set_title("Niederschlag & Schnee (24h-Summen)")
    ax2.grid(True, axis="y", alpha=0.3)
    ax2.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.25),
        borderaxespad=0.0,
        ncol=2,
        fontsize=8,
        frameon=False
    )

    # ---- Plot 3: Wind (min/max + Böen, mit Stufen) ----
    strong_wind_th = 39.0   # km/h, starker Wind (≈ Beaufort 6)[web:75][web:76][web:78]
    storm_th       = 50.0   # km/h, Sturm / Near Gale (≈ Beaufort 7)[web:75][web:76][web:78]
    max_fill       = 89.0   # km/h, Obergrenze der Schattierung

    wd = df_daily_wind

    # Linien: min/max Wind + Böen
    ax3.plot(wd.index, wd["wind_speed_10m_min"], label="Wind min [km/h]", color="tab:green")
    ax3.plot(wd.index, wd["wind_speed_10m_max"], label="Wind max [km/h]", color="tab:orange")
    ax3.plot(wd.index, wd["wind_gusts_10m_max"], label="Böen max [km/h]", color="tab:red")
    ax3.axvline(today, color="red", linestyle="--", linewidth=2, label="Heute")

    # horizontale Referenzlinien
    ax3.axhline(strong_wind_th, color="gray", linestyle="--", linewidth=1)
    ax3.axhline(storm_th,       color="gray", linestyle="--", linewidth=1)
    ax3.axhline(max_fill,       color="gray", linestyle=":",  linewidth=1)

    # Bereich 39–50 km/h: starker Wind
    ax3.fill_between(
        wd.index,
        strong_wind_th,
        wd["wind_gusts_10m_max"].clip(upper=storm_th),
        where=wd["wind_gusts_10m_max"] >= strong_wind_th,
        color="gold",
        alpha=0.2,
        label="Starker Wind (≥39 km/h)"
    )

    # Bereich 50–89 km/h: Sturm
    ax3.fill_between(
        wd.index,
        storm_th,
        wd["wind_gusts_10m_max"].clip(upper=max_fill),
        where=wd["wind_gusts_10m_max"] >= storm_th,
        color="red",
        alpha=0.2,
        label="Sturm (≥50 km/h)"
    )

    ax3.set_ylim(0, max(max_fill, wd["wind_gusts_10m_max"].max() * 1.05))
    ax3.set_ylabel("Wind [km/h]")
    ax3.set_title("Wind min/max & Böen\nstarker Wind ab 39 km/h, Sturm ab 50 km/h")
    ax3.grid(True, alpha=0.3)
    ax3.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.25),
        borderaxespad=0.0,
        ncol=2,
        fontsize=8,
        frameon=False
    )

    # Platz für die Legenden unter den Subplots
    fig.subplots_adjust(bottom=0.3)

    # Gesamttitel & Datumsformat
    fig.suptitle(label, fontsize=11)
    fig.autofmt_xdate(rotation=45)
    fig.tight_layout()#rect=[0, 0.08, 1, 0.95])

    plt.show()

if __name__ == "__main__":
    
    PRESET_LOCATIONS = [
    ("Fislisbach", "CH"),
    ("Hamburg", "DE"),
    ("Haugesund", "NO"),
    ("Bodø", "NO"),
    ("Sortland", "NO"),
    ("Harstad", "NO"),
    ("Tromsø", "NO"),
    ("Alta", "NO"),
    ("Trondheim", "NO"),
    ("Måløy", "NO"),]
    main()
