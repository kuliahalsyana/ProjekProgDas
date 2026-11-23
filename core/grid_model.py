"""
=============================================================================================
VoltSolar-Sim Pro Enterprise - Modul Pemodelan Jaringan Distribusi Tegangan Rendah (JTR)
Program Studi: Teknologi Rekayasa Elektro | Praktikum Pemrograman Dasar
=============================================================================================
Fungsi Utama Modul:
1. Memodelkan Trafo Distribusi Penurun Tegangan (Step-Down 20 kV / 0.4 kV) standar PLN.
2. Memodelkan Saluran Kabel Pilin Udara Tegangan Rendah (LVTC - Low Voltage Twisted Cable).
3. Memodelkan Titik Beban Konsumen Rumah Tangga (Load) berbasis daya aktif (P) & reaktif (Q).
4. Memodelkan Pembangkit Listrik Tenaga Surya (PLTS) Atap On-Grid sebagai Static Generator (sgen).
5. Mendukung Topologi Linear Radial Standar maupun Topologi Kustom Bercabang (Tree Network).
=============================================================================================
"""

import pandapower as pp  # Library komputasi aliran daya standar industri (Newton-Raphson)
import numpy as np       # Library operasi numerik, trigonometri, dan matriks


# =============================================================================================
# 1. DATABASE SPESIFIKASI KABEL JTR STANDAR PLN (Kabel Pilin / Twisted Cable LVTC)
# Parameter keteknikan:
# - r_ohm_per_km: Resistansi kawat konduktor per kilometer (Ohm/km) -> menentukan jatuh tegangan resistif
# - x_ohm_per_km: Reaktansi induktif kawat konduktor per kilometer (Ohm/km) -> induktansi saluran
# - max_i_ka: Arus kontinu maksimal yang diizinkan (kilo-Ampere) -> batas kapasitas termal kawat
# - c_nf_per_km: Kapasitansi saluran ke tanah (nano-Farad/km) -> mendekati 0 untuk kabel udara pendek
# =============================================================================================
CABLE_TYPES = {
    "LVTC 3x70 + 1x50 mm²": {
        "r_ohm_per_km": 0.443,  # Resistansi rendah, cocok untuk saluran utama (tulang punggung feeder)
        "x_ohm_per_km": 0.080,  # Reaktansi induktif kabel pilin 70 mm²
        "max_i_ka": 0.190,      # Kuat Hantar Arus (KHA) maksimum 190 Ampere
        "c_nf_per_km": 0.0      # Kapasitansi shunt diabaikan pada tegangan rendah
    },
    "LVTC 3x50 + 1x35 mm²": {
        "r_ohm_per_km": 0.641,  # Resistansi sedang, cocok untuk feeder percabangan sekunder
        "x_ohm_per_km": 0.082,  # Reaktansi induktif kabel pilin 50 mm²
        "max_i_ka": 0.150,      # KHA maksimum 150 Ampere
        "c_nf_per_km": 0.0
    },
    "LVTC 3x35 + 1x25 mm²": {
        "r_ohm_per_km": 0.868,  # Resistansi lebih tinggi, umum untuk cabang pendek
        "x_ohm_per_km": 0.085,  # Reaktansi kabel 35 mm²
        "max_i_ka": 0.125,      # KHA maksimum 125 Ampere
        "c_nf_per_km": 0.0
    },
    "LVTC 3x25 + 1x25 mm²": {
        "r_ohm_per_km": 1.200,  # Resistansi tinggi, hanya untuk ujung beban kecil
        "x_ohm_per_km": 0.088,  # Reaktansi kabel 25 mm²
        "max_i_ka": 0.100,      # KHA maksimum 100 Ampere
        "c_nf_per_km": 0.0
    }
}


