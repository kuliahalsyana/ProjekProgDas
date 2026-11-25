"""
Modul Basis Data & API Wilayah Indonesia (38 Provinsi, Kabupaten/Kota, dan Kecamatan)
Mendukung Resolusi Kode ADM4 BMKG untuk Prakiraan Cuaca Seluruh Indonesia
Program Studi: Teknologi Rekayasa Elektro / Praktikum Pemrograman Dasar
"""

import os
import json
import urllib.request
import ssl

# Direktori Basis Data Wilayah & Cache BMKG Lokal agar super cepat dan memiliki ketahanan offline
CACHE_DIR = os.path.join(os.path.dirname(__file__), "Data BMKG")
if not os.path.exists(CACHE_DIR):
    alt_cache = os.path.join(os.path.dirname(__file__), "wilayah_cache")
    if os.path.exists(alt_cache):
        CACHE_DIR = alt_cache
os.makedirs(CACHE_DIR, exist_ok=True)

# 1. DAFTAR 38 PROVINSI RESMI REPUBLIK INDONESIA
PROVINCES_LIST = [
    {"id": "11", "name": "Aceh"},
    {"id": "12", "name": "Sumatera Utara"},
    {"id": "13", "name": "Sumatera Barat"},
    {"id": "14", "name": "Riau"},
    {"id": "15", "name": "Jambi"},
    {"id": "16", "name": "Sumatera Selatan"},
    {"id": "17", "name": "Bengkulu"},
    {"id": "18", "name": "Lampung"},
    {"id": "19", "name": "Kepulauan Bangka Belitung"},
    {"id": "21", "name": "Kepulauan Riau"},
    {"id": "31", "name": "DKI Jakarta"},
    {"id": "32", "name": "Jawa Barat"},
    {"id": "33", "name": "Jawa Tengah"},
    {"id": "34", "name": "D.I. Yogyakarta"},
    {"id": "35", "name": "Jawa Timur"},
    {"id": "36", "name": "Banten"},
    {"id": "51", "name": "Bali"},
    {"id": "52", "name": "Nusa Tenggara Barat"},
    {"id": "53", "name": "Nusa Tenggara Timur"},
    {"id": "61", "name": "Kalimantan Barat"},
    {"id": "62", "name": "Kalimantan Tengah"},
    {"id": "63", "name": "Kalimantan Selatan"},
    {"id": "64", "name": "Kalimantan Timur"},
    {"id": "65", "name": "Kalimantan Utara"},
    {"id": "71", "name": "Sulawesi Utara"},
    {"id": "72", "name": "Sulawesi Tengah"},
    {"id": "73", "name": "Sulawesi Selatan"},
    {"id": "74", "name": "Sulawesi Tenggara"},
    {"id": "75", "name": "Gorontalo"},
    {"id": "76", "name": "Sulawesi Barat"},
    {"id": "81", "name": "Maluku"},
    {"id": "82", "name": "Maluku Utara"},
    {"id": "91", "name": "Papua"},
    {"id": "92", "name": "Papua Barat"},
    {"id": "93", "name": "Papua Selatan"},
    {"id": "94", "name": "Papua Tengah"},
    {"id": "95", "name": "Papua Pegunungan"},
    {"id": "96", "name": "Papua Barat Daya"}
]

# Cache in-memory
_MEM_CACHE = {
    "provinces": PROVINCES_LIST,
    "regencies": {},
    "districts": {},
    "adm4_resolved": {}
}


def _fetch_url_json(url, timeout=5):
    """Helper untuk mengambil JSON dari URL dengan SSL bypass dan User-Agent."""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            return data
    except Exception:
        return None


def get_provinces():
    """Mengembalikan daftar 38 provinsi di Indonesia."""
    return PROVINCES_LIST


def get_regencies(prov_id: str):
    """Mengambil daftar Kabupaten/Kota berdasarkan kode ID Provinsi (2 digit)."""
    prov_id = str(prov_id).strip()
    if prov_id in _MEM_CACHE["regencies"]:
        return _MEM_CACHE["regencies"][prov_id]

    cache_file = os.path.join(CACHE_DIR, f"reg_{prov_id}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                regs = json.load(f)
                _MEM_CACHE["regencies"][prov_id] = regs
                return regs
        except Exception:
            pass

    # Ambil dari open data CDN
    url = f"https://www.emsifa.com/api-wilayah-indonesia/v2/regencies/{prov_id}.json"
    regs = _fetch_url_json(url)
    if regs and isinstance(regs, list):
        cleaned = [{"id": r.get("id"), "name": r.get("name")} for r in regs if "id" in r]
        _MEM_CACHE["regencies"][prov_id] = cleaned
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cleaned, f)
        except Exception:
            pass
        return cleaned

    # Fallback jika offline
    fallback_regs = _get_offline_regencies(prov_id)
    _MEM_CACHE["regencies"][prov_id] = fallback_regs
    return fallback_regs


