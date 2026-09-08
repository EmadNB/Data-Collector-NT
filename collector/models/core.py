from __future__ import annotations

import os
import re

import numpy as np
import pandas as pd

from collector.models.opentepes import (
    _DEFAULT_ELECTROLYSER_EFF,
    h2_intra_country_pairs,
    h2_main_zones,
)
from collector.utils.config import TECH_COLUMNS, build_tech_columns
from collector.utils.helpers import expand_profile_to_hourly

_TECH_COL_FUEL_KEY: dict[str, str] = {
    "Nuclear (MW)":              "Nuclear",
    "Hard Coal (old1) (MW)":     "Hard_coal",
    "Hard Coal (old2) (MW)":     "Hard_coal",
    "Hard Coal (new) (MW)":      "Hard_coal",
    "Hard Coal (ccs) (MW)":      "Hard_coal",
    "Lignite (old1) (MW)":       "Lignite",
    "Lignite (old2) (MW)":       "Lignite",
    "Lignite (new) (MW)":        "Lignite",
    "Lignite (ccs) (MW)":        "Lignite",
    "Gas (conv_old1) (MW)":      "Natural_Gas",
    "Gas (conv_old2) (MW)":      "Natural_Gas",
    "Gas (ccgt_old1) (MW)":      "Natural_Gas",
    "Gas (ccgt_old2) (MW)":      "Natural_Gas",
    "Gas (ccgt_new) (MW)":       "Natural_Gas",
    "Gas (ccgt_ccs) (MW)":       "Natural_Gas",
    "Gas (ocgt_old) (MW)":       "Natural_Gas",
    "Gas (ocgt_new) (MW)":       "Natural_Gas",
    "Light Oil (MW)":            "Light_oil",
    "Heavy oil (old1) (MW)":     "Heavy_oil",
    "Heavy oil (old2) (MW)":     "Heavy_oil",
    "Oil shale (old) (MW)":      "Oil_shale",
    "Oil shale (new) (MW)":      "Oil_shale",
    "Gas (ccgt_pre1) (MW)":      "Natural_Gas",
    "Gas (ccgt_pre2) (MW)":      "Natural_Gas",
    "Hydrogen (fc) (MW)":        "Hydrogen",
    "Hydrogen (ccgt) (MW)":      "Hydrogen",
    "Other RES (biomass) (MW)":  "Biomethane",
    "Other RES (waste) (MW)":    "Biomethane",
}


# Availability summary


def build_availability_summary(
    profiles_df: dict[str, list[dict]],
    node_df: pd.DataFrame,
) -> pd.DataFrame:
    code_to_country: dict[str, str] = {}
    if isinstance(node_df, pd.DataFrame) and {"Code", "Location"}.issubset(node_df.columns):
        code_to_country = {str(r["Code"]): str(r["Location"]) for _, r in node_df.iterrows()}

    all_codes = sorted({p["Code"] for pl in profiles_df.values() for p in pl})
    profile_types = sorted(profiles_df.keys())

    records: list[dict] = []
    for code in all_codes:
        country = code_to_country.get(code, "")
        display = f"{country}\n({code})" if country else code
        row: dict = {"Code": display}
        for pt in profile_types:
            found = False
            for entry in profiles_df.get(pt, []):
                if entry.get("Code") == code:
                    arr = entry.get("Data")
                    if isinstance(arr, np.ndarray) and not np.all((np.isnan(arr)) | (arr == 0)):
                        found = True
                        break
            row[pt] = "Available" if found else "No Data"
        records.append(row)

    df = pd.DataFrame(records).set_index("Code")
    return df.transpose()


# Per-zone Excel export


