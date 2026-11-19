"""
VoltSolar-Sim Pro Enterprise - Backend Server (Flask REST API)
Melayani Antarmuka Web HTML5 Interaktif & Komputasi Sistem Tenaga Listrik
Program Studi: Teknologi Rekayasa Elektro
Praktikum Pemrograman Dasar
"""

import os
import io
import json
import numpy as np
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file

from core.grid_model import create_lv_network, CABLE_TYPES, TRANSFORMER_TYPES
from core.profiles import (
    generate_load_profile,
    generate_solar_profile,
    fetch_bmkg_weather,
    BMKG_CITIES,
    WEATHER_FACTORS
)
from core.simulation import (
    run_time_series_comparison,
    calculate_hosting_capacity,
    calculate_phase_unbalance,
    calculate_techno_economics,
    export_simulation_to_docx,
    export_simulation_to_excel
)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# Helper serializer untuk mengonversi tipe numpy/pandas ke tipe standar Python/JSON
def sanitize_json(data):
    if isinstance(data, dict):
        return {k: sanitize_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_json(v) for v in data]
    elif isinstance(data, (np.integer, np.int64, np.int32)):
        return int(data)
    elif isinstance(data, (np.floating, np.float64, np.float32)):
        return float(data)
    elif isinstance(data, (np.bool_, bool)):
        return bool(data)
    elif isinstance(data, pd.DataFrame):
        return sanitize_json(data.to_dict(orient="split"))
    elif isinstance(data, pd.Series):
        return sanitize_json(data.to_dict())
    return data


@app.route("/")
def index():
    """Halaman Utama Dashboard Web HTML5"""
    return render_template("index.html")


@app.route("/api/initial-config", methods=["GET"])
def get_initial_config():
    """Menyediakan daftar parameter awal untuk UI"""
    default_branches = [
        {"from": "Trafo", "to": "Tiang_1"},
        {"from": "Tiang_1", "to": "Tiang_2"},
        {"from": "Tiang_2", "to": "Tiang_3"},
        {"from": "Tiang_3", "to": "Tiang_4"},
        {"from": "Tiang_4", "to": "Tiang_5"},
        {"from": "Tiang_5", "to": "Tiang_6"},
        {"from": "Tiang_6", "to": "Tiang_7"},
        {"from": "Tiang_7", "to": "Tiang_8"},
        {"from": "Tiang_8", "to": "Tiang_9"},
        {"from": "Tiang_9", "to": "Tiang_10"}
    ]
    return jsonify({
        "status": "success",
        "cables": list(CABLE_TYPES.keys()),
        "transformers": list(TRANSFORMER_TYPES.keys()),
        "weather_presets": list(WEATHER_FACTORS.keys()),
        "bmkg_cities": list(BMKG_CITIES.keys()),
        "default_branches": default_branches
    })


@app.route("/api/bmkg", methods=["GET"])
def get_bmkg_weather():
    """Mengambil data cuaca langsung dari REST API resmi BMKG"""
    city = request.args.get("city", "Jakarta Pusat")
    res = fetch_bmkg_weather(city)
    return jsonify(res)