def get_districts(reg_id: str):
    """Mengambil daftar Kecamatan berdasarkan kode ID Kabupaten/Kota (4 digit)."""
    reg_id = str(reg_id).strip()
    # Normalisasi format ID (misal '3374' -> '33.74')
    if "." not in reg_id and len(reg_id) >= 4:
        reg_id_dot = f"{reg_id[:2]}.{reg_id[2:4]}"
    else:
        reg_id_dot = reg_id

    cache_key = reg_id_dot.replace(".", "_")
    if cache_key in _MEM_CACHE["districts"]:
        return _MEM_CACHE["districts"][cache_key]

    cache_file = os.path.join(CACHE_DIR, f"dist_{cache_key}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                dists = json.load(f)
                _MEM_CACHE["districts"][cache_key] = dists
                return dists
        except Exception:
            pass

    url = f"https://www.emsifa.com/api-wilayah-indonesia/v2/districts/{reg_id_dot}.json"
    dists = _fetch_url_json(url)
    if dists and isinstance(dists, list):
        cleaned = [{"id": d.get("id"), "name": d.get("name"), "lat": d.get("lat"), "lon": d.get("lng")} for d in dists if "id" in d]
        _MEM_CACHE["districts"][cache_key] = cleaned
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cleaned, f)
        except Exception:
            pass
        return cleaned

    fallback_dists = _get_offline_districts(reg_id_dot)
    _MEM_CACHE["districts"][cache_key] = fallback_dists
    return fallback_dists


def resolve_district_adm4(adm3_code: str):
    """
    Menemukan kode ADM4 BMKG yang valid untuk sebuah Kecamatan (ADM3).
    Mencoba kandidat kelurahan/desa (.1001, .2001, .1002, .2002) dengan caching instan.
    """
    adm3 = str(adm3_code).strip()
    # Jika sudah merupakan kode ADM4 (10 digit bertitik, e.g. 33.74.06.1001)
    if len(adm3.split(".")) == 4:
        return adm3

    if adm3 in _MEM_CACHE["adm4_resolved"]:
        return _MEM_CACHE["adm4_resolved"][adm3]

    cache_file = os.path.join(CACHE_DIR, "resolved_adm4.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if adm3 in saved:
                    _MEM_CACHE["adm4_resolved"][adm3] = saved[adm3]
                    return saved[adm3]
        except Exception:
            pass

    candidates = [
        f"{adm3}.1001",
        f"{adm3}.2001",
        f"{adm3}.1002",
        f"{adm3}.2002"
    ]

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.bmkg.go.id/"
    }

    resolved_code = None
    for cand in candidates:
        url = f"https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4={cand}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=2.5) as r:
                if r.status == 200:
                    resolved_code = cand
                    break
        except Exception:
            continue

    if not resolved_code:
        # Default fallback ke 1001
        resolved_code = f"{adm3}.1001"

    _MEM_CACHE["adm4_resolved"][adm3] = resolved_code
    # Simpan ke cache disk
    try:
        saved_dict = {}
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                saved_dict = json.load(f)
        saved_dict[adm3] = resolved_code
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(saved_dict, f)
    except Exception:
        pass

    return resolved_code


