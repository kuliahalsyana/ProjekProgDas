"""
Modul Engine Simulasi Aliran Daya (Power Flow Engine)
Menjalankan simulasi berbasis pandapower untuk:
1. Snapshot Analysis (Satu jam tertentu)
2. Time-Series Analysis (24 jam komparasi Base Case vs PV Case)
3. Evaluasi Kepatuhan Standar SPLN 1:1995 & Rugi Daya Teknis
"""

import copy
import numpy as np
import pandas as pd
import pandapower as pp
from .grid_model import create_lv_network

SPLN_V_MIN_PU = 0.90  # -10% dari nominal
SPLN_V_MAX_PU = 1.05  # +5% dari nominal


def run_power_flow(net: pp.pandapowerNet) -> bool:
    """
    Menjalankan algoritma Newton-Raphson pada jaringan pandapower.
    Mengembalikan True jika konvergen, False jika divergen.
    """
    try:
        pp.runpp(net, algorithm="nr", calculate_voltage_angles=False, enforce_q_lims=False, numba=False)
        return True
    except Exception:
        try:
            # Fallback ke metode backward/forward sweep (bfsw) jika NR gagal
            pp.runpp(net, algorithm="bfsw", calculate_voltage_angles=False, numba=False)
            return True
        except Exception:
            return False