# =============================================================================================
# 2. DATABASE STANDAR KAPASITAS TRAFO DISTRIBUSI PLN (20 kV / 0.4 kV)
# Parameter keteknikan:
# - sn_mva: Daya semu nominal transformator dalam satuan Mega-Volt-Ampere (MVA)
# - vn_hv_kv: Tegangan nominal belitan primer / sisi Tegangan Menengah (TM = 20.0 kV)
# - vn_lv_kv: Tegangan nominal belitan sekunder / sisi Tegangan Rendah (TR = 0.4 kV / 400 V fasa-ke-fasa)
# - vk_percent: Tegangan hubung singkat / impedansi ekivalen (%) -> menentukan drop tegangan internal trafo
# - vkr_percent: Rugi resistif hubung singkat trafo (%) -> rugi tembaga saat beban penuh
# - pfe_kw: Rugi inti besi trafo / rugi tanpa beban (kilo-Watt) -> selalu ada selama trafo berenergi
# - i0_percent: Arus eksitasi / arus tanpa beban (%)
# =============================================================================================
TRANSFORMER_TYPES = {
    "50 kVA (20/0.4 kV)": {
        "sn_mva": 0.05, "vn_hv_kv": 20.0, "vn_lv_kv": 0.4,
        "vk_percent": 4.0, "vkr_percent": 1.1, "pfe_kw": 0.19, "i0_percent": 0.30
    },
    "100 kVA (20/0.4 kV)": {
        "sn_mva": 0.10, "vn_hv_kv": 20.0, "vn_lv_kv": 0.4,
        "vk_percent": 4.0, "vkr_percent": 1.1, "pfe_kw": 0.32, "i0_percent": 0.28
    },
    "160 kVA (20/0.4 kV)": {
        "sn_mva": 0.16, "vn_hv_kv": 20.0, "vn_lv_kv": 0.4,
        "vk_percent": 4.0, "vkr_percent": 1.1, "pfe_kw": 0.46, "i0_percent": 0.25
    },
    "200 kVA (20/0.4 kV)": {
        "sn_mva": 0.20, "vn_hv_kv": 20.0, "vn_lv_kv": 0.4,
        "vk_percent": 4.0, "vkr_percent": 1.1, "pfe_kw": 0.55, "i0_percent": 0.23
    },
    "250 kVA (20/0.4 kV)": {
        "sn_mva": 0.25, "vn_hv_kv": 20.0, "vn_lv_kv": 0.4,
        "vk_percent": 4.0, "vkr_percent": 1.1, "pfe_kw": 0.65, "i0_percent": 0.22
    },
    "400 kVA (20/0.4 kV)": {
        "sn_mva": 0.40, "vn_hv_kv": 20.0, "vn_lv_kv": 0.4,
        "vk_percent": 4.0, "vkr_percent": 1.0, "pfe_kw": 0.93, "i0_percent": 0.20
    }
}


