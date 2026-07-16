"""Data aggregation and export functions for the ENTSO-E collector pipeline."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from collector.models.opentepes import _DEFAULT_ELECTROLYSER_EFF, h2_main_zones
from collector.utils.config import TECH_COLUMNS, build_tech_columns
from collector.utils.helpers import expand_profile_to_hourly

# Mapping from technology capacity column name -> commodity price key
# (used to add "Fuel (EUR/MWh)" column to Normal mode output)
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


# ---------------------------------------------------------------------------
# Availability summary
# ---------------------------------------------------------------------------


def build_availability_summary(
    profiles_df: dict[str, list[dict]],
    node_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build a profile-availability matrix (zones × profile types).

    A cell is ``'Available'`` when the corresponding data array contains at
    least one non-zero, non-NaN value; otherwise ``'No Data'``.

    Args:
        profiles_df (dict[str, list[dict]]): Combined profiles dict as returned
            by :func:`~collector.data.loader.load_all_profiles`.
        node_df (pd.DataFrame): Nodes table with ``Code`` and ``Location``
            columns (used to enrich row labels).

    Returns:
        pd.DataFrame: Transposed availability matrix with profile types as rows
            and zone codes (with country names) as columns.

    Example:
        >>> summary = build_availability_summary(profiles, nodes)
        >>> summary.shape
        (16, 3)
    """
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


# ---------------------------------------------------------------------------
# Per-zone Excel export
# ---------------------------------------------------------------------------


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
    """Write all data for a single zone to a multi-sheet Excel workbook.

    Sheets written:

    * ``Technology Capacities`` – MW capacity table (Parameter / Value).
    * ``Storage Capacities``    – MWh capacity table.
    * ``Reserve Requirements``  – FCR/FRR values.
    * ``Hourly Profiles``       – time-series profiles + cross-border flows.
    * ``Technology Characteristics`` – per-tech unit parameters.
    * ``Gas & Hydrogen Assets`` – storage and terminal capacities.

    Args:
        zone_name (str): Zone code (e.g. ``'ES00'``).
        tech_cap_df (pd.DataFrame): Technology capacity DataFrame.
        tech_char_df (pd.DataFrame): Technology characteristics DataFrame.
        reserve_req_df (pd.DataFrame): Reserve requirements DataFrame.
        profiles_df (dict[str, list[dict]]): Combined profiles dict.
        export_df (pd.DataFrame): Cross-border exchange flows DataFrame.
        storage_df (dict[str, np.ndarray]): Storage capacity arrays.
        terminal_df (dict[str, np.ndarray]): Terminal import capacity arrays.
        selected_hours (int): Hourly series length used for padding.
        output_folder (str): Folder where ``<zone_name>.xlsx`` is written.

    Returns:
        None

    Example:
        >>> export_zone_data("ES00", cap_df, char_df, res_df,
        ...                  profiles, exports, storage, terminals,
        ...                  8736, "Outputs/Excel Files/Normal")
    """
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
    # Remove zero-capacity DSR / Other Non-RES entries from Technology Capacities sheet
    _multi_zero = df_mw["Parameter"].str.startswith(("DSR", "Other Non-RES"), na=False) & (
        pd.to_numeric(df_mw["Value"], errors="coerce").fillna(0) == 0
    )
    df_mw = df_mw[~_multi_zero]
    # If only one DSR / Other Non-RES type is present, relabel "<x>1" → "<x>"
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

    # Merge in cross-border exports
    export_cols = export_df.filter(like=f"Exports_{zone_name}_", axis=1).copy()
    export_cols.index = export_cols.index + 1
    merged = hourly_out.merge(export_cols, left_index=True, right_index=True, how="outer")

    # Add each profile type as a column
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

    # Drop DSR / Other Non-RES rows where the installed capacity is zero or absent
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

    # Inject "Fuel (EUR/MWh)" column from TYNDP commodity prices
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
    """Extract a flat list of floats from a cell that may contain an array."""
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
    """Convert the technology characteristics row for *zone_name* to a 2-D DataFrame."""
    matches = tech_char_df[tech_char_df["Code"] == zone_name]
    if matches.empty:
        return pd.DataFrame()

    idx = matches.index[0]
    out = pd.DataFrame()
    # Char rows are labelled positionally, so match the DSR count used to build
    # the char arrays (Other Non-RES is fixed at 27).
    tech_label_cols = build_tech_columns(n_dsr)[1:]

    for col in tech_char_df.columns[1:]:
        arr = tech_char_df.loc[idx, col]
        for r, value in enumerate(arr if hasattr(arr, "__iter__") else [arr]):
            row_title = tech_label_cols[r] if r < len(tech_label_cols) else f"row_{r}"
            if isinstance(value, (list, np.ndarray)):
                out.loc[row_title, col] = ", ".join(map(str, value))
            else:
                if col == "Efficiency (%)" and isinstance(value, (int, float)):
                    # Electrolysers with a blank/zero source efficiency default to
                    # 68% (matching the openTEPES ProductionFunctionH2 fallback).
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
    """Build the Gas & Hydrogen assets summary table for *zone_name*."""
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