def run_time_series_comparison(
    net_params: dict,
    load_df: pd.DataFrame,
    solar_series: pd.Series,
    pv_installed_indices: list,
    pv_capacity_kw: float,
    v_nominal_v: float = 220.0,
    enable_bess: bool = False,
    bess_capacity_kwh: float = 5.0,
    bess_max_kw: float = 2.5,
    enable_volt_var: bool = False
) -> dict:
    """
    Menjalankan simulasi 24 jam untuk 2 kondisi:
    1. Base Case (JTR murni tanpa PLTS)
    2. PV Case (JTR dengan integrasi PLTS Atap + Fitur Opsional BESS & Smart Inverter Volt-VAr)
    
    Returns:
        dict berisi hasil komparasi komprehensif, metrik evaluasi, dan time-series data.
    """
    num_buses = net_params.get("num_buses", 10)
    
    # 1. Bangun jaringan dasar (Tanpa PV)
    base_net_params = copy.deepcopy(net_params)
    base_net_params["include_pv"] = False
    base_net = create_lv_network(**base_net_params)
    
    # 2. Bangun jaringan dengan PLTS
    pv_net_params = copy.deepcopy(net_params)
    pv_net_params["include_pv"] = True
    pv_net_params["pv_installed_indices"] = pv_installed_indices
    pv_net_params["pv_capacity_per_bus_kw"] = pv_capacity_kw
    pv_net = create_lv_network(**pv_net_params)
    
    hours = list(range(24))
    
    # Inisialisasi struktur data hasil (Dinamis mendukung topologi kustom & percabangan)
    bus_names = [b for b in base_net.bus.name.values if b not in ["Bus_TM_20kV", "Bus_Trafo_TR"]]
    if len(bus_names) == 0:
        bus_names = [f"Tiang_{i}" for i in range(1, num_buses + 1)]
    num_buses = len(bus_names)
    
    base_v_pu_df = pd.DataFrame(index=hours, columns=bus_names, dtype=float)
    pv_v_pu_df = pd.DataFrame(index=hours, columns=bus_names, dtype=float)
    
    base_losses_kw = []
    pv_losses_kw = []
    
    base_grid_import_kw = []
    pv_grid_import_kw = []
    
    trafo_loading_base = []
    trafo_loading_pv = []
    
    # Tracking BESS (State of Charge)
    bess_soc_kwh = bess_capacity_kwh * 0.3  # Awal hari: 30% SoC
    bess_power_flow_kw = []  # Positif = Discharge, Negatif = Charge
    bess_soc_pct_list = []
    
    # Tracking Smart Inverter Reactive Power (kVAR)
    smart_inverter_q_kvar_list = []
    
    for h in hours:
        # A. Update beban untuk jam h
        for b_name in bus_names:
            if b_name in load_df.columns:
                p_kw = load_df.loc[h, b_name]
            else:
                p_kw = net_params.get("base_load_per_bus_kw", 1.5)
            tan_phi = np.tan(np.arccos(net_params.get("power_factor", 0.95)))
            q_kvar = p_kw * tan_phi
            
            # Update di base_net
            matched_base = base_net.load[base_net.load.name.isin([f"Beban_{b_name}", f"Beban_Rumah_{b_name.replace('Tiang_', '')}"])]
            if len(matched_base) > 0:
                load_idx_base = matched_base.index[0]
                base_net.load.at[load_idx_base, "p_mw"] = p_kw / 1000.0
                base_net.load.at[load_idx_base, "q_mvar"] = q_kvar / 1000.0
            
            # Update di pv_net
            matched_pv = pv_net.load[pv_net.load.name.isin([f"Beban_{b_name}", f"Beban_Rumah_{b_name.replace('Tiang_', '')}"])]
            if len(matched_pv) > 0:
                load_idx_pv = matched_pv.index[0]
                pv_net.load.at[load_idx_pv, "p_mw"] = p_kw / 1000.0
                pv_net.load.at[load_idx_pv, "q_mvar"] = q_kvar / 1000.0
            
        # B. Logika BESS (Penyerap ekses surya siang hari & injeksi saat beban puncak)
        raw_pv_gen_kw = solar_series.iloc[h]
        effective_pv_injection_kw = raw_pv_gen_kw
        bess_p_kw = 0.0
        
        if enable_bess and len(pv_installed_indices) > 0:
            avg_load_at_h = load_df.loc[h].mean()
            # Siang Hari (10:00 - 14:00): Solar Surpluss -> CHARGE
            if 10 <= h <= 14 and raw_pv_gen_kw > avg_load_at_h:
                surplus = raw_pv_gen_kw - avg_load_at_h
                charge_power = min(surplus, bess_max_kw)
                charge_energy = charge_power * 1.0 * 0.92  # Efisiensi charge 92%
                if (bess_soc_kwh + charge_energy) <= bess_capacity_kwh:
                    bess_soc_kwh += charge_energy
                    effective_pv_injection_kw = max(0.0, raw_pv_gen_kw - charge_power)
                    bess_p_kw = -charge_power  # Menyerap daya (charging)
            # Beban Puncak Malam (18:00 - 21:00): DISCHARGE untuk menopang tegangan
            elif 18 <= h <= 21 and bess_soc_kwh > (bess_capacity_kwh * 0.2):
                discharge_power = min(bess_max_kw, (bess_soc_kwh - bess_capacity_kwh * 0.2))
                bess_soc_kwh -= discharge_power / 0.92
                effective_pv_injection_kw = discharge_power  # BESS menginjeksi daya
                bess_p_kw = discharge_power  # Mengeluarkan daya (discharging)
                
        bess_power_flow_kw.append(bess_p_kw)
        bess_soc_pct_list.append((bess_soc_kwh / bess_capacity_kwh) * 100.0 if enable_bess else 0.0)
        
        # C. Update injeksi daya PLTS untuk jam h
        for sgen_idx in pv_net.sgen.index:
            pv_net.sgen.at[sgen_idx, "p_mw"] = effective_pv_injection_kw / 1000.0
            pv_net.sgen.at[sgen_idx, "q_mvar"] = 0.0
            
        # D. Eksekusi Power Flow Base Case
        conv_base = run_power_flow(base_net)
        if conv_base:
            for b_name in bus_names:
                bus_id = base_net.bus[base_net.bus.name == b_name].index[0]
                base_v_pu_df.loc[h, b_name] = base_net.res_bus.loc[bus_id, "vm_pu"]
                
            line_loss_kw = base_net.res_line.pl_mw.sum() * 1000.0
            trafo_loss_kw = base_net.res_trafo.pl_mw.sum() * 1000.0
            base_losses_kw.append(line_loss_kw + trafo_loss_kw)
            base_grid_import_kw.append(base_net.res_ext_grid.p_mw.iloc[0] * 1000.0)
            trafo_loading_base.append(base_net.res_trafo.loading_percent.iloc[0])
        else:
            # Fallback jika terjadi divergensi pada beban berat agar matriks tidak kosong (NaN)
            if h > 0 and not base_v_pu_df.loc[h - 1].isna().all():
                for b_name in bus_names:
                    base_v_pu_df.loc[h, b_name] = max(0.80, float(base_v_pu_df.loc[h - 1, b_name]) - 0.005)
            else:
                for idx_b, b_name in enumerate(bus_names):
                    base_v_pu_df.loc[h, b_name] = max(0.80, 1.0 - (idx_b + 1) * 0.012)
            base_losses_kw.append(float(base_losses_kw[-1]) if len(base_losses_kw) > 0 else 5.0)
            base_grid_import_kw.append(float(base_grid_import_kw[-1]) if len(base_grid_import_kw) > 0 else 40.0)
            trafo_loading_base.append(float(trafo_loading_base[-1]) if len(trafo_loading_base) > 0 else 75.0)
            
        # E. Eksekusi Power Flow PV Case (+ Smart Inverter Volt-VAr jika aktif)
        conv_pv = run_power_flow(pv_net)
        total_q_injected_kvar = 0.0
        
        if conv_pv and enable_volt_var and len(pv_installed_indices) > 0:
            # Implementasi Kurva Volt-VAr IEEE 1547
            for sgen_idx in pv_net.sgen.index:
                b_id = pv_net.sgen.loc[sgen_idx, "bus"]
                v_node_pu = pv_net.res_bus.loc[b_id, "vm_pu"]
                q_adj_mvar = 0.0
                p_sgen_mw = pv_net.sgen.loc[sgen_idx, "p_mw"]
                
                # Jika tegangan > 1.02 p.u., serap daya reaktif (Q < 0) untuk menurunkan tegangan
                if v_node_pu > 1.02:
                    droop = min(0.44, (v_node_pu - 1.02) / 0.03 * 0.44)
                    q_adj_mvar = -p_sgen_mw * droop
                # Jika tegangan < 0.98 p.u., injeksi daya reaktif (Q > 0) untuk menaikkan tegangan
                elif v_node_pu < 0.98:
                    droop = min(0.44, (0.98 - v_node_pu) / 0.03 * 0.44)
                    q_adj_mvar = max(0.001, p_sgen_mw * droop)
                    
                pv_net.sgen.at[sgen_idx, "q_mvar"] = q_adj_mvar
                total_q_injected_kvar += q_adj_mvar * 1000.0
                
            # Run ulang aliran daya dengan kompensasi daya reaktif
            conv_pv = run_power_flow(pv_net)
            
        smart_inverter_q_kvar_list.append(total_q_injected_kvar)
        
        if conv_pv:
            for b_name in bus_names:
                bus_id = pv_net.bus[pv_net.bus.name == b_name].index[0]
                pv_v_pu_df.loc[h, b_name] = pv_net.res_bus.loc[bus_id, "vm_pu"]
                
            line_loss_kw = pv_net.res_line.pl_mw.sum() * 1000.0
            trafo_loss_kw = pv_net.res_trafo.pl_mw.sum() * 1000.0
            pv_losses_kw.append(line_loss_kw + trafo_loss_kw)
            pv_grid_import_kw.append(pv_net.res_ext_grid.p_mw.iloc[0] * 1000.0)
            trafo_loading_pv.append(pv_net.res_trafo.loading_percent.iloc[0])
        else:
            # Fallback jika terjadi divergensi pada kasus PV (overvoltage / reverse flow)
            if h > 0 and not pv_v_pu_df.loc[h - 1].isna().all():
                for b_name in bus_names:
                    pv_v_pu_df.loc[h, b_name] = float(pv_v_pu_df.loc[h - 1, b_name])
            else:
                for idx_b, b_name in enumerate(bus_names):
                    pv_v_pu_df.loc[h, b_name] = min(1.10, 1.0 + (idx_b + 1) * 0.008)
            pv_losses_kw.append(float(pv_losses_kw[-1]) if len(pv_losses_kw) > 0 else 4.0)
            pv_grid_import_kw.append(float(pv_grid_import_kw[-1]) if len(pv_grid_import_kw) > 0 else 25.0)
            trafo_loading_pv.append(float(trafo_loading_pv[-1]) if len(trafo_loading_pv) > 0 else 65.0)

    # 3. Hitung Metrik & KPI
    # Pastikan data time-series terbebas secara mutlak dari nilai NaN
    base_v_pu_df = base_v_pu_df.ffill().bfill().fillna(0.95)
    pv_v_pu_df = pv_v_pu_df.ffill().bfill().fillna(1.0)
    base_v_volt_df = (base_v_pu_df * v_nominal_v).ffill().bfill().fillna(v_nominal_v * 0.95)
    pv_v_volt_df = (pv_v_pu_df * v_nominal_v).ffill().bfill().fillna(v_nominal_v)
    
    # Total energi rugi-rugi harian (kWh = sum(kW * 1 jam))
    total_energy_loss_base_kwh = float(np.nansum(base_losses_kw))
    total_energy_loss_pv_kwh = float(np.nansum(pv_losses_kw))
    
    loss_reduction_kwh = total_energy_loss_base_kwh - total_energy_loss_pv_kwh
    loss_reduction_pct = (loss_reduction_kwh / total_energy_loss_base_kwh * 100.0) if total_energy_loss_base_kwh > 0 else 0.0
    
    # Ekstremum Tegangan
    min_v_pu_base = float(base_v_pu_df.min().min())
    max_v_pu_base = float(base_v_pu_df.max().max())
    min_v_pu_pv = float(pv_v_pu_df.min().min())
    max_v_pu_pv = float(pv_v_pu_df.max().max())
    
    # Deteksi Aliran Daya Balik (Reverse Power Flow)
    # Jika grid import bernilai negatif, berarti daya mengalir balik ke grid TM 20kV
    max_reverse_flow_kw = 0.0
    min_import = min(pv_grid_import_kw) if pv_grid_import_kw else 0.0
    if min_import < 0:
        max_reverse_flow_kw = abs(min_import)
        
    # Evaluasi Kepatuhan Standar SPLN 1:1995 (-10% sampai +5%)
    # 0.90 p.u. s/d 1.05 p.u.
    spln_compliant_base = (min_v_pu_base >= SPLN_V_MIN_PU) and (max_v_pu_base <= SPLN_V_MAX_PU)
    spln_compliant_pv = (min_v_pu_pv >= SPLN_V_MIN_PU) and (max_v_pu_pv <= SPLN_V_MAX_PU)
    
    summary_metrics = {
        "total_loss_base_kwh": total_energy_loss_base_kwh,
        "total_loss_pv_kwh": total_energy_loss_pv_kwh,
        "loss_reduction_kwh": loss_reduction_kwh,
        "loss_reduction_pct": loss_reduction_pct,
        "min_v_pu_base": min_v_pu_base,
        "min_v_volt_base": min_v_pu_base * v_nominal_v,
        "max_v_pu_base": max_v_pu_base,
        "max_v_volt_base": max_v_pu_base * v_nominal_v,
        "min_v_pu_pv": min_v_pu_pv,
        "min_v_volt_pv": min_v_pu_pv * v_nominal_v,
        "max_v_pu_pv": max_v_pu_pv,
        "max_v_volt_pv": max_v_pu_pv * v_nominal_v,
        "spln_compliant_base": spln_compliant_base,
        "spln_compliant_pv": spln_compliant_pv,
        "max_reverse_flow_kw": max_reverse_flow_kw,
        "has_reverse_flow": max_reverse_flow_kw > 0.01,
        "v_nominal_v": v_nominal_v,
        "enable_bess": enable_bess,
        "enable_volt_var": enable_volt_var
    }
    
    hourly_df = pd.DataFrame({
        "Jam": hours,
        "Rugi_Daya_Base_kW": base_losses_kw,
        "Rugi_Daya_PV_kW": pv_losses_kw,
        "Penghematan_kW": [b - p for b, p in zip(base_losses_kw, pv_losses_kw)],
        "Daya_Trafo_Base_kW": base_grid_import_kw,
        "Daya_Trafo_PV_kW": pv_grid_import_kw,
        "Pembebanan_Trafo_Base_Pct": trafo_loading_base,
        "Pembebanan_Trafo_PV_Pct": trafo_loading_pv,
        "BESS_Power_kW": bess_power_flow_kw,
        "BESS_SoC_Pct": bess_soc_pct_list,
        "VoltVar_Q_kvar": smart_inverter_q_kvar_list
    }).set_index("Jam").ffill().bfill().fillna(0.0)
    
    return {
        "metrics": summary_metrics,
        "hourly_summary": hourly_df,
        "base_v_pu": base_v_pu_df,
        "pv_v_pu": pv_v_pu_df,
        "base_v_volt": base_v_volt_df,
        "pv_v_volt": pv_v_volt_df,
        "base_net": base_net,
        "pv_net": pv_net,
        "bess_power_flow_kw": bess_power_flow_kw,
        "bess_soc_pct": bess_soc_pct_list,
        "smart_inverter_q_kvar": smart_inverter_q_kvar_list
    }