def create_lv_network(
    num_buses: int = 10,
    span_length_km: float = 0.040,
    cable_type_name: str = "LVTC 3x70 + 1x50 mm²",
    transformer_type_name: str = "100 kVA (20/0.4 kV)",
    base_load_per_bus_kw: float = 1.3,
    power_factor: float = 0.95,
    pv_installed_indices: list = None,
    pv_capacity_per_bus_kw: float = 2.0,
    include_pv: bool = True,
    custom_branches: list = None
) -> pp.pandapowerNet:
    """
    Membangun model jaringan sistem tenaga listrik Tegangan Rendah (JTR) berbasis pandapower.
    
    Parameter:
    - num_buses: Jumlah tiang/bus konsumen untuk topologi linear (default: 10 tiang).
    - span_length_km: Jarak bentangan antar tiang dalam kilometer (40 meter = 0.040 km).
    - cable_type_name: Nama tipe kabel konduktor dari dictionary CABLE_TYPES.
    - transformer_type_name: Spesifikasi kapasitas gardu trafo dari TRANSFORMER_TYPES.
    - base_load_per_bus_kw: Daya aktif beban rata-rata per rumah (kW).
    - power_factor: Faktor daya beban rumah tangga (cos phi, default 0.95 lagging).
    - pv_installed_indices: Daftar tiang/rumah yang terpasang sistem PLTS atap.
    - pv_capacity_per_bus_kw: Kapasitas nominal inverter PLTS tiap rumah (kWp).
    - include_pv: Sakelar status aktivasi sistem PLTS atap (True/False).
    - custom_branches: Struktur percabangan kustom jika bukan topologi linear murni.
    
    Output:
    - pp.pandapowerNet: Objek jaringan listrik terintegrasi siap dihitung dengan Newton-Raphson.
    """
    # Inisialisasi wadah jaringan listrik kosong
    net = pp.create_empty_network(name="JTR_Distribusi_Residensial") #buat jaringan kosong
    
    # -----------------------------------------------------------------------------------------
    # LANGKAH 1: Bus & Sumber Daya Sisi Tegangan Menengah (Grid PLN 20 kV)
    # -----------------------------------------------------------------------------------------
    # Bus tegangan menengah 20 kV sebagai sisi primer transformator
    bus_mv = pp.create_bus(net, vn_kv=20.0, name="Bus_TM_20kV", zone="TM") #membuat bus
    # External grid merepresentasikan sumber daya tak terbatas PLN (Slack Bus / V-theta bus: V = 1.0 pu)
    pp.create_ext_grid(net, bus=bus_mv, vm_pu=1.0, name="Grid_TM_PLN")
    
    # -----------------------------------------------------------------------------------------
    # LANGKAH 2: Bus Pangkal Tegangan Rendah (LV Root / Sisi Sekunder Trafo 400 V)
    # -----------------------------------------------------------------------------------------
    # Bus tegangan rendah 0.4 kV (400 Volt fasa-ke-fasa / 230 Volt fasa-ke-netral)
    bus_lv_root = pp.create_bus(net, vn_kv=0.4, name="Bus_Trafo_TR", zone="TR")
    
    # -----------------------------------------------------------------------------------------
    # LANGKAH 3: Pemasangan Transformator Distribusi TM/TR (Dyn5)
    # -----------------------------------------------------------------------------------------
    # Ambil spesifikasi trafo sesuai opsi yang dipilih di antarmuka web
    trafo_specs = TRANSFORMER_TYPES.get(transformer_type_name, TRANSFORMER_TYPES["100 kVA (20/0.4 kV)"])
    # Hubungkan sisi HV ke Bus TM dan sisi LV ke Bus TR
    pp.create_transformer_from_parameters(
        net,
        hv_bus=bus_mv,
        lv_bus=bus_lv_root,
        sn_mva=trafo_specs["sn_mva"],
        vn_hv_kv=trafo_specs["vn_hv_kv"],
        vn_lv_kv=trafo_specs["vn_lv_kv"],
        vk_percent=trafo_specs["vk_percent"],
        vkr_percent=trafo_specs["vkr_percent"],
        pfe_kw=trafo_specs["pfe_kw"],
        i0_percent=trafo_specs["i0_percent"],
        name="Trafo_Distribusi"
    )
    
    # -----------------------------------------------------------------------------------------
    # LANGKAH 4: Konfigurasi Parameter Beban & Konversi Daya Reaktif (Q)
    # -----------------------------------------------------------------------------------------
    # Ambil spesifikasi teknis konduktor saluran
    cable_specs = CABLE_TYPES.get(cable_type_name, CABLE_TYPES["LVTC 3x70 + 1x50 mm²"])
    
    # Hitung daya reaktif Q berdasarkan rumus daya semu segitiga daya: Q = P * tan(arccos(cos_phi))
    tan_phi = np.tan(np.arccos(power_factor))
    base_q_kvar = base_load_per_bus_kw * tan_phi
    
    # Normalisasi daftar bus PLTS yang dipilih pengguna agar fleksibel (menerima angka maupun teks)
    if pv_installed_indices is None:
        pv_installed_indices = []
        
    pv_set = set()
    for item in pv_installed_indices:
        if isinstance(item, int):
            pv_set.add(f"Tiang_{item}")
            pv_set.add(item)
        else:
            pv_set.add(str(item))
            if str(item).startswith("Tiang_"):
                try:
                    pv_set.add(int(str(item).split("_")[1]))
                except Exception:
                    pass

    # -----------------------------------------------------------------------------------------
    # LANGKAH 5: Pembangunan Saluran Distribusi & Beban Konsumen
    # -----------------------------------------------------------------------------------------
    if custom_branches and len(custom_branches) > 0:
        # KASUS A: TOPOLOGI KUSTOM BERCABANG (TREE NETWORK)
        bus_lookup = {"Trafo": bus_lv_root, "Bus_Trafo_TR": bus_lv_root}
        
        # Ekstrak seluruh daftar nama tiang unik dari relasi percabangan
        all_bus_names = []
        for branch in custom_branches:
            for name in [branch["from"], branch["to"]]:
                if name not in ["Trafo", "Bus_Trafo_TR"] and name not in all_bus_names:
                    all_bus_names.append(name)
                    
        # Buat bus dan pasang beban rumah di setiap bus unik
        for b_name in all_bus_names:
            b_id = pp.create_bus(net, vn_kv=0.4, name=b_name, zone="TR")
            bus_lookup[b_name] = b_id
            
            # Pasang Beban Konsumen (Daya dikonversi dari kW/kVAR ke MW/MVAR untuk pandapower)
            pp.create_load(
                net,
                bus=b_id,
                p_mw=base_load_per_bus_kw / 1000.0,
                q_mvar=base_q_kvar / 1000.0,
                name=f"Beban_{b_name}"
            )
            
            # Pasang Inverter PLTS Atap jika bus ini dipilih
            if include_pv and (b_name in pv_set):
                pp.create_sgen(
                    net,
                    bus=b_id,
                    p_mw=pv_capacity_per_bus_kw / 1000.0,
                    q_mvar=0.0,
                    name=f"PLTS_{b_name}",
                    type="PV"
                )
                
        # Bentangkan saluran kabel penghubung antar tiang sesuai relasi cabang
        for branch in custom_branches:
            from_id = bus_lookup.get(branch["from"])
            to_id = bus_lookup.get(branch["to"])
            if from_id is not None and to_id is not None:
                pp.create_line_from_parameters(
                    net,
                    from_bus=from_id,
                    to_bus=to_id,
                    length_km=span_length_km,
                    r_ohm_per_km=cable_specs["r_ohm_per_km"],
                    x_ohm_per_km=cable_specs["x_ohm_per_km"],
                    c_nf_per_km=cable_specs["c_nf_per_km"],
                    max_i_ka=cable_specs["max_i_ka"],
                    name=f"Saluran_{branch['from']}_{branch['to']}"
                )
    else:
        # KASUS B: TOPOLOGI RADIAL LINEAR STANDAR (Trafo -> Tiang 1 -> Tiang 2 -> ... -> Tiang N)
        previous_bus = bus_lv_root
        for i in range(1, num_buses + 1):
            bus_name = f"Tiang_{i}"
            current_bus = pp.create_bus(net, vn_kv=0.4, name=bus_name, zone="TR")
            
            # Buat segmen saluran kabel dari tiang sebelumnya ke tiang saat ini
            pp.create_line_from_parameters(
                net,
                from_bus=previous_bus,
                to_bus=current_bus,
                length_km=span_length_km,
                r_ohm_per_km=cable_specs["r_ohm_per_km"],
                x_ohm_per_km=cable_specs["x_ohm_per_km"],
                c_nf_per_km=cable_specs["c_nf_per_km"],
                max_i_ka=cable_specs["max_i_ka"],
                name=f"Saluran_{previous_bus}_{current_bus}"
            )
            
            # Pasang beban listrik rumah tangga di tiang ini
            pp.create_load(
                net,
                bus=current_bus,
                p_mw=base_load_per_bus_kw / 1000.0,
                q_mvar=base_q_kvar / 1000.0,
                name=f"Beban_Rumah_{i}"
            )
            
            # Pasang generator surya PLTS jika tiang ini dipilih oleh pengguna
            if include_pv and ((i in pv_set) or (bus_name in pv_set)):
                pp.create_sgen(
                    net,
                    bus=current_bus,
                    p_mw=pv_capacity_per_bus_kw / 1000.0,
                    q_mvar=0.0,
                    name=f"PLTS_Atap_{i}",
                    type="PV"
                )
                
            # Geser penunjuk tiang sebelumnya untuk iterasi kabel tiang berikutnya
            previous_bus = current_bus
        
    return net