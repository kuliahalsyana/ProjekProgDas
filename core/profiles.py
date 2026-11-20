"""
=============================================================================================
VoltSolar-Sim Pro Enterprise - Modul Profil Kurva Beban & Radiasi Surya 24 Jam
Program Studi: Teknologi Rekayasa Elektro | Praktikum Pemrograman Dasar
=============================================================================================
Fungsi Utama Modul:
1. Menyediakan profil kurva beban residensial 24 jam berbasis pola konsumsi listrik Indonesia.
2. Memodelkan kurva radiasi penyinaran matahari harian (Clear Sky Bell Curve).
3. Mengintegrasikan data cuaca real-time langsung dari REST API resmi BMKG (api.bmkg.go.id).
4. Menghitung pengaruh tutupan awan (Total Cloud Cover) & efek suhu terhadap efisiensi panel surya.
=============================================================================================
"""

import numpy as np   # Digunakan untuk operasi array matematika dan bilangan acak Gaussian
import pandas as pd  # Digunakan untuk struktur data tabel/DataFrame time-series 24 jam


# =============================================================================================
# 1. KOEFISIEN KURVA BEBAN RESIDENSIAL 24 JAM TIPIKAL INDONESIA (SPLN / Standar Beban Rumah)
# Nilai dinormalisasi terhadap beban puncak (Peak Load = 1.0 pada jam 19.00 malam)
# =============================================================================================
DEFAULT_LOAD_CURVE_24H = np.array([
    0.38, 0.35, 0.34, 0.35, 0.42, 0.58,  # Pukul 00:00 - 05:00 WIB (Dini hari tidur, konsumsi rendah)
    0.65, 0.62, 0.52, 0.48, 0.46, 0.50,  # Pukul 06:00 - 11:00 WIB (Pagi hari aktivitas, pompa air, memasak)
    0.55, 0.53, 0.50, 0.54, 0.62, 0.78,  # Pukul 12:00 - 17:00 WIB (Siang - sore hari, AC dan elektronik)
    0.95, 1.00, 0.96, 0.82, 0.65, 0.48   # Pukul 18:00 - 23:00 WIB (Beban Puncak Malam: lampu, TV, pendingin)
])


# =============================================================================================
# 2. KOEFISIEN RADIASI MATAHARI 24 JAM (Clear Sky Bell Curve / Kurva Lonceng Langit Cerah)
# Berdasarkan posisi lintang khatulistiwa Indonesia (-6° s.d. -7° LS)
# =============================================================================================
DEFAULT_SOLAR_CURVE_24H = np.array([
    0.00, 0.00, 0.00, 0.00, 0.00, 0.00,  # Pukul 00:00 - 05:00 WIB (Malam / gelap gulita, daya surya = 0)
    0.05, 0.22, 0.48, 0.72, 0.88, 0.98,  # Pukul 06:00 - 11:00 WIB (Matahari terbit, radiasi naik tajam)
    1.00, 0.95, 0.82, 0.60, 0.35, 0.10,  # Pukul 12:00 - 17:00 WIB (Puncak siang pukul 12.00, lalu meredup)
    0.00, 0.00, 0.00, 0.00, 0.00, 0.00   # Pukul 18:00 - 23:00 WIB (Matahari terbenam, daya surya = 0)
])


