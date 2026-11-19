"""
Modul Profil Kurva Beban Rumah Tangga dan Radiasi Surya (PLTS) 24 Jam
Menyediakan profil kurva harian tipikal berbasis kondisi riil di Indonesia.
"""

import numpy as np
import pandas as pd

# Koefisien Profil Beban Residensial Tipikal Indonesia (Pukul 00:00 - 23:00)
# Nilai ternormalisasi terhadap beban puncak (Peak Load = 1.0 pada jam 19.00 - 20.00)
DEFAULT_LOAD_CURVE_24H = np.array([
    0.38, 0.35, 0.34, 0.35, 0.42, 0.58,  # 00:00 - 05:00 (Dini hari - Subuh)
    0.65, 0.62, 0.52, 0.48, 0.46, 0.50,  # 06:00 - 11:00 (Pagi aktivitas)
    0.55, 0.53, 0.50, 0.54, 0.62, 0.78,  # 12:00 - 17:00 (Siang - Sore)
    0.95, 1.00, 0.96, 0.82, 0.65, 0.48   # 18:00 - 23:00 (Beban Puncak Malam)
])

# Koefisien Radiasi Matahari Harian (Clear Sky Bell Curve)
DEFAULT_SOLAR_CURVE_24H = np.array([
    0.00, 0.00, 0.00, 0.00, 0.00, 0.00,  # 00:00 - 05:00 (Malam)
    0.05, 0.22, 0.48, 0.72, 0.88, 0.98,  # 06:00 - 11:00 (Matahari terbit - Puncak)
    1.00, 0.95, 0.82, 0.60, 0.35, 0.10,  # 12:00 - 17:00 (Puncak siang - Menjelang sore)
    0.00, 0.00, 0.00, 0.00, 0.00, 0.00   # 18:00 - 23:00 (Matahari terbenam)
])

WEATHER_FACTORS = {
    "Cerah Maksimal": 1.00,
    "Cerah Berawan": 0.80,
    "Berawan Tebal": 0.50,
    "Hujan / Mendung": 0.20
}


def generate_load_profile(
    num_buses: int = 10,
    base_load_kw: float = 1.5,
    random_noise: bool = True,
    noise_level: float = 0.05,
    seed: int = 42,
    bus_names: list = None
) -> pd.DataFrame:
    """
    Menghasilkan DataFrame beban 24 jam untuk setiap bus (mendukung linear maupun kustom).
    
    Returns:
        pd.DataFrame dengan indeks jam (0-23) dan kolom untuk setiap bus
    """
    if random_noise:
        np.random.seed(seed)
    
    hours = list(range(24))
    data = {}
    
    if bus_names is None:
        target_buses = [f"Tiang_{i}" for i in range(1, num_buses + 1)]
    else:
        target_buses = list(bus_names)
        
    for idx, b_name in enumerate(target_buses, 1):
        curve = DEFAULT_LOAD_CURVE_24H * base_load_kw
        if random_noise:
            noise = np.random.normal(0, noise_level * base_load_kw, size=24)
            curve = np.clip(curve + noise, a_min=0.1 * base_load_kw, a_max=1.3 * base_load_kw)
        data[b_name] = curve
        data[f"Bus_{idx}"] = curve  # Dukungan backwards compatibility
        
    df = pd.DataFrame(data, index=hours)
    df.index.name = "Jam"
    return df


def generate_solar_profile(
    weather_condition: str = "Cerah Maksimal",
    pv_capacity_kw: float = 2.0,
    custom_factor: float = None
) -> pd.Series:
    """
    Menghasilkan Series profil daya aktif (kW) PLTS atap selama 24 jam.
    
    Returns:
        pd.Series dengan indeks jam (0-23)
    """
    if custom_factor is not None:
        factor = float(custom_factor)
    else:
        factor = WEATHER_FACTORS.get(weather_condition, 1.0)
    solar_kw = DEFAULT_SOLAR_CURVE_24H * pv_capacity_kw * factor
    return pd.Series(solar_kw, index=range(24), name="Daya_PV_kW")