def export_zone_data(
    zone_name: str,
    tech_cap_df: pd.DataFrame,
    tech_char_df: pd.DataFrame,
    reserve_req_df: pd.DataFrame,
    profiles_df: dict[str, list[dict]],
    export_df: pd.DataFrame,
    storage_df: dict[str, np.ndarray],
    terminal_df: dict[str, np.ndarray],
    selected_hours: int,
    output_folder: str,
    commodity_prices: dict[str, float] | None = None,
    lignite_groups: dict[str, str] | None = None,
) -> None:
    os.makedirs(output_folder, exist_ok=True)

    mw_cols   = [c for c in tech_cap_df.columns if "(MW)" in c]
    mwh_cols  = [c for c in tech_cap_df.columns if "(MWh)" in c]
    ts_cols   = [c for c in tech_cap_df.columns
                 if any(t in c for t in ["(MW/h)", "(MWh/h)", "(MW-h)", "(MWh-h)"])]
    id_col    = ["Code"] if "Code" in tech_cap_df.columns else []

    zone_row = tech_cap_df[tech_cap_df["Code"] == zone_name]
    if zone_row.empty:
        print(f"No capacity data found for zone {zone_name} – skipping export")
        return

    zone_df = zone_row.loc[:, ~zone_row.columns.duplicated()]

    df_mw  = zone_df[id_col + mw_cols].T.reset_index()
    df_mw.columns  = ["Parameter", "Value"]
    _multi_zero = df_mw["Parameter"].str.startswith(("DSR", "Other Non-RES"), na=False) & (
        pd.to_numeric(df_mw["Value"], errors="coerce").fillna(0) == 0
    )
    df_mw = df_mw[~_multi_zero]
    _single_dsr = df_mw["Parameter"].str.startswith("DSR", na=False).sum() == 1
    _single_onr = df_mw["Parameter"].str.startswith("Other Non-RES", na=False).sum() == 1
    if _single_dsr:
        df_mw["Parameter"] = df_mw["Parameter"].replace({"DSR1 (MW)": "DSR (MW)"})
    if _single_onr:
        df_mw["Parameter"] = df_mw["Parameter"].replace({"Other Non-RES1 (MW)": "Other Non-RES (MW)"})
    df_mwh = zone_df[id_col + mwh_cols].T.reset_index()
    df_mwh.columns = ["Parameter", "Value"]

    # Build hourly profiles sheet
    hourly_data: dict[str, list] = {}
    max_len = 0
    for col in ts_cols:
        cell = zone_row.iloc[0][col]
        values = _extract_array_values(cell)
        if not values:
            continue
        if col.startswith(("DSR", "Other Non-RES")) and all(v == 0 or v != v for v in values):
            continue
        hourly_data[col] = values
        max_len = max(max_len, len(values))

    if hourly_data:
        hourly_out = pd.DataFrame(
            {p: (v if len(v) == max_len else v + [None] * (max_len - len(v)))
             for p, v in hourly_data.items()},
            index=range(1, max_len + 1),
        )
        hourly_out.index.name = "Hour"
    else:
        hourly_out = pd.DataFrame()

    export_cols = export_df.filter(
        regex=rf"Exports_{re.escape(zone_name)}(_| )", axis=1
    ).copy()
    export_cols.index = export_cols.index + 1
    merged = hourly_out.merge(export_cols, left_index=True, right_index=True, how="outer")

    for profile_type, profile_list in profiles_df.items():
        for entry in profile_list:
            if entry["Code"] != zone_name:
                continue
            data = entry["Data"]
            if len(data) != selected_hours:
                data = expand_profile_to_hourly(data, selected_hours)
            merged[profile_type] = list(data)
            break

    merged = merged.fillna(0)

    _SOLAR_FALLBACK_PAIRS = [
        ("Solar (MW)",                        "Solar Profile",             "Solar_Utility Profile"),
        ("Solar (rooftop) (MW)",              "Solar_Rooftop Profile",     "Solar Profile"),
        ("Solar (thermal) (MW)",              "CSP_noStorage Profile",     "CSP_withStorage_D Profile"),
        ("Solar (thermal_with_storage) (MW)", "CSP_withStorage_D Profile", "CSP_noStorage Profile"),
    ]
    for _cap_col, _primary_col, _fallback_col in _SOLAR_FALLBACK_PAIRS:
        if _cap_col not in zone_df.columns:
            continue
        try:
            _cap = float(zone_df[_cap_col].iloc[0])
        except (TypeError, ValueError):
            _cap = 0.0
        if _cap <= 0:
            continue
        _primary = merged.get(_primary_col)
        _primary_missing = _primary is None or not (
            pd.to_numeric(_primary, errors="coerce").fillna(0) != 0
        ).any()
        if not _primary_missing:
            continue
        _fallback = merged.get(_fallback_col)
        if _fallback is not None and (pd.to_numeric(_fallback, errors="coerce").fillna(0) != 0).any():
            merged[_primary_col] = _fallback

    if _single_dsr:
        merged = merged.rename(columns={"DSR1 (MW/h)": "DSR (MW/h)"})
    if _single_onr:
        merged = merged.rename(columns={"Other Non-RES1 (MW/h)": "Other Non-RES (MW/h)"})

    # Reserve requirements
    reserve_zone = (
        reserve_req_df[reserve_req_df["Code"] == zone_name]
        if "Code" in reserve_req_df.columns
        else reserve_req_df
    ).fillna(0).T
    reserve_clean = pd.DataFrame(columns=["Parameter", "Value"])
    reserve_clean.loc[0] = ["Code", zone_name]
    items  = reserve_zone.index.tolist()
    values = reserve_zone.iloc[:, 0].tolist() if reserve_zone.shape[1] > 0 else []
    for i, param in enumerate(items):
        if param == "Code":
            continue
        reserve_clean.loc[len(reserve_clean)] = [param, values[i] if i < len(values) else None]

    # Technology characteristics
    _n_dsr = sum(1 for c in tech_cap_df.columns
                 if str(c).startswith("DSR") and str(c).endswith("(MW)"))
    tech_char_excel = _build_tech_char_excel(tech_char_df, zone_name, _n_dsr)

    if not tech_char_excel.empty:
        rows_to_drop = []
        for _rt in list(tech_char_excel.index):
            if not str(_rt).startswith(("DSR", "Other Non-RES")):
                continue
            _cap_col = str(_rt)
            if _cap_col not in tech_cap_df.columns:
                rows_to_drop.append(_rt)
                continue
            _cap_vals = tech_cap_df.loc[tech_cap_df["Code"] == zone_name, _cap_col]
            if _cap_vals.empty:
                rows_to_drop.append(_rt)
                continue
            try:
                _v = float(_cap_vals.iloc[0])
                if _v != _v or _v == 0:
                    rows_to_drop.append(_rt)
            except (TypeError, ValueError):
                rows_to_drop.append(_rt)
        if rows_to_drop:
            tech_char_excel = tech_char_excel.drop(index=rows_to_drop, errors="ignore")
        if _single_dsr:
            tech_char_excel = tech_char_excel.rename(index={"DSR1 (MW)": "DSR (MW)"})
        if _single_onr:
            tech_char_excel = tech_char_excel.rename(index={"Other Non-RES1 (MW)": "Other Non-RES (MW)"})

    if commodity_prices and not tech_char_excel.empty:
        country = zone_name.rstrip("0123456789")
        lignite_key = (lignite_groups or {}).get(country, "Lignite_G2")
        for row_title in tech_char_excel.index:
            fuel_key = _TECH_COL_FUEL_KEY.get(str(row_title), "")
            if fuel_key == "Lignite":
                fuel_key = lignite_key
            tech_char_excel.loc[row_title, "Fuel (EUR/MWh)"] = (
                commodity_prices.get(fuel_key, 0.0) if fuel_key else 0.0
            )

    if not tech_char_excel.empty:
        def _numeric_col(name: str) -> pd.Series:
            if name in tech_char_excel.columns:
                return pd.to_numeric(tech_char_excel[name], errors="coerce").fillna(0)
            return pd.Series(0.0, index=tech_char_excel.index)

        fix_cost   = _numeric_col("Start-up Fix Cost (EUR/MW)")
        fuel_cons  = _numeric_col("Start-up Fuel Consumption (GJ/MW)")
        fuel_price = _numeric_col("Fuel (EUR/MWh)")
        tech_char_excel["Start-Up Cost (EUR)"] = fix_cost + fuel_cons / 3.6 * fuel_price
        tech_char_excel = tech_char_excel.drop(
            columns=["Start-up Fuel Consumption (GJ/MW)", "Start-up Fix Cost (EUR/MW)"],
            errors="ignore",
        )

    # Gas & Hydrogen assets
    assets_df = _build_assets_df(zone_name, storage_df, terminal_df)

    out_path = os.path.join(output_folder, f"{zone_name}.xlsx")
    with pd.ExcelWriter(out_path) as writer:
        df_mw.style.set_properties(**{"font-weight": "bold"}, subset=["Parameter"]).to_excel(
            writer, sheet_name="Technology Capacities", index=False)
        df_mwh.style.set_properties(**{"font-weight": "bold"}, subset=["Parameter"]).to_excel(
            writer, sheet_name="Storage Capacities", index=False)
        reserve_clean.style.set_properties(**{"font-weight": "bold"}, subset=["Parameter"]).to_excel(
            writer, sheet_name="Reserve Requirements", index=False)
        merged.to_excel(writer, sheet_name="Hourly Profiles")
        tech_char_excel.fillna(0).to_excel(writer, sheet_name="Technology Characteristics")
        assets_df.style.set_properties(**{"font-weight": "bold"}, subset=["Parameter"]).to_excel(
            writer, sheet_name="Gas & Hydrogen Assets", index=False)

    print(f"Exported zone data: {out_path}")