# =============================================================================================
# 3. FAKTOR PENGURANG INTENSITAS CAHAYA BERDASARKAN KONDISI CUACA PRESET
# =============================================================================================
WEATHER_FACTORS = {
    "Cerah Maksimal": 1.00,   # Langit biru tanpa awan, iradiansi penuh 1000 W/m²
    "Cerah Berawan": 0.80,    # Awan tipis parsial, produksi surya ~80%
    "Berawan Tebal": 0.50,    # Cahaya baur (diffuse radiation), produksi surya ~50%
    "Hujan / Mendung": 0.20   # Langit gelap hujan deras, produksi surya sisa ~20%
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
    Menghasilkan tabel (DataFrame) profil konsumsi listrik 24 jam untuk seluruh tiang konsumen.
    
    Fitur:
    - Menghitung kurva deterministik (perkalian koefisien waktu dengan beban dasar kW).
    - Menambahkan variasi stokastik acak Gaussian (Random Noise) agar realistis seperti data PLN riil.
    """
    # Kunci seed generator bilangan acak agar hasil simulasi konsisten dan dapat direproduksi
    if random_noise:
        np.random.seed(seed)
    
    hours = list(range(24))  # Rentang jam 0 sampai 23 (24 jam)
    data = {}                # Kamus penyimpanan data kolom tiap tiang
    
    # Tentukan daftar nama tiang/bus yang akan dibuat profil bebannya
    if bus_names is None:
        target_buses = [f"Tiang_{i}" for i in range(1, num_buses + 1)]
    else:
        target_buses = list(bus_names)
        
    for idx, b_name in enumerate(target_buses, 1):
        # Hitung kurva dasar tiang bersangkutan
        curve = DEFAULT_LOAD_CURVE_24H * base_load_kw
        
        # Tambahkan variasi fluktuasi acak beban rumah jika opsi stokastik aktif
        if random_noise:
            # Distribusi normal rata-rata 0 dengan standar deviasi sebanding noise_level
            noise = np.random.normal(0, noise_level * base_load_kw, size=24)
            # Batasi agar nilai beban tidak bernilai negatif dan tidak melompat ekstrem
            curve = np.clip(curve + noise, a_min=0.1 * base_load_kw, a_max=1.3 * base_load_kw)
            
        data[b_name] = curve
        data[f"Bus_{idx}"] = curve  # Alias penamaan tambahan untuk kompatibilitas fungsi lama
        
    # Susun menjadi tabel Pandas berindeks jam operasional 0-23
    df = pd.DataFrame(data, index=hours)
    df.index.name = "Jam"
    return df


def generate_solar_profile(
    weather_condition: str = "Cerah Maksimal",
    pv_capacity_kw: float = 2.0,
    custom_factor: float = None
) -> pd.Series:
    """
    Menghitung deret output daya aktif harian (kW) yang dihasilkan oleh inverter PLTS atap.
    
    Rumus:
    P_PV(t) = Koefisien_Surya(t) * Kapasitas_Inverter_kW * Faktor_Cuaca
    """
    # Gunakan faktor cuaca kustom (dari BMKG) atau faktor dari preset pilihan pengguna
    if custom_factor is not None:
        factor = float(custom_factor)
    else:
        factor = WEATHER_FACTORS.get(weather_condition, 1.0)
        
    # Hitung daya listrik surya di tiap jam (kW)
    solar_kw = DEFAULT_SOLAR_CURVE_24H * pv_capacity_kw * factor
    return pd.Series(solar_kw, index=range(24), name="Daya_PV_kW")


# =============================================================================================
# 4. KODE WILAYAH KOTA KONTROL BMKG (Kode ADM4 Wilayah Administrasi Resmi BMKG)
# =============================================================================================
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
    Menghubungi endpoint REST API resmi BMKG secara online untuk mengambil data cuaca riil:
    - Tutupan awan (Total Cloud Cover / TCC dalam %)
    - Suhu udara lingkungan (T dalam °C)
    - Kelembaban udara (HU dalam %)
    - Menghitung koefisien derating suhu modul fotovoltaik (-0.4%/°C di atas 25°C).
    - Memiliki mode fallback otomatis jika koneksi internet sedang terputus (Offline Resilience).
    """
    import urllib.request  # Modul standar Python untuk request HTTP
    import json            # Modul parsing respons format JSON
    import ssl             # Modul penanganan sertifikat SSL/TLS

    code = BMKG_CITIES.get(city_name, "31.71.01.1001")
    url = f"https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4={code}"
    
    # Header HTTP agar request diterima dengan baik oleh server BMKG
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
        "Referer": "https://www.bmkg.go.id/"
    }
    
    # Konfigurasi konteks SSL yang toleran terhadap perbedaan sertifikat lokal Windows
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        # Kirim request ke API BMKG dengan batas waktu tunggu (timeout) 4 detik
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            cuaca_list = data.get("data", [{}])[0].get("cuaca", [[]])[0]
            now = cuaca_list[0] if cuaca_list else {}
            
            # Ekstrak data cuaca waktu terkini
            w_code = now.get("weather", 1)                  # Kode kondisi cuaca
            w_desc = now.get("weather_desc", "Cerah Berawan") # Deskripsi teks kondisi cuaca
            temp_c = now.get("t", 28)                       # Suhu udara (°C)
            tcc_pct = now.get("tcc", 50)                     # Persentase tutupan awan (%)
            hu_pct = now.get("hu", 75)                      # Kelembaban udara (%)
            
            # Estimasi faktor radiasi matahari berbasis tutupan awan (TCC)
            if w_code == 0 or tcc_pct < 20:
                rad_factor = 1.00   # Langit bersih tanpa halangan awan
            elif w_code in [1, 2] or tcc_pct < 50:
                rad_factor = 0.85   # Cerah berawan ringan
            elif w_code in [3, 4] or tcc_pct < 80:
                rad_factor = 0.55   # Berawan tebal
            else:
                rad_factor = 0.20   # Hujan / mendung pekat
                
            # Efek suhu sel fotovoltaik (Koefisien termal daya ~ -0.4% per °C di atas standar STC 25°C)
            temp_derating = max(0.85, 1.0 - (temp_c - 25) * 0.004) if temp_c > 25 else 1.0
            # Faktor efektif akhir hasil kombinasi awan dan suhu
            effective_factor = round(rad_factor * temp_derating, 3)
            
            # Ambil deretan prakiraan waktu berikutnya untuk pita ramalan cuaca antarmuka web
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
        # Cadangan otomatis jika internet offline: aplikasi tetap berjalan normal dengan estimasi standar
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