BMKG_CITIES = {
    "Jakarta Pusat": "31.71.01.1001",
    "Surabaya": "35.78.08.1001",
    "Bandung": "32.73.01.1001",
    "Semarang": "33.74.06.1001",
    "Yogyakarta": "34.71.04.1001",
    "Denpasar": "51.71.01.1001",
    "Medan": "12.71.01.1001",
    "Makassar": "73.71.04.1001"
}


def fetch_bmkg_weather(city_name="Jakarta Pusat"):
    """
    Mengambil data cuaca real-time dari REST API resmi BMKG (api.bmkg.go.id).
    Mendukung graceful fallback ke mode offline jika koneksi internet terputus.
    """
    import urllib.request
    import json
    import ssl

    code = BMKG_CITIES.get(city_name, "31.71.01.1001")
    url = f"https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4={code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        "Referer": "https://www.bmkg.go.id/"
    }
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            cuaca_list = data.get("data", [{}])[0].get("cuaca", [[]])[0]
            now = cuaca_list[0] if cuaca_list else {}
            
            w_code = now.get("weather", 1)
            w_desc = now.get("weather_desc", "Cerah Berawan")
            temp_c = now.get("t", 28)
            tcc_pct = now.get("tcc", 50)
            hu_pct = now.get("hu", 75)
            
            # Faktor radiasi matahari berbasis kode & tcc
            if w_code == 0 or tcc_pct < 20:
                rad_factor = 1.00
            elif w_code in [1, 2] or tcc_pct < 50:
                rad_factor = 0.85
            elif w_code in [3, 4] or tcc_pct < 80:
                rad_factor = 0.55
            else: # Hujan / Petir
                rad_factor = 0.20
                
            # Efek suhu sel (derating jika suhu > 25°C)
            temp_derating = max(0.85, 1.0 - (temp_c - 25) * 0.004) if temp_c > 25 else 1.0
            effective_factor = round(rad_factor * temp_derating, 3)
            
            # Ambil beberapa slot prakiraan ke depan
            forecast_slots = []
            for item in cuaca_list[:6]:
                dt = item.get("local_datetime", "")
                t_str = dt.split(" ")[-1][:5] if " " in dt else "--:--"
                forecast_slots.append({
                    "time": t_str,
                    "datetime": dt,
                    "weather_desc": item.get("weather_desc", "Cerah Berawan"),
                    "temp_c": item.get("t", 28),
                    "tcc_pct": item.get("tcc", 50),
                    "hu_pct": item.get("hu", 75),
                    "icon_url": item.get("image", "")
                })

            return {
                "status": "success",
                "city": city_name,
                "code": code,
                "weather_desc": w_desc,
                "weather_code": w_code,
                "temp_c": temp_c,
                "tcc_pct": tcc_pct,
                "hu_pct": hu_pct,
                "rad_factor": rad_factor,
                "effective_solar_factor": effective_factor,
                "forecast_slots": forecast_slots,
                "source": "BMKG Open Data API"
            }
    except Exception as e:
        return {
            "status": "fallback",
            "city": city_name,
            "weather_desc": "Cerah Berawan (Offline Fallback)",
            "weather_code": 1,
            "temp_c": 29,
            "tcc_pct": 40,
            "hu_pct": 75,
            "rad_factor": 0.85,
            "effective_solar_factor": 0.835,
            "forecast_slots": [
                {"time": "06:00", "weather_desc": "Cerah", "temp_c": 25, "tcc_pct": 20},
                {"time": "09:00", "weather_desc": "Cerah Berawan", "temp_c": 29, "tcc_pct": 35},
                {"time": "12:00", "weather_desc": "Cerah", "temp_c": 32, "tcc_pct": 15},
                {"time": "15:00", "weather_desc": "Berawan", "temp_c": 30, "tcc_pct": 60},
                {"time": "18:00", "weather_desc": "Hujan Ringan", "temp_c": 27, "tcc_pct": 80},
                {"time": "21:00", "weather_desc": "Berawan", "temp_c": 26, "tcc_pct": 65}
            ],
            "source": "Standard Fallback (Offline Mode)"
        }