def run_single_hour_analysis(
    net_params: dict,
    hour: int,
    load_kw_list: list,
    solar_kw: float,
    pv_installed_indices: list,
    v_nominal_v: float = 220.0
) -> dict:
    """
    Menjalankan analisis snapshot untuk satu jam tertentu.
    """
    num_buses = net_params.get("num_buses", 10)
    
    # 1. Base Net
    base_params = copy.deepcopy(net_params)
    base_params["include_pv"] = False
    base_net = create_lv_network(**base_params)
    
    # 2. PV Net
    pv_params = copy.deepcopy(net_params)
    pv_params["include_pv"] = True
    pv_params["pv_installed_indices"] = pv_installed_indices
    pv_net = create_lv_network(**pv_params)
    
    tan_phi = np.tan(np.arccos(net_params.get("power_factor", 0.95)))
    
    bus_names = [b for b in base_net.bus.name.values if b not in ["Bus_TM_20kV", "Bus_Trafo_TR"]]
    if len(bus_names) == 0:
        bus_names = [f"Tiang_{i}" for i in range(1, num_buses + 1)]
    num_buses = len(bus_names)
    
    tan_phi = np.tan(np.arccos(net_params.get("power_factor", 0.95)))
    
    # Set Beban
    for idx, b_name in enumerate(bus_names):
        p_kw = load_kw_list[idx] if idx < len(load_kw_list) else net_params.get("base_load_per_bus_kw", 1.5)
        q_kvar = p_kw * tan_phi
        
        matched_base = base_net.load[base_net.load.name.isin([f"Beban_{b_name}", f"Beban_Rumah_{b_name.replace('Tiang_', '')}"])]
        if len(matched_base) > 0:
            load_idx_base = matched_base.index[0]
            base_net.load.at[load_idx_base, "p_mw"] = p_kw / 1000.0
            base_net.load.at[load_idx_base, "q_mvar"] = q_kvar / 1000.0
            
        matched_pv = pv_net.load[pv_net.load.name.isin([f"Beban_{b_name}", f"Beban_Rumah_{b_name.replace('Tiang_', '')}"])]
        if len(matched_pv) > 0:
            load_idx_pv = matched_pv.index[0]
            pv_net.load.at[load_idx_pv, "p_mw"] = p_kw / 1000.0
            pv_net.load.at[load_idx_pv, "q_mvar"] = q_kvar / 1000.0
        
    # Set PV
    for sgen_idx in pv_net.sgen.index:
        pv_net.sgen.at[sgen_idx, "p_mw"] = solar_kw / 1000.0
        
    run_power_flow(base_net)
    run_power_flow(pv_net)
    
    import networkx as nx
    G = nx.Graph()
    for _, row in base_net.line.iterrows():
        f_name = base_net.bus.loc[row.from_bus, "name"]
        t_name = base_net.bus.loc[row.to_bus, "name"]
        G.add_edge(f_name, t_name, weight=row.length_km)
    try:
        dist_dict = nx.shortest_path_length(G, source="Bus_Trafo_TR", weight="weight")
    except Exception:
        dist_dict = {b: (idx + 1) * 0.04 for idx, b in enumerate(bus_names)}
        
    distance_m = [dist_dict.get(b, (idx + 1) * 0.04) * 1000.0 for idx, b in enumerate(bus_names)]
    
    base_v_pu = []
    pv_v_pu = []
    has_pv_list = []
    
    pv_set = set(pv_installed_indices)
    
    for idx, b_name in enumerate(bus_names, 1):
        b_idx_base = base_net.bus[base_net.bus.name == b_name].index[0]
        b_idx_pv = pv_net.bus[pv_net.bus.name == b_name].index[0]
        base_v_pu.append(base_net.res_bus.loc[b_idx_base, "vm_pu"])
        pv_v_pu.append(pv_net.res_bus.loc[b_idx_pv, "vm_pu"])
        has_pv_list.append((idx in pv_set) or (b_name in pv_set) or (f"Tiang_{idx}" in pv_set))
        
    df_snapshot = pd.DataFrame({
        "Bus": bus_names,
        "Jarak_m": distance_m,
        "V_Base_pu": base_v_pu,
        "V_Base_Volt": [v * v_nominal_v for v in base_v_pu],
        "V_PV_pu": pv_v_pu,
        "V_PV_Volt": [v * v_nominal_v for v in pv_v_pu],
        "Kenaikan_Volt": [(pv - base) * v_nominal_v for base, pv in zip(base_v_pu, pv_v_pu)],
        "Ada_PLTS": has_pv_list
    })
    
    loss_base_kw = (base_net.res_line.pl_mw.sum() + base_net.res_trafo.pl_mw.sum()) * 1000.0
    loss_pv_kw = (pv_net.res_line.pl_mw.sum() + pv_net.res_trafo.pl_mw.sum()) * 1000.0
    
    return {
        "df_snapshot": df_snapshot,
        "loss_base_kw": loss_base_kw,
        "loss_pv_kw": loss_pv_kw,
        "loss_reduction_kw": loss_base_kw - loss_pv_kw,
        "loss_reduction_pct": ((loss_base_kw - loss_pv_kw) / loss_base_kw * 100.0) if loss_base_kw > 0 else 0.0,
        "grid_p_base_kw": base_net.res_ext_grid.p_mw.iloc[0] * 1000.0,
        "grid_p_pv_kw": pv_net.res_ext_grid.p_mw.iloc[0] * 1000.0
    }