def _extract_array_values(cell: object) -> list:
    if isinstance(cell, (list, np.ndarray)):
        raw = list(cell)
    elif isinstance(cell, str):
        sep = "," if "," in cell else None
        raw = [v.strip() for v in (cell.split(sep) if sep else cell.split())]
    elif pd.isna(cell) if not isinstance(cell, (list, np.ndarray)) else False:
        return []
    else:
        try:
            raw = list(cell)
        except TypeError:
            return []

    flat: list[float] = []
    for v in raw:
        item = v[0] if isinstance(v, (list, tuple, np.ndarray)) else v
        if item is not None and item != "":
            try:
                flat.append(float(item))
            except (TypeError, ValueError):
                pass
    return flat


def _build_tech_char_excel(tech_char_df: pd.DataFrame, zone_name: str,
                           n_dsr: int) -> pd.DataFrame:
    matches = tech_char_df[tech_char_df["Code"] == zone_name]
    if matches.empty:
        return pd.DataFrame()

    idx = matches.index[0]
    out = pd.DataFrame()
    tech_label_cols = build_tech_columns(n_dsr)[1:]

    for col in tech_char_df.columns[1:]:
        arr = tech_char_df.loc[idx, col]
        for r, value in enumerate(arr if hasattr(arr, "__iter__") else [arr]):
            row_title = tech_label_cols[r] if r < len(tech_label_cols) else f"row_{r}"
            if isinstance(value, (list, np.ndarray)):
                out.loc[row_title, col] = ", ".join(map(str, value))
            else:
                if col == "Efficiency (%)" and isinstance(value, (int, float)):
                    if row_title == "Electrolyser (MW)" and (pd.isna(value) or value <= 0):
                        value = _DEFAULT_ELECTROLYSER_EFF
                    value = value * 100
                out.loc[row_title, col] = value

    out.index.name = "Technology"
    return out