# ---------------------------------------------------------------------------
# Network Excel export
# ---------------------------------------------------------------------------


def export_network_data(
    network_df: dict[str, np.ndarray],
    output_folder: str,
    commodity_prices: dict[str, float] | None = None,
) -> None:
    """Write loss fractions and line capacities for all carriers to ``Networks.xlsx``.

    Columns for loss fractions: ``From``, ``To``, ``Length (km)``,
    ``Loss Fraction (%)``.

    Columns for line capacities: ``From``, ``To``,
    ``From-To Capacity (MW)``, ``To-From Capacity (MW)``.

    Args:
        network_df (dict[str, np.ndarray]): Network data as returned by
            :func:`~collector.processing.transforms.build_network_data`.
        output_folder (str): Folder where ``Networks.xlsx`` is written.

    Returns:
        None

    Example:
        >>> export_network_data(network_df, "Outputs/Excel Files/Normal")
    """
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


# ---------------------------------------------------------------------------
# Convenience: export all zones at once
# ---------------------------------------------------------------------------


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
    """Export per-zone Excel workbooks and the shared Networks workbook.

    Iterates over *selected_zones*, calls
    :func:`export_zone_data` for each, then calls
    :func:`export_network_data` once.

    Args:
        tech_cap_df (pd.DataFrame): Technology capacity DataFrame.
        tech_char_df (pd.DataFrame): Technology characteristics DataFrame.
        reserve_req_df (pd.DataFrame): Reserve requirements DataFrame.
        profiles_df (dict[str, list[dict]]): Combined profiles dict.
        export_df (pd.DataFrame): Cross-border exchange flows.
        storage_df (dict[str, np.ndarray]): Storage capacity arrays.
        terminal_df (dict[str, np.ndarray]): Terminal import capacity arrays.
        network_df (dict[str, np.ndarray]): Network loss and capacity arrays.
        selected_hours (int): Hourly series length.
        selected_zones (list[str]): Zone codes to export.
        output_folder (str): Root output folder (e.g.
            ``'Outputs/Excel Files/Normal'``).

    Returns:
        None

    Example:
        >>> export_all_zones(cap_df, char_df, res_df, profiles, exports,
        ...                  storage, terminals, network, 8736,
        ...                  ["ES00", "PT00"], "Outputs/Excel Files/Normal")
    """
    # Hydrogen demand is a country-level total tied to the country's single H2
    # node, but the loader assigns it to every zone of the country. Keep it only
    # on the main/representative zone (the Lines_H node, matching the openTEPES
    # export) and zero the country's other zones so the per-zone workbooks don't
    # duplicate the national total.
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
                        commodity_prices=commodity_prices)
