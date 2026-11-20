# 📖 PANDUAN LENGKAP PENJELASAN KODE BARIS DEMI BARIS
## Proyek: VoltSolar-Sim Pro Enterprise v2.5
### Program Studi: Teknologi Rekayasa Elektro | Praktikum Pemrograman Dasar

Dokumen ini disusun sebagai **panduan belajar intensif & lembar contekan (*cheat sheet*) sidang/ujian praktikum** untuk menjelaskan logika, rumus matematika, dan alur setiap baris kode dari seluruh file proyek.

---

## DAFTAR ISI FILE PROYEK
1. [core/grid_model.py](#1-coregrid_modelpy--pemodelan-jaringan-distribusi-jtr) – Pemodelan JTR, Gardu Trafo & Kabel LVTC
2. [core/profiles.py](#2-coreprofilespy--profil-beban-radiasi-surya--api-bmkg) – Kurva Beban, Radiasi Surya & Integrasi BMKG
3. [core/simulation.py](#3-coresimulationpy--komputasi-aliran-daya-newton-raphson--analisis) – Solver Newton-Raphson, BESS, IEEE 1547, Finansial & Ekspor
4. [server.py](#4-serverpy--backend-flask-rest-api) – REST API Server, Routing & Serialisasi Data
5. [run_app.bat](#5-run_appbat--otomatisasi-instalasi--peluncur-aplikasi) – Script Batch Pendeteksi Python & Auto-Setup
6. [templates/index.html](#6-templatesindexhtml--frontend-html5-css3-glassmorphism--plotlyjs) – Antarmuka Web, Visualisasi & Sinkronisasi

---

## 1. `core/grid_model.py` – Pemodelan Jaringan Distribusi JTR

File ini bertugas mengonstruksi topologi jaringan listrik tegangan rendah menggunakan library **pandapower**.

### Rincian Baris & Penjelasan Logika:
* **Baris 1–8:** *Docstring modul*, menjelaskan fungsi pemodelan trafo penurun tegangan, kabel LVTC, titik beban konsumen, dan generator PLTS.
* **Baris 10:** `import pandapower as pp` – Memanggil pustaka standar internasional untuk analisis sistem tenaga listrik (berbasis solver Newton-Raphson).
* **Baris 11:** `import numpy as np` – Memanggil pustaka numerik untuk perhitungan matriks dan trigonometri daya ($P, Q, S$).
* **Baris 15–40 (`CABLE_TYPES`):** Database kawat konduktor pilin udara (*Low Voltage Twisted Cable* / LVTC) standar PLN:
  * `r_ohm_per_km`: Resistansi kawat per km ($\Omega/\text{km}$), menentukan rugi-rugi panas ($I^2 R$) dan jatuh tegangan resistif.
  * `x_ohm_per_km`: Reaktansi induktif per km ($\Omega/\text{km}$), menentukan rugi reaktif induktansi kabel pilin.
  * `max_i_ka`: Kuat Hantar Arus (KHA) maksimum dalam kilo-Ampere (kA), misalnya 0.190 kA = 190 A untuk ukuran $3 \times 70 + 1 \times 50\text{ mm}^2$.
  * `c_nf_per_km`: Kapasitansi ke tanah (0 untuk saluran tegangan rendah pendek).
* **Baris 43–50 (`TRANSFORMER_TYPES`):** Spesifikasi trafo step-down $20\text{ kV} / 0.4\text{ kV}$ (50 kVA hingga 400 kVA):
  * `sn_mva`: Daya semu pengenal trafo dalam satuan Mega-Volt-Ampere ($100\text{ kVA} = 0.10\text{ MVA}$).
  * `vn_hv_kv`: Tegangan sisi primer / Tegangan Menengah ($20\text{ kV}$).
  * `vn_lv_kv`: Tegangan sisi sekunder / Tegangan Rendah ($0.4\text{ kV} / 400\text{ V}$ antar fasa, atau $230\text{ V}$ fasa-netral).
  * `vk_percent`: Tegangan hubung singkat ($4\%$), menunjukkan impedansi internal trafo.
  * `vkr_percent`: Komponen resistif hubung singkat ($1.1\%$), menentukan rugi tembaga (*copper losses*).
  * `pfe_kw`: Rugi inti besi (*iron losses / no-load losses*), energi yang terus hilang selama trafo terhubung tegangan.
* **Baris 53–84 (`def create_lv_network(...)`):** Fungsi utama pembuat objek topologi jaringan listrik:
  * Menerima parameter jumlah tiang, panjang bentang kabel, jenis trafo, kabel, daya beban rumah, dan status PLTS.
* **Baris 85:** `net = pp.create_empty_network(...)` – Menyiapkan wadah kosong elemen sistem tenaga.
* **Baris 88–89:** `pp.create_bus(..., vn_kv=20.0)` & `pp.create_ext_grid(...)` – Membuat bus Tegangan Menengah dan mendefinisikannya sebagai *External Grid (Slack Bus)* dengan referensi tegangan $V = 1.0\text{ pu}$ dan sudut fasa $\theta = 0^\circ$.
* **Baris 92:** `pp.create_bus(..., vn_kv=0.4)` – Membuat bus pangkal sisi sekunder gardu trafo.
* **Baris 96–108:** `pp.create_transformer_from_parameters(...)` – Menghubungkan sisi primer dan sekunder trafo dengan parameter impedansi riil.
* **Baris 114–115:** `tan_phi = np.tan(np.arccos(power_factor))` & `base_q_kvar = base_load_per_bus_kw * tan_phi` – Menghitung daya reaktif ($Q$) beban berdasarkan segitiga daya $Q = P \times \tan(\theta)$.
* **Baris 135–190:** Penanganan **Topologi Kustom Bercabang (Tree Network)** jika pengguna mendesain saluran cabang via Drag & Drop Canvas.
* **Baris 191–230:** Penanganan **Topologi Radial Linear Standar** (Trafo $\rightarrow$ Tiang 1 $\rightarrow$ Tiang 2 $\rightarrow$ ... $\rightarrow$ Tiang $N$):
  * `pp.create_line_from_parameters(...)`: Membentangkan kabel antar tiang.
  * `pp.create_load(...)`: Memasang beban rumah tangga pada tiang.
  * `pp.create_sgen(...)`: Memasang unit PLTS atap on-grid sebagai generator statis ($P > 0, Q = 0$).

---

## 2. `core/profiles.py` – Profil Beban, Radiasi Surya & API BMKG

File ini bertanggung jawab menyediakan kurva dinamis 24 jam untuk beban listrik dan sinar matahari, serta integrasi cuaca online.

### Rincian Baris & Penjelasan Logika:
* **Baris 11–16 (`DEFAULT_LOAD_CURVE_24H`):** Array 24 elemen berisi koefisien normalisasi konsumsi listrik rumah tangga Indonesia:
  * Pukul 00.00–05.00: Rendah ($0.34 - 0.42$) karena penghuni rumah tidur.
  * Pukul 06.00–11.00: Mulai naik ($0.46 - 0.65$) aktivitas pagi.
  * Pukul 18.00–21.00: **Beban Puncak Malam (*Peak Load*)** bernilai $0.95 - 1.00$ karena lampu, televisi, pendingin ruangan (AC), dan pompa air menyala bersamaan.
* **Baris 19–24 (`DEFAULT_SOLAR_CURVE_24H`):** Array 24 elemen kurva radiasi matahari (*Clear Sky Bell Curve*):
  * Pukul 00.00–05.00 & 18.00–23.00 bernilai $0.00$ (malam hari tidak ada sinar surya).
  * Pukul 06.00 mulai naik ($0.05$), mencapai puncak $1.00$ pada pukul 12.00 siang, lalu menurun hingga $0.10$ pada pukul 17.00.
* **Baris 26–31 (`WEATHER_FACTORS`):** Koefisien pengali cuaca: Cerah ($1.0$), Cerah Berawan ($0.8$), Berawan Tebal ($0.5$), Hujan ($0.2$).
* **Baris 34–70 (`def generate_load_profile(...)`):**
  * Mengalikan kurva normalisasi dengan daya dasar rumah ($P_{\text{base}}$).
  * Menambahkan variasi acak Gaussian `np.random.normal(...)` agar beban tiap rumah bervariasi secara alami (stokastik) seperti kondisi nyata di lapangan.
* **Baris 72–89 (`def generate_solar_profile(...)`):**
  * Menghitung daya listrik harian PLTS ($kW$): $P_{\text{PV}}(t) = \text{Kurva}(t) \times \text{Kapasitas (kWp)} \times \text{Faktor Cuaca}$.
* **Baris 91–100 (`BMKG_CITIES`):** Kamus kode wilayah administratif (ADM4) untuk 8 kota besar Indonesia pada API BMKG.
* **Baris 103–180 (`def fetch_bmkg_weather(...)`):**
  * Menghubungi REST API BMKG `https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4={kode}`.
  * Mengekstrak parameter cuaca: Deskripsi Cuaca, Suhu Udara ($^\circ\text{C}$), Tutupan Awan (*Total Cloud Cover* / TCC dalam $\%$), dan Kelembaban (HU $\%$).
  * **Kompensasi Suhu Panel (*Temperature Derating*):** Panel surya mengalami penurunan efisiensi sebesar $-0.4\%$ per $^\circ\text{C}$ jika suhu sel berada di atas $25^\circ\text{C}$ (Standard Test Condition / STC). Rumus: $\text{Derating} = 1.0 - (T - 25) \times 0.004$.
* **Baris 181–201:** Blok `except` – Menyediakan *offline fallback* otomatis jika koneksi internet terputus sehingga server tidak pernah *crash*.

---

## 3. `core/simulation.py` – Komputasi Aliran Daya Newton-Raphson & Analisis

File inti (*computational engine*) yang menjalankan aliran daya non-linear, evaluasi standar SPLN, BESS, Smart Inverter, dan ekspor laporan.

### Rincian Fungsi & Logika Matematis:
1. **`run_power_flow(net)`:**
   * Mengeksekusi solver `pp.runpp(net, algorithm="nr", enforce_q_lims=True)`.
   * Algoritma **Newton-Raphson (NR)** memecahkan persamaan aliran daya non-linear melalui matriks Jacobian:
     $$\begin{bmatrix} \Delta P \\ \Delta Q \end{bmatrix} = \begin{bmatrix} J_{11} & J_{12} \\ J_{21} & J_{22} \end{bmatrix} \begin{bmatrix} \Delta \theta \\ \Delta V \end{bmatrix}$$
   * Jika tidak konvergen, sistem secara otomatis beralih (*fallback*) ke metode *Fast Decoupled Power Flow* (FDPF).
2. **Standar Toleransi SPLN 1:1995:**
   * `SPLN_V_MIN_PU = 0.90` (Batas bawah $-10\% = 198.0\text{ Volt}$).
   * `SPLN_V_MAX_PU = 1.05` (Batas atas $+5\% = 231.0\text{ Volt}$).
   * Memastikan tegangan di seluruh tiang tidak menyebabkan *undervoltage* (peralatan redup/rusak) atau *overvoltage* (inverter trip/elektronik terbakar).
3. **`run_time_series_comparison(...)` (Simulasi 24 Jam Komparatif):**
   * Mengiterasi jam 0 s.d. 23 untuk 2 kondisi paralel:
     * **Kondisi Base Case:** Jaringan murni memasok beban tanpa bantuan PLTS.
     * **Kondisi PV Case:** Jaringan dengan injeksi daya aktif dari PLTS atap.
   * **BESS Controller (Baterai):**
     * Pada siang terik (10.00–14.00 WIB): Jika daya surya berlebih, daya di-charge ke baterai (menaikkan SoC baterai, mencegah overvoltage).
     * Pada jam beban puncak malam (17.00–21.00 WIB): Daya baterai di-discharge ke rumah (*Peak Shaving*, menurunkan pembebanan trafo).
   * **Smart Inverter Volt-Var Control (IEEE 1547-2018):**
     * Menginjeksi daya reaktif ($+Q$) jika voltase turun di bawah 0.95 pu.
     * Menyerap daya reaktif ($-Q$) jika voltase naik di atas 1.03 pu untuk meratakan profil tegangan.
4. **`calculate_phase_unbalance(...)` (Analisis Ketidakseimbangan 3-Fasa):**
   * Memetakan beban rumah ke fasa R, S, dan T.
   * Menghitung arus kawat netral ($I_N$) menggunakan penjumlahan fasor:
     $$\vec{I}_N = \vec{I}_R + \vec{I}_S \angle -120^\circ + \vec{I}_T \angle 120^\circ$$
   * Menghitung rugi daya kawat netral ($P_{\text{loss}, N} = I_N^2 \times R_N$) dan memastikan *Voltage Unbalance Factor* (VUF) memenuhi standar IEC ($\le 2\%$).
5. **`calculate_hosting_capacity(...)` (Kapasitas Tampung Maksimum Feeder):**
   * Melakukan pemindaian bertahap (*stepping scan*) kapasitas PLTS dari 0.5 kWp hingga 15 kWp per rumah.
   * Mencatat batas kapasitas maksimum sebelum terjadi pelanggaran:
     1. Tegangan melebihi $231\text{ V}$ (+5% SPLN).
     2. Pembebanan kawat saluran melampaui $100\%$ KHA.
     3. Pembebanan trafo melampaui $100\%$ kapasitas kVA.
6. **`calculate_techno_economics(...)` (Analisis Finansial 25 Tahun):**
   * Menghitung Biaya Investasi Awal (*Capital Expenditure* / CAPEX).
   * Menghitung penghematan tagihan listrik tahunan berdasarkan tarif resmi PLN (Rp/kWh).
   * Menghitung *Payback Period* (Waktu Balik Modal) dan *Net Present Value* (NPV) dengan suku bunga diskonto 8%:
     $$\text{NPV} = \sum_{t=1}^{N} \frac{\text{Penghematan}_t}{(1 + r)^t} - \text{CAPEX}$$
   * Menghitung reduksi emisi karbon: $1\text{ kWh solar} \approx 0.85\text{ kg CO}_2$ (setara menanam ~22 kg $\text{CO}_2$/pohon/tahun).
7. **`export_simulation_to_docx` & `export_simulation_to_excel`:**
   * Menghasilkan proposal kelayakan resmi Microsoft Word (.docx) berorientasi konsumen dengan kop surat, tabel parameter, hasil evaluasi SPLN, dan tanda tangan legal konsultan.
   * Menghasilkan buku kerja audit Microsoft Excel (.xlsx) multi-sheet berisi riwayat tegangan 24 jam dan matriks finansial.

---

## 4. `server.py` – Backend Flask REST API

File ini menghubungkan antarmuka web (browser) dengan modul komputasi Python.

### Rincian Endpoint & Logika:
* **Baris 13–30:** Import modul Flask, pandas, numpy, serta modul `core`.
* **Baris 37–52 (`sanitize_json`):** Fungsi helper krusial untuk mengonversi objek NumPy (`int64`, `float64`) dan DataFrame Pandas menjadi tipe data asli Python (`int`, `float`, `dict`) agar tidak terjadi error `TypeError: Object of type int64 is not JSON serializable` saat dikirim ke browser.
* **Baris 55–58 (`@app.route("/")`):** Menampilkan antarmuka dashboard utama `templates/index.html`.
* **Baris 61–83 (`@app.route("/api/initial-config")`):** Mengirim daftar pilihan kabel, trafo, preset cuaca, dan daftar kota BMKG saat halaman web pertama kali dibuka.
* **Baris 86–91 (`@app.route("/api/bmkg")`):** Menerima request cuaca kota pilihan pengguna dan meneruskannya ke fungsi BMKG.
* **Baris 94–301 (`@app.route("/api/simulate")`):** Endpoint utama simulasi:
  * Menerima payload JSON: jumlah tiang, panjang bentang, kapasitas PLTS, tarif PLN, status baterai BESS, dsb.
  * Menjalankan simulasi aliran daya 24 jam dan mengembalikan hasil tegangan, rugi-rugi daya, evaluasi SPLN, dan tekno-ekonomi dalam format JSON.
* **Baris 303–320 (`@app.route("/api/hosting-capacity")`):** Endpoint pemindaian kapasitas penetrasi surya maksimum jaringan.
* **Baris 323–380 (`@app.route("/api/export-docx")` & `/api/export-excel`):** Menghasilkan file dokumen di memori server menggunakan `io.BytesIO()` dan mengirimkannya sebagai file unduhan langsung ke browser pengguna (`send_file`).
* **Baris 382–390 (`if __name__ == "__main__":`):** Membaca port dinamis `os.environ.get("PORT", 5000)` agar kompatibel saat dijalankan di komputer lokal maupun saat di-*deploy* ke cloud (Render/Railway).

---

## 5. `run_app.bat` – Script Otomatisasi Instalasi & Peluncur

File batch Windows yang bertindak sebagai *self-healing installer*:

### Rincian Alur Eksekusi:
1. `setlocal enabledelayedexpansion` & `cd /d "%~dp0"`: Mengunci folder kerja ke lokasi file proyek.
2. `if exist "%~dp0.venv\Scripts\python.exe" goto START_SERVER`: Jika virtual environment sudah ada, lewati proses instalasi dan langsung jalankan server.
3. **Pengecekan Pintasan Palsu Windows (*WindowsApps Alias Bypass*):**
   * Menguji perintah `python -c "import sys"`. Jika yang merespons adalah pintasan Microsoft Store (exit code 9009), script otomatis mengabaikannya.
   * Memindai direktori instalasi Python asli di Windows (`C:\Program Files\Python3*`, `%LOCALAPPDATA%\Programs\Python*`, `C:\Program Files\KiCad\*\bin\python.exe`, Conda).
4. **Dukungan `winget`:** Jika di komputer dosen/penguji belum ada Python sama sekali, script menawarkan pengunduhan Python 3.11 otomatis via *Windows Package Manager*.
5. `"!PY_EXE!" -m venv "%~dp0.venv"`: Membuat virtual environment lokal yang bersih dan terisolasi.
6. `pip install -r "%~dp0requirements.txt"`: Mengunduh dan memasang seluruh library (`pandapower`, `flask`, `python-docx`, `openpyxl`, `numpy`, `pandas`, `scipy`).
7. `start "" http://localhost:5000`: Membuka browser secara otomatis ke alamat dashboard simulator.

---

## 6. `templates/index.html` – Frontend Web Dashboard

Antarmuka pengguna tunggal modern (*Single Page Application*) yang menggabungkan:
1. **Desain CSS Glassmorphism & Monokrom Putih:**
   * Palet gelap Obsidian (`#0B0D14`, `#121624`) dengan teks dan aksen putih bersih (`#FFFFFF`).
   * Aksen warna fungsional tetap dipertahankan: Hijau Emerald (`#10B981`) untuk status aman SPLN dan penghematan, Kuning Surya (`#F59E0B`) untuk grafik radiasi dan batas atas, serta Merah (`#EF4444`) untuk batas kritis.
2. **Navigasi 10 Tab Kerja:**
   * Tab 0: Ringkasan 5 Kunci Konsumen & Eksekutif Verdict.
   * Tab 1: Dashboard Kepatuhan SPLN 1:1995 & Heatmap Tegangan 24 Jam.
   * Tab 2: Player Animasi Profil Tegangan Feeder Interaktif (Jam 0 s.d. 23).
   * Tab 3: Visualisasi Permukaan 3D (Waktu vs Tiang vs Tegangan) dengan tombol skenario: *Dengan PLTS, Tanpa PLTS, Dual Overlay 3D,* dan *Kenaikan $\Delta V$*.
   * Tab 4: Hosting Capacity Scanner (Batas Kuota Penetrasi PLTS).
   * Tab 5: Manajemen Baterai BESS (*Peak Shaving & Emergency Backup*).
   * Tab 6: Smart Inverter (IEEE 1547) & Ketidakseimbangan Beban 3-Fasa.
   * Tab 7: Analisis Finansial & Tekno-Ekonomi 25 Tahun (Arus Kas, NPV, ROI).
   * Tab 8: Editor Topologi Jaringan Interaktif (Drag & Drop Canvas).
   * Tab 9: Formulir Data Konsumen & Tombol Ekspor Proposal Word/Excel.
3. **Engine Visualisasi Plotly.js ES6:**
   * Seluruh grafik dirender di sisi browser secara responsif tanpa perlu *reload* halaman web.
   * Sinkronisasi data otomatis (*two-way binding*) antara pilihan golongan tarif PLN (450 VA s.d. 6.600 VA) dengan simulasi tekno-ekonomi.

---

## 💡 Tips & Trik Menjawab Pertanyaan Dosen Saat Sidang:
1. **Pertanyaan: Mengapa menggunakan metode Newton-Raphson, bukan Gauss-Seidel?**
   * *Jawaban:* Newton-Raphson memiliki konvergensi kuadratik yang jauh lebih cepat (hanya butuh 3–5 iterasi) dan sangat stabil untuk sistem distribusi dengan rasio $R/X$ kabel yang relatif tinggi seperti pada kabel LVTC.
2. **Pertanyaan: Mengapa tegangan di siang hari bisa naik saat PLTS aktif?**
   * *Jawaban:* Sesuai hukum Ohm dan persamaan aliran daya, injeksi daya aktif ($P_{\text{PV}}$) dari inverter surya mengurangi arus yang mengalir dari gardu trafo, bahkan dapat menyebabkan aliran daya balik (*reverse power flow*), sehingga gradien jatuh tegangan terbalik ($\Delta V \approx \frac{P \cdot R + Q \cdot X}{V}$) dan menaikkan voltase di ujung tiang.
3. **Pertanyaan: Mengapa pada pelanggan 450 VA dan 900 VA waktu balik modal lebih lama?**
   * *Jawaban:* Karena tarif listrik golongan 450 VA (Rp 415/kWh) dan 900 VA (Rp 605/kWh) mendapatkan subsidi besar dari pemerintah. Nilai penghematan tagihan per kWh yang dihasilkan PLTS lebih kecil dibandingkan jika dipasang pada pelanggan 1.300 VA ke atas (Rp 1.444,70/kWh) yang tarifnya non-subsidi.