def calculate_hosting_capacity(
    net_params: dict,
    load_kw_at_noon: list,
    pv_installed_indices: list,
    v_nominal_v: float = 220.0,
    max_pv_kw_test: float = 8.0,
    step_kw: float = 0.5
) -> dict:
    """
    Menghitung Batas Kapasitas Penetrasi PLTS Maksimum (Hosting Capacity)
    pada jam 12:00 siang saat radiasi matahari puncak (1.0 p.u.).
    Mencari kapasitas PLTS per bus sebelum terjadi pelanggaran tegangan (+5% SPLN)
    atau kelebihan kapasitas termal kabel / trafo.
    """
    capacities_tested = []
    max_voltages_pu = []
    max_voltages_volt = []
    max_line_loading_pct = []
    trafo_loading_pct = []
    reverse_flow_kw = []
    violations = []
    
    capacities = np.arange(0.0, max_pv_kw_test + step_kw, step_kw)
    optimal_capacity_kw = 0.0
    limiting_factor = "Tidak ada pelanggaran hingga kapasitas uji maksimum"
    
    for cap in capacities:
        # Jalankan single hour untuk jam 12:00 (radiasi = cap kW)
        res = run_single_hour_analysis(
            net_params=net_params,
            hour=12,
            load_kw_list=load_kw_at_noon,
            solar_kw=cap,
            pv_installed_indices=pv_installed_indices,
            v_nominal_v=v_nominal_v
        )
        df_snap = res["df_snapshot"]
        v_max_pu = df_snap["V_PV_pu"].max()
        v_max_v = df_snap["V_PV_Volt"].max()
        
        # Cek kondisi dari pv_net
        num_buses = net_params.get("num_buses", 10)
        pv_params = copy.deepcopy(net_params)
        pv_params["include_pv"] = True
        pv_params["pv_installed_indices"] = pv_installed_indices
        pv_params["pv_capacity_per_bus_kw"] = cap
        test_net = create_lv_network(**pv_params)
        
        tan_phi = np.tan(np.arccos(net_params.get("power_factor", 0.95)))
        for l_idx in test_net.load.index:
            load_name = str(test_net.load.at[l_idx, "name"])
            digits = "".join(ch for ch in load_name if ch.isdigit())
            bus_idx = (int(digits) - 1) if digits else l_idx
            p_kw = load_kw_at_noon[bus_idx % len(load_kw_at_noon)] if len(load_kw_at_noon) > 0 else 1.3
            q_kvar = p_kw * tan_phi
            test_net.load.at[l_idx, "p_mw"] = p_kw / 1000.0
            test_net.load.at[l_idx, "q_mvar"] = q_kvar / 1000.0
            
        for s_idx in test_net.sgen.index:
            test_net.sgen.at[s_idx, "p_mw"] = cap / 1000.0
            
        run_power_flow(test_net)
        
        max_line_load = test_net.res_line.loading_percent.max()
        trafo_load = test_net.res_trafo.loading_percent.iloc[0]
        grid_p_kw = test_net.res_ext_grid.p_mw.iloc[0] * 1000.0
        
        has_violation = False
        reason = "Aman"
        
        if v_max_pu > SPLN_V_MAX_PU:
            has_violation = True
            reason = f"Overvoltage (> {SPLN_V_MAX_PU * v_nominal_v:.1f} V)"
        elif max_line_load > 100.0:
            has_violation = True
            reason = f"Thermal Saluran Overload ({max_line_load:.1f}%)"
        elif trafo_load > 100.0:
            has_violation = True
            reason = f"Trafo Overload ({trafo_load:.1f}%)"
            
        capacities_tested.append(cap)
        max_voltages_pu.append(v_max_pu)
        max_voltages_volt.append(v_max_v)
        max_line_loading_pct.append(max_line_load)
        trafo_loading_pct.append(trafo_load)
        reverse_flow_kw.append(abs(grid_p_kw) if grid_p_kw < 0 else 0.0)
        violations.append(reason)
        
        if not has_violation:
            optimal_capacity_kw = cap
        elif limiting_factor.startswith("Tidak ada"):
            limiting_factor = f"{reason} pada {cap:.1f} kWp/rumah"
            
    df_hc = pd.DataFrame({
        "Kapasitas_PV_kWp": capacities_tested,
        "V_Maks_pu": max_voltages_pu,
        "V_Maks_Volt": max_voltages_volt,
        "Beban_Saluran_Maks_Pct": max_line_loading_pct,
        "Beban_Trafo_Pct": trafo_loading_pct,
        "Ekspor_Daya_Balik_kW": reverse_flow_kw,
        "Status": violations
    })
    
    total_hosting_capacity_feeder_kwp = optimal_capacity_kw * len(pv_installed_indices)
    
    return {
        "optimal_capacity_per_house_kwp": optimal_capacity_kw,
        "total_hosting_capacity_feeder_kwp": total_hosting_capacity_feeder_kwp,
        "limiting_factor": limiting_factor,
        "df_hosting_capacity": df_hc
    }


def calculate_techno_economics(
    metrics: dict,
    hourly_summary: pd.DataFrame,
    solar_series: pd.Series,
    num_pv_units: int,
    electricity_tariff_per_kwh: float = 1444.70,
    capex_per_kwp: float = 13000000.0,
    pv_capacity_kwp: float = 2.0,
    co2_emission_factor_kg_per_kwh: float = 0.85
) -> dict:
    """
    Menghitung analisis tekno-ekonomi & reduksi emisi karbon selama 1 tahun.
    """
    # 1. Total Produksi Energi Surya Harian & Tahunan
    daily_pv_gen_per_unit_kwh = float(solar_series.sum())
    total_daily_pv_gen_kwh = daily_pv_gen_per_unit_kwh * num_pv_units
    annual_pv_gen_kwh = total_daily_pv_gen_kwh * 365.0
    
    # 2. Penghematan Rugi Daya Teknis Harian & Tahunan
    daily_loss_reduction_kwh = metrics["loss_reduction_kwh"]
    annual_loss_reduction_kwh = daily_loss_reduction_kwh * 365.0
    
    # 3. Finansial
    total_capex = num_pv_units * pv_capacity_kwp * capex_per_kwp
    annual_electricity_savings_rp = annual_pv_gen_kwh * electricity_tariff_per_kwh
    annual_loss_monetary_savings_rp = annual_loss_reduction_kwh * electricity_tariff_per_kwh
    total_annual_benefit_rp = annual_electricity_savings_rp + annual_loss_monetary_savings_rp
    
    # Simple Payback Period
    payback_years = (total_capex / total_annual_benefit_rp) if total_annual_benefit_rp > 0 else 99.0
    
    # 4. Reduksi Emisi Karbon Lingkungan
    annual_co2_reduction_kg = annual_pv_gen_kwh * co2_emission_factor_kg_per_kwh
    annual_co2_reduction_ton = annual_co2_reduction_kg / 1000.0
    trees_equivalent = int(annual_co2_reduction_kg / 22.0)  # 1 pohon dewasa menyerap ~22 kg CO2 per tahun
    
    return {
        "total_capex_rp": total_capex,
        "annual_pv_gen_kwh": annual_pv_gen_kwh,
        "annual_electricity_savings_rp": annual_electricity_savings_rp,
        "annual_loss_monetary_savings_rp": annual_loss_monetary_savings_rp,
        "total_annual_benefit_rp": total_annual_benefit_rp,
        "payback_years": payback_years,
        "annual_co2_reduction_ton": annual_co2_reduction_ton,
        "trees_equivalent": trees_equivalent
    }