@app.route("/api/simulate", methods=["POST"])
def run_simulation():
    """Menjalankan aliran daya Newton-Raphson 24 jam & analisis lengkap"""
    try:
        req = request.json or {}
        num_buses = int(req.get("num_buses", 10))
        span_length_m = float(req.get("span_length_m", 40.0))
        cable_type = req.get("cable_type", "LVTC 3x70 + 1x50 mm²")
        transformer_type = req.get("transformer_type", "100 kVA (Dyn5)")
        v_nominal = float(req.get("v_nominal", 220.0))
        base_load_kw = float(req.get("base_load_kw", 1.5))
        cos_phi = float(req.get("cos_phi", 0.95))
        stochastic = bool(req.get("stochastic_load", True))
        
        topology_type = req.get("topology_type", "Linear Radial (Standar)")
        custom_branches = req.get("custom_branches", None)
        
        # Penentuan Bus List
        if topology_type == "Linear Radial (Standar)" or not custom_branches:
            bus_list = [f"Tiang_{i}" for i in range(1, num_buses + 1)]
            active_branches = None
        else:
            active_branches = custom_branches
            all_b = []
            for br in active_branches:
                for b_item in [br["from"], br["to"]]:
                    if b_item not in ["Trafo", "Bus_Trafo_TR"] and b_item not in all_b:
                        all_b.append(b_item)
            bus_list = all_b
            num_buses = len(bus_list)

        # Penetrasi PLTS
        pv_placement = req.get("pv_placement_mode", "Semua Tiang (100% Penetrasi)")
        if pv_placement == "Semua Tiang (100% Penetrasi)":
            pv_installed_buses = list(bus_list)
        elif pv_placement == "Tiang Ujung Saja (50% Terakhir)":
            pv_installed_buses = list(bus_list[len(bus_list)//2:])
        elif pv_placement == "Tiang Tengah Feeder":
            mid = len(bus_list)//2
            pv_installed_buses = list(bus_list[max(0, mid-1):min(len(bus_list), mid+2)])
        elif pv_placement == "Kustom / Pilihan Manual":
            pv_installed_buses = req.get("pv_installed_buses", bus_list[:len(bus_list)//2])
        else:
            pv_installed_buses = list(bus_list[:max(2, len(bus_list)//2)])

        pv_capacity_kw = float(req.get("pv_capacity_kw", 2.0))
        
        # Cuaca: BMKG vs Preset
        weather_mode = req.get("weather_mode", "bmkg")
        bmkg_info = None
        effective_factor = 1.0
        
        if weather_mode == "bmkg":
            city = req.get("weather_city", "Jakarta Pusat")
            bmkg_info = fetch_bmkg_weather(city)
            effective_factor = bmkg_info.get("effective_solar_factor", 0.85)
            solar_series = generate_solar_profile(pv_capacity_kw=pv_capacity_kw, custom_factor=effective_factor)
        else:
            w_cond = req.get("weather_condition", "Cerah Maksimal")
            solar_series = generate_solar_profile(weather_condition=w_cond, pv_capacity_kw=pv_capacity_kw)

        # BESS & Smart Inverter
        enable_bess = bool(req.get("enable_bess", False))
        bess_cap_kwh = float(req.get("bess_cap_kwh", 5.0))
        bess_kw = float(req.get("bess_kw", 2.5))
        enable_volt_var = bool(req.get("enable_volt_var", False))

        # Generator Profil Beban
        load_df = generate_load_profile(
            num_buses=num_buses,
            base_load_kw=base_load_kw,
            random_noise=stochastic,
            noise_level=0.06,
            bus_names=bus_list
        )

        net_params = {
            "num_buses": num_buses,
            "span_length_km": span_length_m / 1000.0,
            "cable_type_name": cable_type,
            "transformer_type_name": transformer_type,
            "base_load_per_bus_kw": base_load_kw,
            "power_factor": cos_phi,
            "custom_branches": active_branches
        }

        # Jalankan Simulasi 24 Jam
        sim_res = run_time_series_comparison(
            net_params=net_params,
            load_df=load_df,
            solar_series=solar_series,
            pv_installed_indices=pv_installed_buses,
            pv_capacity_kw=pv_capacity_kw,
            v_nominal_v=v_nominal,
            enable_bess=enable_bess,
            bess_capacity_kwh=bess_cap_kwh,
            bess_max_kw=bess_kw,
            enable_volt_var=enable_volt_var
        )

        # Analisis Ketidakseimbangan 3-Fasa
        phase_alloc = req.get("phase_allocation_mode", "Seimbang (R-S-T Bergantian)")
        pv_indices = [idx for idx, b in enumerate(bus_list, 1) if b in pv_installed_buses]

        unbalance_res = calculate_phase_unbalance(
            num_buses=num_buses,
            load_df=load_df,
            solar_series=solar_series,
            pv_installed_indices=pv_indices,
            v_nominal_v=v_nominal,
            allocation_mode=phase_alloc
        )
        df_unb = unbalance_res["df_unbalance"]

        # Analisis Tekno-Ekonomi & Emisi
        tariff_pln = float(req.get("tariff_pln", 1444.70))
        capex_kwp = float(req.get("capex_kwp", 13000000.0))
        emission_factor = float(req.get("emission_factor", 0.85))

        techno_econ = calculate_techno_economics(
            metrics=sim_res["metrics"],
            hourly_summary=sim_res["hourly_summary"],
            solar_series=solar_series,
            num_pv_units=len(pv_installed_buses),
            electricity_tariff_per_kwh=tariff_pln,
            capex_per_kwp=capex_kwp,
            pv_capacity_kwp=pv_capacity_kw,
            co2_emission_factor_kg_per_kwh=emission_factor
        )
        # Tambahkan alias kunci agar kompatibel dengan template HTML
        techno_econ["total_capex_idr"] = techno_econ["total_capex_rp"]
        techno_econ["annual_savings_idr"] = techno_econ["total_annual_benefit_rp"]
        techno_econ["payback_period_years"] = techno_econ["payback_years"]
        techno_econ["annual_co2_reduction_tons"] = techno_econ["annual_co2_reduction_ton"]
        
        # Hitung NPV akurat dengan discount rate & lifetime dinamis
        discount_rate = float(req.get("discount_rate", 8.0)) / 100.0
        lifetime_yr = int(req.get("lifetime_yr", 25))
        annuity_factor = sum([1.0 / ((1.0 + discount_rate) ** t) for t in range(1, lifetime_yr + 1)])
        techno_econ["npv_25yr_idr"] = (techno_econ["total_annual_benefit_rp"] * annuity_factor) - techno_econ["total_capex_rp"]
        techno_econ["discount_rate_pct"] = discount_rate * 100.0
        techno_econ["lifetime_yr"] = lifetime_yr
        techno_econ["tariff_pln"] = tariff_pln
        techno_econ["capex_kwp"] = capex_kwp
        techno_econ["emission_factor"] = emission_factor

        # Ekstrak Jarak Bus Fisik menggunakan NetworkX
        import networkx as nx
        G_dist = nx.Graph()
        if active_branches:
            for br in active_branches:
                G_dist.add_edge(br["from"], br["to"], weight=span_length_m)
            try:
                bus_distances_m = nx.shortest_path_length(G_dist, source="Trafo", weight="weight")
            except Exception:
                bus_distances_m = {b: (idx+1)*span_length_m for idx, b in enumerate(bus_list)}
        else:
            bus_distances_m = {f"Tiang_{i}": i * span_length_m for i in range(1, num_buses + 1)}

        # Konversi data matriks tegangan ke list of dict untuk visualisasi grafik JS
        base_v_volt = sim_res["base_v_volt"]
        pv_v_volt = sim_res["pv_v_volt"]
        
        # Format respons JSON yang komprehensif
        response_data = {
            "status": "success",
            "metrics": sim_res["metrics"],
            "bus_list": bus_list,
            "pv_installed_buses": pv_installed_buses,
            "bus_distances_m": bus_distances_m,
            "hourly_summary": sim_res["hourly_summary"].to_dict(orient="records"),
            "base_v_volt": base_v_volt.to_dict(orient="index"),
            "pv_v_volt": pv_v_volt.to_dict(orient="index"),
            "bess_flow": list(sim_res.get("bess_power_flow_kw") if sim_res.get("bess_power_flow_kw") is not None else [0]*24),
            "bess_soc": list(sim_res.get("bess_soc_pct") if sim_res.get("bess_soc_pct") is not None else [50]*24),
            "smart_inverter_q": list(sim_res.get("smart_inverter_q_kvar") if sim_res.get("smart_inverter_q_kvar") is not None else [0]*24),
            "solar_profile": [float(x) for x in solar_series.tolist()],
            "avg_load_curve_kw": [float(load_df.loc[h].mean()) for h in range(24)],
            "total_load_curve_kw": [float(load_df.loc[h].sum()) for h in range(24)],
            "bess_params": {
                "enabled": enable_bess,
                "capacity_kwh": bess_cap_kwh,
                "max_kw": bess_kw,
                "total_capacity_feeder_kwh": bess_cap_kwh * len(pv_installed_buses)
            },
            "unbalance_res": {
                "neutral_current_a": df_unb["Arus_Netral_In_A"].tolist(),
                "i_r_a": df_unb["Arus_Fasa_R_A"].tolist(),
                "i_s_a": df_unb["Arus_Fasa_S_A"].tolist(),
                "i_t_a": df_unb["Arus_Fasa_T_A"].tolist(),
                "unbalance_factor_pct": df_unb["Ketidakseimbangan_VUF_Pct"].tolist(),
                "max_neutral_current_a": unbalance_res["max_neutral_current_a"],
                "max_vuf_pct": unbalance_res["max_vuf_pct"],
                "vuf_compliant": unbalance_res["vuf_compliant"],
                "neutral_loss_kwh": unbalance_res["total_neutral_loss_kwh"]
            },
            "techno_econ": techno_econ,
            "bmkg_info": bmkg_info,
            "active_branches": active_branches if active_branches else [{"from": f"Tiang_{i-1}" if i > 1 else "Trafo", "to": f"Tiang_{i}"} for i in range(1, num_buses + 1)]
        }

        return jsonify(sanitize_json(response_data))

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/hosting-capacity", methods=["POST"])
def get_hosting_capacity():
    """Pemindaian kapasitas tampung maksimum PLTS pada jaringan"""
    try:
        req = request.json or {}
        num_buses = int(req.get("num_buses", 10))
        span_length_m = float(req.get("span_length_m", 40.0))
        cable_type = req.get("cable_type", "LVTC 3x70 + 1x50 mm²")
        transformer_type = req.get("transformer_type", "100 kVA (Dyn5)")
        v_nominal = float(req.get("v_nominal", 220.0))
        base_load_kw = float(req.get("base_load_kw", 1.5))
        cos_phi = float(req.get("cos_phi", 0.95))
        custom_branches = req.get("custom_branches", None)

        net_params = {
            "num_buses": num_buses,
            "span_length_km": span_length_m / 1000.0,
            "cable_type_name": cable_type,
            "transformer_type_name": transformer_type,
            "base_load_per_bus_kw": base_load_kw,
            "power_factor": cos_phi,
            "custom_branches": custom_branches
        }

        noon_load = [base_load_kw * 0.5] * num_buses
        pv_indices = list(range(1, num_buses + 1))

        hc_res = calculate_hosting_capacity(
            net_params=net_params,
            load_kw_at_noon=noon_load,
            pv_installed_indices=pv_indices,
            v_nominal_v=v_nominal,
            max_pv_kw_test=8.0,
            step_kw=1.0
        )

        df_hc = hc_res["df_hosting_capacity"]
        scan_records = []
        for _, row in df_hc.iterrows():
            scan_records.append({
                "pv_kw": float(row["Kapasitas_PV_kWp"]),
                "v_max_volt": float(row["V_Maks_Volt"]),
                "trafo_loading_pct": float(row["Beban_Trafo_Pct"]),
                "status": str(row["Status"])
            })

        return jsonify(sanitize_json({
            "status": "success",
            "hosting_capacity_kw": hc_res["optimal_capacity_per_house_kwp"],
            "total_feeder_capacity_kwp": hc_res["total_hosting_capacity_feeder_kwp"],
            "limiting_factor": hc_res["limiting_factor"],
            "scan_data": scan_records
        }))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/export-docx", methods=["POST"])
def download_docx():
    """Menghasilkan file Microsoft Word (.docx) proposal kelayakan konsumen"""
    try:
        req = request.json or {}
        consumer_name = req.get("consumer_name", "Bpk. Budi Santoso")
        consumer_address = req.get("consumer_address", "Jl. Panorama Hijau No. 8, Semarang")
        pln_id = req.get("pln_id", "5381-0924-8810")
        tariff_group = req.get("tariff_group", "R-1/TR 2.200 VA (Rp 1.444,70 / kWh)")
        monthly_bill_idr = float(req.get("monthly_bill_idr", 1500000.0))
        consultant_name = req.get("consultant_name", "Tim Konsultan Sistem Tenaga Surya")
        bess_choice = req.get("bess_choice", "Termasuk Baterai LiFePO4 5.0 kWh")
        field_notes = req.get("field_notes", "Atap bebas bayangan arah utara sudut 15°, proteksi SPD Kelas II & grounding < 2 Ohm")

        sim_data = req.get("sim_data", {})
        metrics = sim_data.get("metrics", {})
        hourly_summary = pd.DataFrame(sim_data.get("hourly_summary", []))
        techno_econ = sim_data.get("techno_econ", {})
        unbalance_res = sim_data.get("unbalance_res", {})
        bess_params = sim_data.get("bess_params", {})

        net_params = {
            "num_buses": len(sim_data.get("bus_list", [])),
            "span_length_km": 0.04,
            "cable_type_name": req.get("cable_type", "LVTC 3x70 + 1x50 mm²"),
            "transformer_type_name": req.get("transformer_type", "100 kVA (Dyn5)"),
            "base_load_per_bus_kw": 1.5
        }

        docx_bytes = export_simulation_to_docx(
            metrics=metrics,
            hourly_summary=hourly_summary,
            net_params=net_params,
            techno_econ=techno_econ,
            unbalance_res=unbalance_res,
            bess_params=bess_params,
            consumer_name=consumer_name,
            consumer_address=consumer_address,
            pln_id=pln_id,
            tariff_group=tariff_group,
            monthly_bill_idr=monthly_bill_idr,
            consultant_name=consultant_name,
            bess_choice=bess_choice,
            field_notes=field_notes
        )

        safe_name = "".join([c if c.isalnum() else "_" for c in consumer_name]).strip("_")
        if not safe_name:
            safe_name = "Konsumen"

        return send_file(
            io.BytesIO(docx_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=f"Proposal_Kelayakan_PLTS_{safe_name}.docx"
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/export-excel", methods=["POST"])
def download_excel():
    """Menghasilkan file Microsoft Excel (.xlsx) audit kelistrikan & tekno-ekonomi konsumen"""
    try:
        req = request.json or {}
        consumer_name = req.get("consumer_name", "Bpk. Budi Santoso")
        sim_data = req.get("sim_data", {})

        metrics = sim_data.get("metrics", {})
        hourly_summary = pd.DataFrame(sim_data.get("hourly_summary", []))
        techno_econ = sim_data.get("techno_econ", {})
        unbalance_res = sim_data.get("unbalance_res", {})

        base_v_df = pd.DataFrame.from_dict(sim_data.get("base_v_volt", {}), orient="index")
        pv_v_df = pd.DataFrame.from_dict(sim_data.get("pv_v_volt", {}), orient="index")

        excel_buffer = io.BytesIO()
        export_simulation_to_excel(
            metrics=metrics,
            hourly_summary=hourly_summary,
            base_v_volt=base_v_df,
            pv_v_volt=pv_v_df,
            load_df=pd.DataFrame(),
            file_path=excel_buffer,
            consumer_info={
                "Nama Konsumen": req.get("consumer_name", "Bpk. Budi Santoso"),
                "Alamat Properti": req.get("consumer_address", "Jl. Panorama Hijau No. 8, Semarang"),
                "ID Pelanggan PLN": req.get("pln_id", "5381-0924-8810"),
                "Golongan Tarif": req.get("tariff_group", "R-1/TR 2.200 VA"),
                "Estimasi Tagihan Bulanan": f"Rp {float(req.get('monthly_bill_idr', 1500000)):,.0f}",
                "Opsi Sistem Baterai": req.get("bess_choice", "Termasuk Baterai LiFePO4 5.0 kWh"),
                "Disusun Oleh": req.get("consultant_name", "Tim Konsultan Sistem Tenaga Surya")
            },
            techno_econ=techno_econ
        )
        excel_buffer.seek(0)

        safe_name = "".join([c if c.isalnum() else "_" for c in consumer_name]).strip("_")
        if not safe_name:
            safe_name = "Konsumen"

        return send_file(
            excel_buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"Audit_Kelistrikan_PLTS_{safe_name}.xlsx"
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    print("\n" + "="*65)
    print("  ⚡ VoltSolar-Sim Pro Enterprise (Web Server HTML5 & Flask)")
    print("  Projek Praktikum Pemrograman Dasar - Teknologi Rekayasa Elektro")
    print("  Server berjalan pada: http://localhost:5000")
    print("="*65 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