def _build_assets_df(
    zone_name: str,
    storage_df: dict[str, np.ndarray],
    terminal_df: dict[str, np.ndarray],
) -> pd.DataFrame:
    def _val(arr: np.ndarray | None, col_idx: int) -> float:
        if arr is None or len(arr) == 0:
            return 0.0
        for row in arr:
            if str(row[0]) == zone_name:
                try:
                    return float(row[col_idx])
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    g  = storage_df.get("Storage Capacity (Gas)")
    h  = storage_df.get("Storage Capacity (Hydrogen)")
    tg = terminal_df.get("Terminal (Gas)")
    th = terminal_df.get("Terminal (Hydrogen)")

    return pd.DataFrame({
        "Parameter": [
            "Code",
            "Injection (Gas) (MW)",
            "Withdraw (Gas) (MW)",
            "Terminal (Gas) (MW)",
            "Injection (Hydrogen) (MW)",
            "Withdraw (Hydrogen) (MW)",
            "Terminal (Hydrogen) (MW)",
        ],
        "Value": [
            zone_name,
            _val(g,  1), _val(g,  2), _val(tg, 1),
            _val(h,  1), _val(h,  2), _val(th, 1),
        ],
    })


# Network Excel export


_H2_INTRA_CAP_MW = 200000.0


