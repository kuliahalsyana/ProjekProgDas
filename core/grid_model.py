"""
Modul Pemodelan Jaringan Distribusi Tegangan Rendah (JTR)
Menggunakan library pandapower untuk memodelkan:
- Sumber tegangan menengah (Trafo MV/LV 20kV / 0.4kV)
- Saluran distribusi radial (Kabel LVTC standar PLN)
- Titik beban rumah tangga
- Pembangkit Listrik Tenaga Surya (PLTS) Atap On-Grid (Static Generator)
"""

import pandapower as pp
import numpy as np

# Database Spesifikasi Kabel JTR Standar PLN (Kabel Pilin / Twisted Cable LVTC)
# Resistansi (r_ohm_per_km), Reaktansi (x_ohm_per_km), dan Arus Maksimum (max_i_ka)
CABLE_TYPES = {
    "LVTC 3x70 + 1x50 mm²": {
        "r_ohm_per_km": 0.443,
        "x_ohm_per_km": 0.080,
        "max_i_ka": 0.190,
        "c_nf_per_km": 0.0
    },
    "LVTC 3x50 + 1x35 mm²": {
        "r_ohm_per_km": 0.641,
        "x_ohm_per_km": 0.082,
        "max_i_ka": 0.150,
        "c_nf_per_km": 0.0
    },
    "LVTC 3x35 + 1x25 mm²": {
        "r_ohm_per_km": 0.868,
        "x_ohm_per_km": 0.085,
        "max_i_ka": 0.125,
        "c_nf_per_km": 0.0
    },
    "LVTC 3x25 + 1x25 mm²": {
        "r_ohm_per_km": 1.200,
        "x_ohm_per_km": 0.088,
        "max_i_ka": 0.100,
        "c_nf_per_km": 0.0
    }
}

# Database Standar Kapasitas Trafo Distribusi 20 kV / 0.4 kV
TRANSFORMER_TYPES = {
    "50 kVA (20/0.4 kV)": {"sn_mva": 0.05, "vn_hv_kv": 20.0, "vn_lv_kv": 0.4, "vk_percent": 4.0, "vkr_percent": 1.1, "pfe_kw": 0.19, "i0_percent": 0.3},
    "100 kVA (20/0.4 kV)": {"sn_mva": 0.10, "vn_hv_kv": 20.0, "vn_lv_kv": 0.4, "vk_percent": 4.0, "vkr_percent": 1.1, "pfe_kw": 0.32, "i0_percent": 0.28},
    "160 kVA (20/0.4 kV)": {"sn_mva": 0.16, "vn_hv_kv": 20.0, "vn_lv_kv": 0.4, "vk_percent": 4.0, "vkr_percent": 1.1, "pfe_kw": 0.46, "i0_percent": 0.25},
    "200 kVA (20/0.4 kV)": {"sn_mva": 0.20, "vn_hv_kv": 20.0, "vn_lv_kv": 0.4, "vk_percent": 4.0, "vkr_percent": 1.1, "pfe_kw": 0.55, "i0_percent": 0.23},
    "250 kVA (20/0.4 kV)": {"sn_mva": 0.25, "vn_hv_kv": 20.0, "vn_lv_kv": 0.4, "vk_percent": 4.0, "vkr_percent": 1.1, "pfe_kw": 0.65, "i0_percent": 0.22},
    "400 kVA (20/0.4 kV)": {"sn_mva": 0.40, "vn_hv_kv": 20.0, "vn_lv_kv": 0.4, "vk_percent": 4.0, "vkr_percent": 1.0, "pfe_kw": 0.93, "i0_percent": 0.20}
}