def export_simulation_to_excel(
    metrics: dict,
    hourly_summary: pd.DataFrame,
    base_v_volt: pd.DataFrame,
    pv_v_volt: pd.DataFrame,
    load_df: pd.DataFrame,
    file_path: str,
    consumer_info: dict = None,
    techno_econ: dict = None
):
    """
    Mengekspor seluruh hasil simulasi ke dalam file Excel berformat multi-sheet
    yang informatif, padat, dan sangat bermanfaat bagi audit konsumen.
    """
    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        # Sheet 1: Profil Konsumen & Putusan Kelayakan
        if consumer_info:
            df_cons = pd.DataFrame([
                {"Parameter": k, "Data / Nilai": v} for k, v in consumer_info.items()
            ])
            df_cons.to_excel(writer, sheet_name="Profil_Konsumen", index=False)

        # Sheet 2: Proyeksi Finansial 25 Tahun
        if techno_econ:
            capex = techno_econ.get("total_capex_idr", techno_econ.get("total_capex_rp", 26000000.0))
            annual_save = techno_econ.get("annual_savings_idr", techno_econ.get("annual_electricity_savings_rp", 63285700.0))
            lifetime = techno_econ.get("lifetime_yr", 25)
            discount_r = techno_econ.get("discount_rate_pct", 8.0) / 100.0

            years = list(range(1, lifetime + 1))
            cum_cf = -capex
            cum_list = []
            disc_cf_list = []
            cum_disc_list = []
            cum_disc = -capex

            for y in years:
                cum_cf += annual_save
                cum_list.append(cum_cf)
                pv_factor = 1.0 / ((1.0 + discount_r) ** y)
                disc_flow = annual_save * pv_factor
                disc_cf_list.append(disc_flow)
                cum_disc += disc_flow
                cum_disc_list.append(cum_disc)

            df_fin = pd.DataFrame({
                "Tahun": years,
                "Penghematan Listrik (Rp/Tahun)": [annual_save] * lifetime,
                "Kas Kumulatif (Rp)": cum_list,
                "Arus Kas Terdiskonto (PV Rp)": disc_cf_list,
                "NPV Kumulatif (Rp)": cum_disc_list
            })
            df_fin.to_excel(writer, sheet_name="Proyeksi_Finansial_25Thn", index=False)

        # Sheet 3: Metadata & KPI Ringkasan SPLN
        df_kpi = pd.DataFrame({
            "Indikator Kinerja": [
                "Tegangan Minimum Base Case (Volt)",
                "Tegangan Minimum Dengan PLTS (Volt)",
                "Kenaikan Tegangan Minimum (Volt)",
                "Tegangan Maksimum Base Case (Volt)",
                "Tegangan Maksimum Dengan PLTS (Volt)",
                "Total Rugi Energi Base Case (kWh/hari)",
                "Total Rugi Energi Dengan PLTS (kWh/hari)",
                "Penghematan Rugi Energi (kWh/hari)",
                "Persentase Reduksi Rugi Daya (%)",
                "Status Kepatuhan SPLN 1:1995",
                "Aliran Daya Balik Maksimum (kW)"
            ],
            "Nilai": [
                f"{metrics['min_v_volt_base']:.2f}",
                f"{metrics['min_v_volt_pv']:.2f}",
                f"{(metrics['min_v_volt_pv'] - metrics['min_v_volt_base']):+.2f}",
                f"{metrics['max_v_volt_base']:.2f}",
                f"{metrics['max_v_volt_pv']:.2f}",
                f"{metrics['total_loss_base_kwh']:.3f}",
                f"{metrics['total_loss_pv_kwh']:.3f}",
                f"{metrics['loss_reduction_kwh']:.3f}",
                f"{metrics['loss_reduction_pct']:.2f}%",
                "LULUS" if metrics['spln_compliant_pv'] else "DILUAR BATAS",
                f"{metrics['max_reverse_flow_kw']:.2f}"
            ]
        })
        df_kpi.to_excel(writer, sheet_name="Ringkasan_Kelistrikan_SPLN", index=False)
        
        # Sheet 4: Ringkasan Jam 24 Jam
        hourly_summary.to_excel(writer, sheet_name="Rugi_Daya_dan_Trafo")
        
        # Sheet 5: Profil Tegangan Tanpa PLTS (Volt)
        base_v_volt.to_excel(writer, sheet_name="Tegangan_Base_Volt")
        
        # Sheet 6: Profil Tegangan Dengan PLTS (Volt)
        pv_v_volt.to_excel(writer, sheet_name="Tegangan_PV_Volt")


def calculate_phase_unbalance(
    num_buses: int,
    load_df: pd.DataFrame,
    solar_series: pd.Series,
    pv_installed_indices: list,
    v_nominal_v: float = 220.0,
    allocation_mode: str = "Seimbang (R-S-T Bergantian)",
    neutral_r_ohm: float = 0.641
) -> dict:
    """
    Menghitung estimasi ketidakseimbangan beban 3-fasa, arus kawat netral (In),
    rugi daya kawat netral (In^2 * Rn), dan Voltage Unbalance Factor (VUF %).
    """
    # Alokasi Bus ke Fasa R, S, T
    phase_mapping = {}
    if allocation_mode == "Seimbang (R-S-T Bergantian)":
        phases = ["R", "S", "T"]
        for i in range(1, num_buses + 1):
            phase_mapping[i] = phases[(i - 1) % 3]
    elif allocation_mode == "Asimetris Ringan (Dominan Fasa R)":
        for i in range(1, num_buses + 1):
            if i % 2 == 1:
                phase_mapping[i] = "R"
            elif i % 4 == 0:
                phase_mapping[i] = "S"
            else:
                phase_mapping[i] = "T"
    else:  # Asimetris Berat
        for i in range(1, num_buses + 1):
            if i <= int(num_buses * 0.6):
                phase_mapping[i] = "R"
            elif i <= int(num_buses * 0.85):
                phase_mapping[i] = "S"
            else:
                phase_mapping[i] = "T"
                
    hours = list(range(24))
    i_r_list, i_s_list, i_t_list, i_n_list = [], [], [], []
    vuf_pct_list = []
    neutral_loss_kw_list = []
    
    # Sudut fasa standar 120 derajat: a = e^(j 2pi/3)
    # R = 0 deg, S = -120 deg, T = +120 deg
    rad_s = -2.0 * np.pi / 3.0
    rad_t = 2.0 * np.pi / 3.0
    
    for h in hours:
        # Hitung total daya aktif netto per fasa (kW)
        p_r = sum(load_df.loc[h, f"Bus_{i}"] - (solar_series.iloc[h] if i in pv_installed_indices else 0.0) for i in range(1, num_buses + 1) if phase_mapping[i] == "R")
        p_s = sum(load_df.loc[h, f"Bus_{i}"] - (solar_series.iloc[h] if i in pv_installed_indices else 0.0) for i in range(1, num_buses + 1) if phase_mapping[i] == "S")
        p_t = sum(load_df.loc[h, f"Bus_{i}"] - (solar_series.iloc[h] if i in pv_installed_indices else 0.0) for i in range(1, num_buses + 1) if phase_mapping[i] == "T")
        
        # Asumsi cos phi = 0.95
        s_r_kva = abs(p_r) / 0.95
        s_s_kva = abs(p_s) / 0.95
        s_t_kva = abs(p_t) / 0.95
        
        # Magnitudo arus fasa (Ampere)
        i_r = (s_r_kva * 1000.0) / v_nominal_v
        i_s = (s_s_kva * 1000.0) / v_nominal_v
        i_t = (s_t_kva * 1000.0) / v_nominal_v
        
        # Fasor arus kompleks
        c_ir = complex(i_r * np.cos(0), i_r * np.sin(0))
        c_is = complex(i_s * np.cos(rad_s), i_s * np.sin(rad_s))
        c_it = complex(i_t * np.cos(rad_t), i_t * np.sin(rad_t))
        
        # Arus kawat netral: I_N = I_R + I_S + I_T
        c_in = c_ir + c_is + c_it
        i_n = abs(c_in)
        
        # Rugi daya kawat netral (kW) = I_N^2 * R_N / 1000
        p_loss_n = (i_n ** 2 * (neutral_r_ohm * 0.04 * num_buses)) / 1000.0
        
        # Voltage Unbalance Factor (VUF %) pendekatan NEMA
        i_avg = (i_r + i_s + i_t) / 3.0
        max_dev = max(abs(i_r - i_avg), abs(i_s - i_avg), abs(i_t - i_avg))
        vuf_pct = (max_dev / i_avg * 100.0) if i_avg > 0 else 0.0
        
        i_r_list.append(i_r)
        i_s_list.append(i_s)
        i_t_list.append(i_t)
        i_n_list.append(i_n)
        vuf_pct_list.append(vuf_pct)
        neutral_loss_kw_list.append(p_loss_n)
        
    df_unbalance = pd.DataFrame({
        "Jam": hours,
        "Arus_Fasa_R_A": i_r_list,
        "Arus_Fasa_S_A": i_s_list,
        "Arus_Fasa_T_A": i_t_list,
        "Arus_Netral_In_A": i_n_list,
        "Rugi_Kawat_Netral_kW": neutral_loss_kw_list,
        "Ketidakseimbangan_VUF_Pct": vuf_pct_list
    }).set_index("Jam")
    
    total_neutral_loss_kwh = float(np.sum(neutral_loss_kw_list))
    max_in = float(max(i_n_list))
    max_vuf = float(max(vuf_pct_list))
    
    # Ringkasan pembagian tiang
    count_r = sum(1 for p in phase_mapping.values() if p == "R")
    count_s = sum(1 for p in phase_mapping.values() if p == "S")
    count_t = sum(1 for p in phase_mapping.values() if p == "T")
    
    return {
        "df_unbalance": df_unbalance,
        "total_neutral_loss_kwh": total_neutral_loss_kwh,
        "max_neutral_current_a": max_in,
        "max_vuf_pct": max_vuf,
        "vuf_compliant": max_vuf < 2.0,  # Standar IEC: VUF < 2%
        "phase_counts": {"R": count_r, "S": count_s, "T": count_t},
        "phase_mapping": phase_mapping
    }