def export_network_data(
    network_df: dict[str, np.ndarray],
    output_folder: str,
    commodity_prices: dict[str, float] | None = None,
    selected_zones: list[str] | None = None,
) -> None:
    os.makedirs(output_folder, exist_ok=True)
    loss_cols = ["From", "To", "Length (km)", "Loss Fraction (%)"]
    cap_cols  = ["From", "To", "From-To Capacity (MW)", "To-From Capacity (MW)"]

    def _to_df(key: str, columns: list[str]) -> pd.DataFrame | None:
        data = network_df.get(key)
        if data is None:
            return None
        if not isinstance(data, pd.DataFrame):
            return pd.DataFrame(data, columns=columns)
        df = data.copy()
        df.columns = columns
        return df

    out_path = os.path.join(output_folder, "Networks.xlsx")
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for carrier, sheet in [("Electricity", "Electricity Lines"),
                                ("Gas",         "Gas Pipelines"),
                                ("Hydrogen",    "Hydrogen Pipelines")]:
            loss_df = _to_df(f"Loss Fraction ({carrier})",   loss_cols)
            cap_df  = _to_df(f"Line Capacity ({carrier})",   cap_cols)
            if carrier == "Hydrogen" and selected_zones:
                rep_map = h2_main_zones(network_df, selected_zones)
                pairs = h2_intra_country_pairs(rep_map, selected_zones)
                if pairs and loss_df is not None:
                    virt_loss = [
                        {"From": rep, "To": other, "Length (km)": 0, "Loss Fraction (%)": 0}
                        for rep, other in pairs
                    ]
                    loss_df = pd.concat(
                        [loss_df, pd.DataFrame(virt_loss, columns=loss_cols)],
                        ignore_index=True,
                    )
                if pairs and cap_df is not None:
                    virt_cap = [
                        {"From": rep, "To": other,
                         "From-To Capacity (MW)": _H2_INTRA_CAP_MW,
                         "To-From Capacity (MW)": _H2_INTRA_CAP_MW}
                        for rep, other in pairs
                    ]
                    cap_df = pd.concat(
                        [cap_df, pd.DataFrame(virt_cap, columns=cap_cols)],
                        ignore_index=True,
                    )
            if loss_df is not None:
                loss_df.to_excel(writer, sheet_name=sheet, index=False, startrow=0, startcol=0)
            if cap_df is not None:
                cap_df.to_excel(writer, sheet_name=sheet, index=False, startrow=0, startcol=5)

        # Commodity price data sheet
        cp = commodity_prices or {}
        data_df = pd.DataFrame({
            "CO2 Price (EUR/ton)": [round(cp.get("CO2_price", 0.0), 4)],
            "Gas Price (EUR/MWh)": [round(cp.get("Gas_blend_NT", 0.0), 4)],
        })
        data_df.to_excel(writer, sheet_name="Data", index=False)

    print(f"Exported network data: {out_path}")


# Convenience: export all zones at once


def export_all_zones(
    tech_cap_df: pd.DataFrame,
    tech_char_df: pd.DataFrame,
    reserve_req_df: pd.DataFrame,
    profiles_df: dict[str, list[dict]],
    export_df: pd.DataFrame,
    storage_df: dict[str, np.ndarray],
    terminal_df: dict[str, np.ndarray],
    network_df: dict[str, np.ndarray],
    selected_hours: int,
    selected_zones: list[str],
    output_folder: str,
    commodity_prices: dict[str, float] | None = None,
    lignite_groups: dict[str, str] | None = None,
) -> None:
    _h2_main = set(h2_main_zones(network_df, selected_zones).values())
    for _entry in profiles_df.get("Hydrogen Demand Profile", []):
        if str(_entry.get("Code")) not in _h2_main and _entry.get("Data") is not None:
            _entry["Data"] = np.zeros_like(np.asarray(_entry["Data"], dtype=float))

    for zone in selected_zones:
        export_zone_data(
            zone_name=zone,
            tech_cap_df=tech_cap_df,
            tech_char_df=tech_char_df,
            reserve_req_df=reserve_req_df,
            profiles_df=profiles_df,
            export_df=export_df,
            storage_df=storage_df,
            terminal_df=terminal_df,
            selected_hours=selected_hours,
            output_folder=output_folder,
            commodity_prices=commodity_prices,
            lignite_groups=lignite_groups,
        )
    export_network_data(network_df=network_df, output_folder=output_folder,
                        commodity_prices=commodity_prices, selected_zones=selected_zones)