# =====================================================================================
# BASIS DATA CADANGAN OFFLINE (OFFLINE RESILIENCE) UNTUK WILAYAH POPULER INDONESIA
# =====================================================================================
def _get_offline_regencies(prov_id: str):
    data = {
        "31": [
            {"id": "31.71", "name": "Kota Adm. Jakarta Pusat"},
            {"id": "31.72", "name": "Kota Adm. Jakarta Utara"},
            {"id": "31.73", "name": "Kota Adm. Jakarta Barat"},
            {"id": "31.74", "name": "Kota Adm. Jakarta Selatan"},
            {"id": "31.75", "name": "Kota Adm. Jakarta Timur"},
            {"id": "31.01", "name": "Kab. Adm. Kepulauan Seribu"}
        ],
        "32": [
            {"id": "32.73", "name": "Kota Bandung"},
            {"id": "32.71", "name": "Kota Bogor"},
            {"id": "32.75", "name": "Kota Bekasi"},
            {"id": "32.76", "name": "Kota Depok"},
            {"id": "32.74", "name": "Kota Cirebon"},
            {"id": "32.04", "name": "Kabupaten Bandung"},
            {"id": "32.01", "name": "Kabupaten Bogor"},
            {"id": "32.17", "name": "Kabupaten Bandung Barat"}
        ],
        "33": [
            {"id": "33.74", "name": "Kota Semarang"},
            {"id": "33.72", "name": "Kota Surakarta (Solo)"},
            {"id": "33.73", "name": "Kota Salatiga"},
            {"id": "33.76", "name": "Kota Tegal"},
            {"id": "33.75", "name": "Kota Pekalongan"},
            {"id": "33.71", "name": "Kota Magelang"},
            {"id": "33.22", "name": "Kabupaten Semarang"},
            {"id": "33.02", "name": "Kabupaten Banyumas (Purwokerto)"},
            {"id": "33.19", "name": "Kabupaten Kudus"},
            {"id": "33.20", "name": "Kabupaten Jepara"},
            {"id": "33.24", "name": "Kabupaten Kendal"},
            {"id": "33.10", "name": "Kabupaten Klaten"},
            {"id": "33.08", "name": "Kabupaten Magelang"},
            {"id": "33.11", "name": "Kabupaten Sukoharjo"},
            {"id": "33.13", "name": "Kabupaten Karanganyar"}
        ],
        "34": [
            {"id": "34.71", "name": "Kota Yogyakarta"},
            {"id": "34.04", "name": "Kabupaten Sleman"},
            {"id": "34.02", "name": "Kabupaten Bantul"},
            {"id": "34.01", "name": "Kabupaten Kulon Progo"},
            {"id": "34.03", "name": "Kabupaten Gunungkidul"}
        ],
        "35": [
            {"id": "35.78", "name": "Kota Surabaya"},
            {"id": "35.73", "name": "Kota Malang"},
            {"id": "35.79", "name": "Kota Batu"},
            {"id": "35.15", "name": "Kabupaten Sidoarjo"},
            {"id": "35.07", "name": "Kabupaten Malang"},
            {"id": "35.10", "name": "Kabupaten Banyuwangi"},
            {"id": "35.09", "name": "Kabupaten Jember"},
            {"id": "35.25", "name": "Kabupaten Gresik"}
        ],
        "36": [
            {"id": "36.71", "name": "Kota Tangerang"},
            {"id": "36.74", "name": "Kota Tangerang Selatan"},
            {"id": "36.73", "name": "Kota Serang"},
            {"id": "36.72", "name": "Kota Cilegon"},
            {"id": "36.03", "name": "Kabupaten Tangerang"}
        ],
        "51": [
            {"id": "51.71", "name": "Kota Denpasar"},
            {"id": "51.03", "name": "Kabupaten Badung (Kuta)"},
            {"id": "51.04", "name": "Kabupaten Gianyar (Ubud)"},
            {"id": "51.02", "name": "Kabupaten Tabanan"},
            {"id": "51.08", "name": "Kabupaten Buleleng (Singaraja)"}
        ],
        "12": [
            {"id": "12.71", "name": "Kota Medan"},
            {"id": "12.72", "name": "Kota Pematangsiantar"},
            {"id": "12.07", "name": "Kabupaten Deli Serdang"}
        ],
        "73": [
            {"id": "73.71", "name": "Kota Makassar"},
            {"id": "73.06", "name": "Kabupaten Gowa"},
            {"id": "73.07", "name": "Kabupaten Sinjai"}
        ],
        "64": [
            {"id": "64.71", "name": "Kota Balikpapan"},
            {"id": "64.72", "name": "Kota Samarinda"},
            {"id": "64.02", "name": "Kabupaten Kutai Kartanegara"}
        ],
        "91": [
            {"id": "91.71", "name": "Kota Jayapura"},
            {"id": "91.01", "name": "Kabupaten Jayapura"}
        ]
    }
    return data.get(prov_id, [{"id": f"{prov_id}.01", "name": f"Pusat Pemerintahan Wilayah {prov_id}"}])