def create_lv_network(
    num_buses: int = 10,
    span_length_km: float = 0.040,  # 40 meter per gawang tiang
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
    Membuat topologi jaringan radial tegangan rendah (JTR), mendukung:
    1. Topologi Linear Konvensional (Trafo -> Tiang 1 -> Tiang 2 -> ... -> Tiang N)
    2. Topologi Kustom Bercabang / Tree Network (misal: Tiang 2 bercabang ke Tiang 3 dan Tiang 5)
    
    Args:
        num_buses: Jumlah tiang/bus konsumen (jika linear).
        span_length_km: Jarak antar tiang (kilometer).
        cable_type_name: Tipe kabel dari CABLE_TYPES.
        transformer_type_name: Tipe trafo dari TRANSFORMER_TYPES.
        base_load_per_bus_kw: Daya aktif nominal beban per bus (kW).
        power_factor: Faktor daya beban (lagging, cos phi).
        pv_installed_indices: Daftar index atau nama bus yang dipasang PLTS.
        pv_capacity_per_bus_kw: Kapasitas inverter PLTS per rumah (kWp).
        include_pv: Flag apakah PLTS diaktifkan.
        custom_branches: List dict percabangan kustom [{'from': 'Trafo', 'to': 'Tiang_1'}, ...].
        
    Returns:
        pp.pandapowerNet: Objek jaringan pandapower siap simulasi.
    """
    net = pp.create_empty_network(name="JTR_Distribusi_Residensial")
    
    # 1. Bus Sisi Tegangan Menengah (TM 20 kV)
    bus_mv = pp.create_bus(net, vn_kv=20.0, name="Bus_TM_20kV", zone="TM")
    pp.create_ext_grid(net, bus=bus_mv, vm_pu=1.0, name="Grid_TM_PLN")
    
    # 2. Bus Sisi Tegangan Rendah Trafo (TR 0.4 kV) - Bus Pangkal
    bus_lv_root = pp.create_bus(net, vn_kv=0.4, name="Bus_Trafo_TR", zone="TR")
    
    # 3. Trafo Distribusi TM/TR
    trafo_specs = TRANSFORMER_TYPES.get(transformer_type_name, TRANSFORMER_TYPES["100 kVA (20/0.4 kV)"])
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
    
    # 4. Standar Kabel JTR
    cable_specs = CABLE_TYPES.get(cable_type_name, CABLE_TYPES["LVTC 3x70 + 1x50 mm²"])
    
    # Hitung daya reaktif dasar berdasarkan cos phi
    tan_phi = np.tan(np.arccos(power_factor))
    base_q_kvar = base_load_per_bus_kw * tan_phi
    
    if pv_installed_indices is None:
        pv_installed_indices = []
        
    # Normalisasi pv_installed_indices agar mendukung int (1, 2) maupun str ('Tiang_1')
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

    # 5. Membangun Saluran Feeder (Linear atau Kustom Percabangan)
    if custom_branches and len(custom_branches) > 0:
        # TOPOLOGI KUSTOM BERCABANG
        bus_lookup = {"Trafo": bus_lv_root, "Bus_Trafo_TR": bus_lv_root}
        
        # Ekstrak semua bus unik
        all_bus_names = []
        for branch in custom_branches:
            f_name = branch["from"]
            t_name = branch["to"]
            for name in [f_name, t_name]:
                if name not in ["Trafo", "Bus_Trafo_TR"] and name not in all_bus_names:
                    all_bus_names.append(name)
                    
        # Buat bus di pandapower
        for b_name in all_bus_names:
            b_id = pp.create_bus(net, vn_kv=0.4, name=b_name, zone="TR")
            bus_lookup[b_name] = b_id
            
            # Pasang Beban Rumah Tangga
            pp.create_load(
                net,
                bus=b_id,
                p_mw=base_load_per_bus_kw / 1000.0,
                q_mvar=base_q_kvar / 1000.0,
                name=f"Beban_{b_name}"
            )
            
            # Pasang PLTS jika terdaftar
            if include_pv and (b_name in pv_set):
                pp.create_sgen(
                    net,
                    bus=b_id,
                    p_mw=pv_capacity_per_bus_kw / 1000.0,
                    q_mvar=0.0,
                    name=f"PLTS_{b_name}",
                    type="PV"
                )
                
        # Buat saluran penghubung antar bus
        for branch in custom_branches:
            f_name = branch["from"]
            t_name = branch["to"]
            from_id = bus_lookup.get(f_name)
            to_id = bus_lookup.get(t_name)
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
                    name=f"Saluran_{f_name}_{t_name}"
                )
    else:
        # TOPOLOGI RADIAL LINEAR DEFAULT
        previous_bus = bus_lv_root
        for i in range(1, num_buses + 1):
            bus_name = f"Tiang_{i}"
            current_bus = pp.create_bus(net, vn_kv=0.4, name=bus_name, zone="TR")
            
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
            
            pp.create_load(
                net,
                bus=current_bus,
                p_mw=base_load_per_bus_kw / 1000.0,
                q_mvar=base_q_kvar / 1000.0,
                name=f"Beban_Rumah_{i}"
            )
            
            if include_pv and ((i in pv_set) or (bus_name in pv_set)):
                pp.create_sgen(
                    net,
                    bus=current_bus,
                    p_mw=pv_capacity_per_bus_kw / 1000.0,
                    q_mvar=0.0,
                    name=f"PLTS_Atap_{i}",
                    type="PV"
                )
                
            previous_bus = current_bus
        
    return net
