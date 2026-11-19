# ⚡ VoltSolar-Sim Pro Enterprise: Web App Simulator JTR & PLTS Atap On-Grid

Aplikasi web interaktif Teknologi Rekayasa Elektro berbasis **HTML5, CSS3, JavaScript, dan Python (Flask REST API & Pandapower)** untuk menganalisis pengaruh variasi beban rumah tangga terhadap profil tegangan (*voltage profile*) dan rugi-rugi daya (*power losses*) pada Jaringan Tegangan Rendah (JTR 220V/380V), serta mengevaluasi perbaikan kualitas daya melalui integrasi PLTS atap on-grid sesuai standar **SPLN 1:1995** (-10% s.d. +5%).

---

## 🎯 Fitur Lengkap Aplikasi

1. **Arsitektur Web Modern (HTML5 + Flask REST API)**:
   - Frontend: Antarmuka mandiri berbasis HTML5, CSS3 Glassmorphism, JavaScript ES6, dan visualisasi interaktif **Plotly.js**.
   - Backend: Python Flask REST API yang menghubungkan logika antarmuka dengan engine komputasi sistem tenaga listrik.

2. **Integrasi Data Cuaca Real-Time BMKG**:
   - Terhubung langsung ke **REST API resmi BMKG** (`api.bmkg.go.id`) untuk data cuaca dan tutupan awan (*Cloud Cover*) kota-kota besar di Indonesia (Jakarta, Semarang, Surabaya, Bandung, Yogyakarta, Denpasar, Medan, Makassar).
   - Menghitung faktor derating radiasi surya nyata secara dinamis berdasarkan data meteorologi harian.

3. **Model JTR & Standar SPLN 1:1995**:
   - Saluran distribusi dengan kabel pilin standar PLN (*LVTC 3x70+1x50, 3x50+1x35, 3x35+1x25, 3x25+1x25 mm²*).
   - Trafo distribusi 20 kV / 0.4 kV (*Dyn5*, 50 kVA s.d. 400 kVA).
   - Evaluasi ambang batas tegangan operasional PLN: **0.90 p.u. (198 V) s.d. 1.05 p.u. (231 V)**.

4. **Topologi Fleksibel & Drag & Drop Canvas**:
   - Pola jaringan linear radial konvensional maupun **percabangan kustom** (misal Tiang 2 dicabang ke jalur lateral).
   - **Kanvas Interaktif Drag & Drop**: Pengguna dapat menggeser letak tiang secara bebas dan menambah tiang cabang baru secara mandiri.
   - Skematik diagram alur daya percabangan 2D (*NetworkX tree graph*).

5. **Visualisasi Interaktif Mutakhir (Plotly.js)**:
   - **Grafik Animasi Profil Tegangan 24 Jam**: Grafik bergerak otomatis dengan tombol *Play/Pause* dan *timeline slider*.
   - **Visualisasi Permukaan 3D**: Permukaan tegangan dinamis (Sumbu X: Jam, Sumbu Y: Jarak/Tiang, Sumbu Z: Tegangan).
   - Profil arus saluran, pembebanan trafo, dan rugi daya tembaga.

6. **Fitur Cerdas Jaringan Modern (Smart Grid)**:
   - **Kalkulator Hosting Capacity**: Perhitungan otomatis kapasitas penetrasi PLTS atap maksimum sebelum terjadi *overvoltage* (> 1.05 p.u.) atau beban lebih pada trafo.
   - **BESS (Battery Energy Storage System)**: Simulasi baterai per rumah untuk *peak shaving* dan penyerapan kelebihan surya siang hari.
   - **Smart Inverter Volt-VAr Control (IEEE 1547-2018)**: Injeksi/absorpsi daya reaktif otomatis untuk stabilisasi tegangan lokal.
   - **Ketidakseimbangan Beban 3-Fasa**: Analisis asimetri fasa R-S-T dan perhitungan arus netral ($I_N$).

7. **Analisis Tekno-Ekonomi & Mitigasi Emisi**:
   - Perhitungan penghematan tagihan listrik per tahun (Rp), NPV 25 tahun, Payback Period, dan LCOE.
   - Kuantifikasi pengurangan emisi karbon ($CO_2$ mitigation dalam ton/tahun).

8. **Ekspor Laporan Akademik Otomatis**:
   - **Microsoft Word (.docx)**: Laporan formal lengkap berstruktur standar praktikum/skripsi.
   - **Microsoft Excel (.xlsx)**: File multi-sheet berisi Ringkasan KPI, Data Aliran Daya 24 Jam Base, Data dengan PLTS, dan Tekno-Ekonomi.

---

## 🚀 Cara Menjalankan Aplikasi

### Opsi 1: Klik Dua Kali File Batch (Paling Mudah)
Cukup klik ganda file:
```
run_app.bat
```
*(Skrip akan otomatis membuka virtual environment dan meluncurkan aplikasi web HTML5 di browser).*

### Opsi 2: Lewat Terminal PowerShell / CMD
```powershell
.\.venv\Scripts\python.exe server.py
```
Aplikasi web akan otomatis terbuka pada alamat: `http://localhost:5000`.

---

## 📁 Struktur File Repositori

```
Projek/
│
├── core/
│   ├── __init__.py
│   ├── grid_model.py          # Pemodelan JTR, trafo, kabel, beban, PLTS, & percabangan (pandapower)
│   ├── profiles.py            # Generator profil beban 24 jam & API Cuaca BMKG
│   └── simulation.py          # Engine Newton-Raphson, Hosting Capacity, BESS, Volt-VAr, & Ekspor Laporan
│
├── templates/
│   └── index.html             # Antarmuka Web Dashboard Utama (HTML5, CSS3, JavaScript, Plotly.js)
│
├── server.py                  # Backend Web Server (Flask REST API & Controller)
├── run_app.bat                # Skrip peluncur otomatis sekali klik ke Web App HTML5 (Port 5000)
├── requirements.txt           # Daftar dependensi library Python
├── .gitignore                 # Konfigurasi file yang diabaikan Git (.venv, cache, dll)
└── README.md                  # Dokumentasi lengkap proyek
```

---

## 📦 Pustaka / Dependensi Utama
- `pandapower`: Analisis aliran daya sistem tenaga listrik (Newton-Raphson)
- `flask`: Framework backend REST API & server web
- `plotly`: Visualisasi grafik ilmiah 2D & 3D
- `networkx`: Analisis graf dan topologi percabangan pohon
- `pandas` & `numpy`: Manipulasi data time-series dan komputasi matriks
- `python-docx` & `openpyxl`: Pembuat dokumen laporan Word dan spreadsheet Excel otomatis

---

## 👨‍💻 Kriteria Penilaian Praktikum
- **Kompleksitas (30%)**: Integrasi pemodelan aliran daya non-linear, percabangan topologi bebas, BESS, Smart Inverter, dan Hosting Capacity.
- **Keterselesaian (30%)**: Berjalan mulus tanpa error, UI modern responsif, ekspor laporan Word & Excel.
- **Keterkaitan Teknologi Rekayasa Elektro (20%)**: Relevansi ketat terhadap regulasi PLN (SPLN 1:1995), rugi teknis $I^2 R$, dan integrasi PLTS atap.
- **Presentasi & Laporan (20%)**: Visualisasi interaktif (2D/3D/Animasi) dan kemudahan penggunaan aplikasi.