def _get_offline_districts(reg_id: str):
    data = {
        "33.74": [  # Kota Semarang
            {"id": "33.74.01", "name": "Semarang Tengah"},
            {"id": "33.74.02", "name": "Semarang Utara"},
            {"id": "33.74.03", "name": "Semarang Timur"},
            {"id": "33.74.04", "name": "Gayamsari"},
            {"id": "33.74.05", "name": "Genuk"},
            {"id": "33.74.06", "name": "Pedurungan"},
            {"id": "33.74.07", "name": "Semarang Selatan"},
            {"id": "33.74.08", "name": "Candisari"},
            {"id": "33.74.09", "name": "Gajahmungkur"},
            {"id": "33.74.10", "name": "Tembalang"},
            {"id": "33.74.11", "name": "Banyumanik"},
            {"id": "33.74.12", "name": "Gunungpati"},
            {"id": "33.74.13", "name": "Semarang Barat"},
            {"id": "33.74.14", "name": "Mijen"},
            {"id": "33.74.15", "name": "Ngaliyan"},
            {"id": "33.74.16", "name": "Tugu"}
        ],
        "34.04": [  # Kabupaten Sleman
            {"id": "34.04.01", "name": "Gamping"},
            {"id": "34.04.02", "name": "Godean"},
            {"id": "34.04.03", "name": "Moyudan"},
            {"id": "34.04.04", "name": "Minggir"},
            {"id": "34.04.05", "name": "Seyegan"},
            {"id": "34.04.06", "name": "Mlati"},
            {"id": "34.04.07", "name": "Depok"},
            {"id": "34.04.08", "name": "Berbah"},
            {"id": "34.04.09", "name": "Prambanan"},
            {"id": "34.04.10", "name": "Kalasan"},
            {"id": "34.04.11", "name": "Ngemplak"},
            {"id": "34.04.12", "name": "Ngaglik"},
            {"id": "34.04.13", "name": "Sleman"},
            {"id": "34.04.14", "name": "Tempel"},
            {"id": "34.04.15", "name": "Turi"},
            {"id": "34.04.16", "name": "Pakem"},
            {"id": "34.04.17", "name": "Cangkringan"}
        ],
        "34.71": [  # Kota Yogyakarta
            {"id": "34.71.01", "name": "Tegalrejo"},
            {"id": "34.71.02", "name": "Jetis"},
            {"id": "34.71.03", "name": "Gondokusuman"},
            {"id": "34.71.04", "name": "Danurejan"},
            {"id": "34.71.05", "name": "Gedongtengen"},
            {"id": "34.71.06", "name": "Ngampilan"},
            {"id": "34.71.07", "name": "Wirobrajan"},
            {"id": "34.71.08", "name": "Mantrijeron"},
            {"id": "34.71.09", "name": "Kraton"},
            {"id": "34.71.10", "name": "Gondomanan"},
            {"id": "34.71.11", "name": "Pakualaman"},
            {"id": "34.71.12", "name": "Mergangsan"},
            {"id": "34.71.13", "name": "Umbulharjo"},
            {"id": "34.71.14", "name": "Kotagede"}
        ],
        "31.71": [  # Jakarta Pusat
            {"id": "31.71.01", "name": "Gambir"},
            {"id": "31.71.02", "name": "Sawah Besar"},
            {"id": "31.71.03", "name": "Kemayoran"},
            {"id": "31.71.04", "name": "Senen"},
            {"id": "31.71.05", "name": "Cempaka Putih"},
            {"id": "31.71.06", "name": "Menteng"},
            {"id": "31.71.07", "name": "Tanah Abang"},
            {"id": "31.71.08", "name": "Johar Baru"}
        ],
        "35.78": [  # Kota Surabaya
            {"id": "35.78.01", "name": "Karang Pilang"},
            {"id": "35.78.02", "name": "Wonocolo"},
            {"id": "35.78.03", "name": "Rungkut"},
            {"id": "35.78.04", "name": "Wonokromo"},
            {"id": "35.78.05", "name": "Tegalsari"},
            {"id": "35.78.06", "name": "Sawahan"},
            {"id": "35.78.07", "name": "Genteng"},
            {"id": "35.78.08", "name": "Gubeng"},
            {"id": "35.78.09", "name": "Sukolilo"},
            {"id": "35.78.10", "name": "Tambaksari"}
        ],
        "32.73": [  # Kota Bandung
            {"id": "32.73.01", "name": "Sukasari"},
            {"id": "32.73.02", "name": "Coblong"},
            {"id": "32.73.03", "name": "Babakan Ciparay"},
            {"id": "32.73.04", "name": "Bojongloa Kaler"},
            {"id": "32.73.05", "name": "Andir"},
            {"id": "32.73.06", "name": "Cicendo"},
            {"id": "32.73.07", "name": "Sumur Bandung"},
            {"id": "32.73.08", "name": "Cibeunying Kaler"}
        ],
        "51.03": [  # Badung Bali
            {"id": "51.03.01", "name": "Kuta"},
            {"id": "51.03.02", "name": "Mengwi"},
            {"id": "51.03.03", "name": "Abiansemal"},
            {"id": "51.03.04", "name": "Petang"},
            {"id": "51.03.05", "name": "Kuta Selatan (Nusa Dua)"},
            {"id": "51.03.06", "name": "Kuta Utara (Canggu)"}
        ]
    }
    return data.get(reg_id, [{"id": f"{reg_id}.01", "name": "Kecamatan Pusat / Utama"}])