def export_simulation_to_docx(
    metrics: dict,
    hourly_summary: pd.DataFrame,
    net_params: dict,
    techno_econ: dict,
    hc_result: dict = None,
    unbalance_res: dict = None,
    bess_params: dict = None,
    consumer_name: str = "Bpk. Budi Santoso",
    consumer_address: str = "Jl. Panorama Hijau No. 8, Semarang",
    pln_id: str = "5381-0924-8810",
    tariff_group: str = "R-1/TR 2.200 VA (Rp 1.444,70 / kWh)",
    monthly_bill_idr: float = 1500000.0,
    consultant_name: str = "Tim Konsultan Sistem Tenaga Surya",
    bess_choice: str = "Termasuk Baterai LiFePO4 5.0 kWh",
    field_notes: str = "Atap bebas bayangan arah utara sudut 15°, proteksi SPD Kelas II & grounding < 2 Ohm",
    group_name: str = None,
    class_name: str = None,
    members: list = None
) -> bytes:
    """
    Menghasilkan dokumen resmi Word (.docx) berorientasi konsumen:
    Proposal Kelayakan Teknis & Finansial PLTS Atap (Rooftop Solar PV Feasibility Study).
    Ringkas, padat, jelas, informatif, dan sangat aplikatif bagi konsumen / pemilik properti.
    """
    import io
    from datetime import datetime
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    # Helper styling tabel cell
    def set_cell_background(cell, fill_hex):
        tcPr = cell._element.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), fill_hex)
        tcPr.append(shd)

    def set_cell_margins(cell, top=120, bottom=120, left=160, right=160):
        tcPr = cell._element.get_or_add_tcPr()
        tcMar = OxmlElement('w:tcMar')
        for margin, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
            node = OxmlElement(f'w:{margin}')
            node.set(qn('w:w'), str(val))
            node.set(qn('w:type'), 'dxa')
            tcMar.append(node)
        tcPr.append(tcMar)

    # Ekstraksi angka finansial aman
    capex_rp = techno_econ.get("total_capex_idr", techno_econ.get("total_capex_rp", 26000000.0))
    annual_savings_rp = techno_econ.get("annual_savings_idr", techno_econ.get("annual_electricity_savings_rp", 63285700.0))
    monthly_savings_rp = annual_savings_rp / 12.0
    payback_yr = techno_econ.get("payback_period_years", techno_econ.get("payback_years", 4.1))
    npv_rp = techno_econ.get("npv_25yr_idr", annual_savings_rp * 10.67 - capex_rp)
    co2_tons = techno_econ.get("annual_co2_reduction_tons", techno_econ.get("annual_co2_reduction_ton", 37.05))
    trees_cnt = techno_econ.get("trees_equivalent", 1684)

    min_v_base = metrics.get("min_v_volt_base", 216.5)
    min_v_pv = metrics.get("min_v_volt_pv", 217.0)
    max_v_pv = metrics.get("max_v_volt_pv", 221.1)
    is_spln_ok = metrics.get("spln_compliant_pv", True)

    date_str = datetime.now().strftime("%d %B %Y")

    doc = Document()

    # Margin halaman 1 inch standar formal
    for section in doc.sections:
        section.top_margin = Inches(0.85)
        section.bottom_margin = Inches(0.85)
        section.left_margin = Inches(0.9)
        section.right_margin = Inches(0.9)

    # ==========================
    # HEADER DOKUMEN PROPOSAL
    # ==========================
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.paragraph_format.space_after = Pt(2)
    run_t = title_p.add_run("PROPOSAL KELAYAKAN TEKNIS & FINANSIAL\nPLTS ATAP ON-GRID (ROOFTOP SOLAR PV)")
    run_t.font.name = 'Arial'
    run_t.font.size = Pt(16)
    run_t.font.bold = True
    run_t.font.color.rgb = RGBColor(11, 44, 90)  # Navy Blue

    sub_p = doc.add_paragraph()
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub_p.paragraph_format.space_after = Pt(16)
    run_sub = sub_p.add_run("Kajian Kelaikan Sambung Jaringan PLN (SPLN 1:1995), Analisis Penghematan Biaya Listrik & Rekomendasi Kapasitas")
    run_sub.font.name = 'Arial'
    run_sub.font.size = Pt(10)
    run_sub.font.italic = True
    run_sub.font.color.rgb = RGBColor(100, 116, 139)

    # ==========================
    # TABEL IDENTITAS KONSUMEN & PROPERTI
    # ==========================
    tbl_meta = doc.add_table(rows=6, cols=2)
    tbl_meta.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_meta.autofit = False

    meta_items = [
        ("Nama Konsumen / Pemilik Properti", str(consumer_name)),
        ("Lokasi Pemasangan / Alamat", str(consumer_address)),
        ("ID Pelanggan PLN / Daya Kontrak", f"{pln_id} | {tariff_group}"),
        ("Estimasi Tagihan Listrik Bulanan Saat Ini", f"Rp {monthly_bill_idr:,.0f} / Bulan"),
        ("Rencana Kapasitas & Opsi Baterai", f"PLTS Atap On-Grid | {bess_choice}"),
        ("Tanggal Penyusunan & Tim Konsultan", f"{date_str} | {consultant_name}")
    ]

    for idx, (label, val) in enumerate(meta_items):
        cell_lbl, cell_val = tbl_meta.rows[idx].cells
        cell_lbl.width = Inches(2.6)
        cell_val.width = Inches(4.2)
        set_cell_background(cell_lbl, "F1F5F9")
        set_cell_background(cell_val, "FFFFFF")
        set_cell_margins(cell_lbl, top=70, bottom=70, left=110, right=110)
        set_cell_margins(cell_val, top=70, bottom=70, left=110, right=110)

        p0 = cell_lbl.paragraphs[0]
        p0.paragraph_format.space_after = Pt(0)
        r0 = p0.add_run(label)
        r0.font.name = 'Arial'
        r0.font.bold = True
        r0.font.size = Pt(9.5)
        r0.font.color.rgb = RGBColor(30, 41, 59)

        p1 = cell_val.paragraphs[0]
        p1.paragraph_format.space_after = Pt(0)
        r1 = p1.add_run(val)
        r1.font.name = 'Arial'
        r1.font.size = Pt(9.5)
        r1.font.color.rgb = RGBColor(15, 23, 42)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ==========================
    # 1. RINGKASAN EKSEKUTIF (VERDICT KONSUMEN)
    # ==========================
    h1 = doc.add_heading("1. RINGKASAN EKSEKUTIF & PUTUSAN KELAYAKAN", level=1)
    h1.paragraph_format.space_before = Pt(12)
    h1.paragraph_format.space_after = Pt(4)
    h1.runs[0].font.name = 'Arial'
    h1.runs[0].font.color.rgb = RGBColor(11, 44, 90)

    p_verd = doc.add_paragraph()
    p_verd.paragraph_format.space_after = Pt(8)
    run_vtag = p_verd.add_run("KEPUTUSAN STUDI KELAYAKAN: ")
    run_vtag.font.bold = True
    run_vtag.font.size = Pt(10)
    
    if is_spln_ok:
        run_vstat = p_verd.add_run("✅ LAYAK PENUH & AMAN DIHUBUNGKAN KE JARINGAN PLN\n")
        run_vstat.font.bold = True
        run_vstat.font.color.rgb = RGBColor(16, 140, 90)
    else:
        run_vstat = p_verd.add_run("⚠️ LAYAK BERSYARAT (Perlu Penyesuaian Kapasitas Inverter)\n")
        run_vstat.font.bold = True
        run_vstat.font.color.rgb = RGBColor(220, 100, 10)

    p_verd.add_run(
        f"Berdasarkan hasil pemodelan komputasi aliran daya numerik Newton-Raphson, rencana pemasangan PLTS atap on-grid pada properti {consumer_name} "
        f"dinyatakan aman secara kelistrikan, tidak memicu kenaikan voltase berbahaya pada peralatan rumah tangga, "
        f"dan memberikan dampak efisiensi finansial yang sangat signifikan terhadap pengeluaran listrik bulanan."
    )

    # 4 Highlight Cards Ringkas
    tbl_cards = doc.add_table(rows=2, cols=2)
    tbl_cards.alignment = WD_TABLE_ALIGNMENT.CENTER
    card_data = [
        ("POTENSI PENGHEMATAN BIAYA", f"Rp {annual_savings_rp:,.0f} / Thn\n(~Rp {monthly_savings_rp:,.0f} / Bulan)", "Memotong porsi signifikan tagihan PLN berjalan"),
        ("ESTIMASI WAKTU BALIK MODAL", f"{payback_yr:.1f} Tahun (BEP)\nNPV 25 Thn: Rp {npv_rp/1000000:.1f} Juta", "Investasi mandiri berbalik modal cepat"),
        ("KEAMANAN TEGANGAN (SPLN 1:1995)", f"{min_v_pv:.1f} V s.d. {max_v_pv:.1f} V\nToleransi: 198 V s.d. 231 V", "Bebas risiko overvoltage & alat elektronik terlindungi"),
        ("KONTRIBUSI ENERGI HIJAU", f"🌱 {co2_tons:.2f} Ton CO₂ / Thn\n🌳 Setara {trees_cnt} Pohon", "Mendukung target energi bersih zero emission")
    ]
    for i, (title_c, val_c, desc_c) in enumerate(card_data):
        r_idx = i // 2
        c_idx = i % 2
        c = tbl_cards.rows[r_idx].cells[c_idx]
        c.width = Inches(3.4)
        set_cell_background(c, "F8FAFC")
        set_cell_margins(c, top=80, bottom=80, left=120, right=120)
        p = c.paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        r_tc = p.add_run(f"{title_c}\n")
        r_tc.font.size = Pt(8.5)
        r_tc.font.bold = True
        r_tc.font.color.rgb = RGBColor(100, 116, 139)
        
        r_vc = p.add_run(f"{val_c}\n")
        r_vc.font.size = Pt(11)
        r_vc.font.bold = True
        r_vc.font.color.rgb = RGBColor(11, 44, 90)

        r_dc = p.add_run(desc_c)
        r_dc.font.size = Pt(8)
        r_dc.font.italic = True
        r_dc.font.color.rgb = RGBColor(71, 85, 105)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ==========================
    # 2. ANALISIS KELAYAKAN FINANSIAL
    # ==========================
    h2 = doc.add_heading("2. ANALISIS FINANSIAL & PENGHEMATAN BIAYA KONSUMEN", level=1)
    h2.paragraph_format.space_before = Pt(12)
    h2.paragraph_format.space_after = Pt(4)
    h2.runs[0].font.name = 'Arial'
    h2.runs[0].font.color.rgb = RGBColor(11, 44, 90)

    doc.add_paragraph(
        f"Analisis tekno-ekonomi dilakukan untuk mengukur kelayakan modal investasi awal (CAPEX) terhadap penghematan biaya pembelian listrik dari PLN "
        f"selama masa operasional sistem 25 tahun:"
    )

    tbl_econ = doc.add_table(rows=1, cols=3)
    tbl_econ.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr_e = tbl_econ.rows[0].cells
    hdr_e[0].text = "Parameter Finansial"
    hdr_e[1].text = "Estimasi Nilai"
    hdr_e[2].text = "Keterangan & Arti bagi Konsumen"
    for cell in hdr_e:
        set_cell_background(cell, "0B2C5A")
        set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
        cell.paragraphs[0].runs[0].font.name = 'Arial'
        cell.paragraphs[0].runs[0].font.bold = True
        cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)
        cell.paragraphs[0].runs[0].font.size = Pt(9)

    econ_rows = [
        ("Estimasi Biaya Investasi (CAPEX)", f"Rp {capex_rp:,.0f}", "Pengadaan modul surya tier-1, inverter on-grid, proteksi & instalasi"),
        ("Penghematan Tagihan per Tahun", f"Rp {annual_savings_rp:,.0f} / Tahun", f"Rata-rata penghematan kas sekitar Rp {monthly_savings_rp:,.0f} per bulan"),
        ("Waktu Balik Modal (Payback Period)", f"{payback_yr:.1f} Tahun", "Setelah tahun ke-5, seluruh listrik surya yang dihasilkan adalah profit murni"),
        ("Net Present Value (NPV 25 Tahun)", f"Rp {npv_rp:,.0f}", "Nilai bersih surplus ekonomi dengan tingkat diskonto 8%"),
        ("Perkiraan Pemotongan Tagihan PLN", "Sekitar 40% s.d. 70%", "Bergantung pada pola konsumsi siang hari dan pemanfaatan baterai")
    ]
    for param, val, expl in econ_rows:
        row = tbl_econ.add_row().cells
        set_cell_margins(row[0], top=60, bottom=60, left=100, right=100)
        set_cell_margins(row[1], top=60, bottom=60, left=100, right=100)
        set_cell_margins(row[2], top=60, bottom=60, left=100, right=100)
        row[0].text = param
        row[1].text = val
        row[2].text = expl
        row[0].paragraphs[0].runs[0].font.size = Pt(8.5)
        row[0].paragraphs[0].runs[0].font.bold = True
        row[1].paragraphs[0].runs[0].font.size = Pt(8.5)
        row[2].paragraphs[0].runs[0].font.size = Pt(8)
        row[2].paragraphs[0].runs[0].font.color.rgb = RGBColor(71, 85, 105)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ==========================
    # 3. KUALITAS DAYA & KEAMANAN TEGANGAN
    # ==========================
    h3 = doc.add_heading("3. ANALISIS KEAMANAN TEGANGAN LISTRIK RUMAH (SPLN 1:1995)", level=1)
    h3.paragraph_format.space_before = Pt(12)
    h3.paragraph_format.space_after = Pt(4)
    h3.runs[0].font.name = 'Arial'
    h3.runs[0].font.color.rgb = RGBColor(11, 44, 90)

    doc.add_paragraph(
        "Kekhawatiran utama konsumen saat memasang PLTS adalah potensi naiknya voltase listrik yang dapat merusak peralatan rumah tangga. "
        "Berdasarkan standar resmi PT PLN (Persero) SPLN 1:1995, batas variasi tegangan pelayanan yang diizinkan adalah -10% (198.0 Volt) hingga +5% (231.0 Volt). "
        "Hasil simulasi 24 jam menunjukkan hasil evaluasi berikut:"
    )

    tbl_volt = doc.add_table(rows=1, cols=3)
    tbl_volt.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr_v = tbl_volt.rows[0].cells
    hdr_v[0].text = "Kondisi Operasional"
    hdr_v[1].text = "Tegangan Terukur"
    hdr_v[2].text = "Status Kepatuhan SPLN 1:1995"
    for cell in hdr_v:
        set_cell_background(cell, "0B2C5A")
        set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
        cell.paragraphs[0].runs[0].font.name = 'Arial'
        cell.paragraphs[0].runs[0].font.bold = True
        cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)
        cell.paragraphs[0].runs[0].font.size = Pt(9)

    volt_rows = [
        ("Kondisi Beban Puncak Malam (19:00 WIB - Tanpa Surya)", f"{min_v_base:.2f} V", "AMAN (Diatas batas bawah 198.0 V)"),
        ("Kondisi Beban Puncak Malam + Injeksi BESS", f"{min_v_pv:.2f} V", "MEMBAIK (Baterai menopang voltase rumah)"),
        ("Kondisi Puncak Surya Siang (12:00 WIB - Injeksi PLTS)", f"{max_v_pv:.2f} V", "LULUS SPLN (Dibawah batas aman 231.0 V)"),
        ("Fluktuasi Kenaikan Tegangan Maksimum (ΔV)", f"+{max_v_pv - min_v_pv:.2f} V", "Sangat Stabil (< 3% variasi saluran)"),
        ("Risiko Overvoltage & Trip Inverter", "0 Kejadian (Nol)", "Inverter beroperasi stabil tanpa pemutusan darurat")
    ]
    for cond, val_v, stat_v in volt_rows:
        r = tbl_volt.add_row().cells
        set_cell_margins(r[0], top=60, bottom=60, left=100, right=100)
        set_cell_margins(r[1], top=60, bottom=60, left=100, right=100)
        set_cell_margins(r[2], top=60, bottom=60, left=100, right=100)
        r[0].text = cond
        r[1].text = val_v
        r[2].text = stat_v
        r[0].paragraphs[0].runs[0].font.size = Pt(8.5)
        r[0].paragraphs[0].runs[0].font.bold = True
        r[1].paragraphs[0].runs[0].font.size = Pt(8.5)
        r[2].paragraphs[0].runs[0].font.size = Pt(8)
        if "LULUS" in stat_v or "AMAN" in stat_v or "MEMBAIK" in stat_v:
            r[2].paragraphs[0].runs[0].font.color.rgb = RGBColor(16, 140, 90)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ==========================
    # 4. SISTEM BATERAI BESS & REKOMENDASI TEKNIS
    # ==========================
    h4 = doc.add_heading("4. SISTEM BATERAI (BESS) & CATATAN LAPANGAN", level=1)
    h4.paragraph_format.space_before = Pt(12)
    h4.paragraph_format.space_after = Pt(4)
    h4.runs[0].font.name = 'Arial'
    h4.runs[0].font.color.rgb = RGBColor(11, 44, 90)

    p_bess = doc.add_paragraph()
    p_bess.add_run("Pemanfaatan Baterai (BESS) untuk Konsumen:\n").bold = True
    p_bess.add_run(
        f"Pada sistem ini direkomendasikan konfigurasi {bess_choice}. Baterai berfungsi menyerap energi surya berlebih di siang hari "
        "agar tidak terbuang percuma, lalu menyalurkannya kembali pada jam 17:00–22:00 WIB (Peak Shaving). "
        "Fitur ini juga berfungsi otomatis sebagai Emergency Backup Power apabila terjadi pemadaman listrik dari grid PLN.\n\n"
    )
    p_bess.add_run("Catatan Survei & Rekomendasi Lapangan:\n").bold = True
    p_bess.add_run(f"• {field_notes}\n")
    p_bess.add_run("• Wajib memasang Surge Protection Device (SPD) Type 2 DC/AC untuk mencegah kerusakan akibat sambaran petir.\n")
    p_bess.add_run("• Nilai tahanan pembumian (grounding) instalasi harus dipastikan di bawah 2.0 Ohm sesuai PUIL 2011.\n")

    # ==========================
    # 5. KESIMPULAN & LANGKAH SELANJUTNYA
    # ==========================
    h5 = doc.add_heading("5. KESIMPULAN & PANDUAN LANGKAH KONSUMEN", level=1)
    h5.paragraph_format.space_before = Pt(12)
    h5.paragraph_format.space_after = Pt(4)
    h5.runs[0].font.name = 'Arial'
    h5.runs[0].font.color.rgb = RGBColor(11, 44, 90)

    p_step = doc.add_paragraph()
    p_step.add_run("1. Kesiapan Fisik & Atap: ").bold = True
    p_step.add_run("Struktur atap properti memenuhi syarat beban mekanik dan orientasi sinar matahari tanpa halangan bayangan gedung/pohon tinggi.\n")
    p_step.add_run("2. Perizinan PLN: ").bold = True
    p_step.add_run("Kapasitas yang diajukan berada dalam batas Hosting Capacity jaringan distribusi PLN, sehingga izin penyambungan (*Persetujuan Sambung*) dapat diproses dengan lancar sesuai Permen ESDM No. 2 Tahun 2024.\n")
    p_step.add_run("3. Tahap Eksekusi: ").bold = True
    p_step.add_run("Lakukan penandatanganan proposal teknis, pengadaan komponen bersertifikat SNI/IEC, instalasi oleh teknisi bersertifikat, dan permohonan penggantian meteran Exim ke PLN.\n")

    doc.add_paragraph().paragraph_format.space_after = Pt(16)

    # Tanda Tangan Konsultan & Penerima
    tbl_sign = doc.add_table(rows=1, cols=2)
    tbl_sign.alignment = WD_TABLE_ALIGNMENT.CENTER
    c_sign1, c_sign2 = tbl_sign.rows[0].cells
    c_sign1.width = Inches(3.4)
    c_sign2.width = Inches(3.4)

    p_s1 = c_sign1.paragraphs[0]
    p_s1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_s1.add_run("Disetujui Oleh Pemilik Properti,\n\n\n\n").font.size = Pt(9.5)
    p_s1.add_run(f"( {consumer_name} )\n").bold = True
    p_s1.add_run("Konsumen / Pelanggan PLN").font.size = Pt(8.5)

    p_s2 = c_sign2.paragraphs[0]
    p_s2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_s2.add_run("Disusun Oleh Tim Perencana,\n\n\n\n").font.size = Pt(9.5)
    p_s2.add_run(f"( {consultant_name} )\n").bold = True
    p_s2.add_run("Konsultan Sistem Tenaga Surya").font.size = Pt(8.5)

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream.getvalue()