from __future__ import annotations

import glob
import os
import re
import openpyxl
from openpyxl.utils import get_column_letter
from functools import lru_cache
import numpy as np
import pandas as pd

_OTHER_NONRES_COLS = [get_column_letter(3 + i) for i in range(27)]

_THERMAL_SHEET_ROW_ORDER = list(range(13)) + [22, 23] + list(range(13, 22)) + list(range(24, 26))


@lru_cache(maxsize=16)
def _excel(path: str) -> pd.ExcelFile:
    return pd.ExcelFile(path)


def clear_excel_cache() -> None:
    _excel.cache_clear()
    _dsr_col_count.cache_clear()

from collector.utils.config import (
    FILEPATH_CO2_FACTORS,
    FILEPATH_COMMON_DATA,
    FILEPATH_COMMODITY_PRICES,
    FILEPATH_NETWORKS,
    FILEPATH_STORAGES,
    FILEPATH_TERMINALS,
    GAS_UNIT_FACTOR,
    HYDRO_FILE_TEMPLATES,
    HYDRO_SCALE_FACTOR,
    HYDRO_SHEET_NAMES,
    HYDRO_TARGET_LENGTHS,
    PECD_FILE_TEMPLATES,
    RESERVE_COLUMNS,
    SOLAR_ROOFTOP_TARGET_LEN,
    TECH_CHAR_COLUMNS,
    TECH_COLUMNS,
    DSR_DEFAULT_COUNT,
    build_tech_columns,
)
from collector.utils.helpers import get_co2_usecols, get_pemmdb_filepath


@lru_cache(maxsize=256)
def _dsr_col_count(filepath: str) -> int:
    try:
        wb = openpyxl.load_workbook(filepath, read_only=True)
        try:
            n = wb["DSR"].max_column
        finally:
            wb.close()
        return max((n or 2) - 2, 0)
    except Exception:
        return 0


def _dsr_count_for(selected_zones: list[str], scenario: int) -> int:
    counts = [_dsr_col_count(get_pemmdb_filepath(z, scenario)) for z in selected_zones]
    return max(counts + [DSR_DEFAULT_COUNT])


def _dsr_cols(n_dsr: int) -> list[str]:
    return [get_column_letter(3 + i) for i in range(n_dsr)]


def _dsr_climate_year_mask(filepath: str, width: int, climate_year: int | None) -> np.ndarray:
    if width <= 0:
        return np.zeros(0, dtype=bool)
    if climate_year is None:
        return np.ones(width, dtype=bool)
    try:
        bounds = pd.read_excel(
            _excel(filepath), sheet_name="DSR",
            usecols=f"C:{get_column_letter(2 + width)}", header=None,
            skiprows=12, nrows=2,
        )
    except Exception:
        return np.ones(width, dtype=bool)
    mask = np.ones(width, dtype=bool)
    for _i in range(min(width, bounds.shape[1])):
        start, end = bounds.iat[0, _i], bounds.iat[1, _i]
        if pd.notna(start) and pd.notna(end):
            mask[_i] = start <= climate_year <= end
    return mask


# Node / network raw loaders


def load_nodes(filepath: str = FILEPATH_NETWORKS, sheet_name: str = "Nodes") -> pd.DataFrame:
    return pd.read_excel(filepath, sheet_name=sheet_name)


def load_network_edges(
    scenario: int,
    filepath: str = FILEPATH_NETWORKS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    edges_e = pd.read_excel(filepath, sheet_name="Lines_E")
    edges_g = pd.read_excel(filepath, sheet_name=f"Lines_G ({scenario})")
    edges_h = pd.read_excel(filepath, sheet_name=f"Lines_H ({scenario})")
    return edges_e, edges_g, edges_h


def load_network_storages(
    scenario: int,
    filepath: str = FILEPATH_STORAGES,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    storages_g = pd.read_excel(filepath, sheet_name=f"Storage_G ({scenario})")
    storages_h = pd.read_excel(filepath, sheet_name=f"Storage_H ({scenario})")
    return storages_g, storages_h


def load_network_terminals(
    scenario: int,
    filepath: str = FILEPATH_TERMINALS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    terminals_g = pd.read_excel(filepath, sheet_name=f"Terminal_G ({scenario})")
    terminals_h = pd.read_excel(filepath, sheet_name=f"Terminal_H ({scenario})")
    return terminals_g, terminals_h


# PEMMDB loaders


def load_tech_capacities(
    node_df: pd.DataFrame,
    selected_zones: list[str],
    scenario: int,
    selected_hours: int,
    climate_year: int | None = None,
) -> pd.DataFrame:
    n_dsr = _dsr_count_for(selected_zones, scenario)
    columns = build_tech_columns(n_dsr)
    tech_rows: list[dict] = []
    for code in node_df["Code"]:
        if code not in selected_zones:
            continue
        filepath = get_pemmdb_filepath(code, scenario)
        data: dict = {"Code": code}
        try:
            _read_thermal_capacities(filepath, data)
            _read_hydro_capacities(filepath, data)
            _read_res_capacities(filepath, data, n_dsr, climate_year)
            _read_storage_capacities(filepath, data)
            _read_timeseries_capacities(filepath, data, selected_hours, n_dsr, climate_year)
            tech_rows.append(data)
            print(f"Technology capacities for {code}: OK")
        except FileNotFoundError:
            print(f"Technology capacities for {code}: file not found – zeros used")
            data.update({col: 0 for col in columns[1:]})
            tech_rows.append(data)
    return pd.DataFrame(tech_rows, columns=columns)


def _read_scalar(filepath: str, sheet: str, col: str, row: int,
                 default: object = 0.0) -> object:
    try:
        df = pd.read_excel(
            _excel(filepath), sheet_name=sheet, usecols=col, header=None, skiprows=row, nrows=1
        )
        if df is None or df.shape[1] == 0 or len(df) == 0:
            return default
        return df.iat[0, 0]
    except Exception:
        return default


def _read_thermal_capacities(filepath: str, data: dict) -> None:
    def _cell(sheet: str, col: str, row: int) -> float:
        return _read_scalar(filepath, sheet, col, row)

    data["Nuclear (MW)"]           = _cell("Thermal", "C", 11)
    data["Hard Coal (old1) (MW)"]  = _cell("Thermal", "C", 13)
    data["Hard Coal (old2) (MW)"]  = _cell("Thermal", "C", 15)
    data["Hard Coal (new) (MW)"]   = _cell("Thermal", "C", 17)
    data["Hard Coal (ccs) (MW)"]   = _cell("Thermal", "C", 19)
    data["Lignite (old1) (MW)"]    = _cell("Thermal", "C", 21)
    data["Lignite (old2) (MW)"]    = _cell("Thermal", "C", 23)
    data["Lignite (new) (MW)"]     = _cell("Thermal", "C", 25)
    data["Lignite (ccs) (MW)"]     = _cell("Thermal", "C", 27)
    data["Gas (conv_old1) (MW)"]   = _cell("Thermal", "C", 29)
    data["Gas (conv_old2) (MW)"]   = _cell("Thermal", "C", 31)
    data["Gas (ccgt_old1) (MW)"]   = _cell("Thermal", "C", 33)
    data["Gas (ccgt_old2) (MW)"]   = _cell("Thermal", "C", 35)
    data["Gas (ccgt_new) (MW)"]    = _cell("Thermal", "C", 37)
    data["Gas (ccgt_ccs) (MW)"]    = _cell("Thermal", "C", 39)
    data["Gas (ocgt_old) (MW)"]    = _cell("Thermal", "C", 41)
    data["Gas (ocgt_new) (MW)"]    = _cell("Thermal", "C", 43)
    data["Light Oil (MW)"]         = _cell("Thermal", "C", 45)
    data["Heavy oil (old1) (MW)"]  = _cell("Thermal", "C", 47)
    data["Heavy oil (old2) (MW)"]  = _cell("Thermal", "C", 49)
    data["Oil shale (old) (MW)"]   = _cell("Thermal", "C", 51)
    data["Oil shale (new) (MW)"]   = _cell("Thermal", "C", 53)
    data["Gas (ccgt_pre1) (MW)"]   = _cell("Thermal", "C", 55)
    data["Gas (ccgt_pre2) (MW)"]   = _cell("Thermal", "C", 57)
    data["Hydrogen (fc) (MW)"]     = _cell("Thermal", "C", 59)
    data["Hydrogen (ccgt) (MW)"]   = _cell("Thermal", "C", 61)


def _read_hydro_capacities(filepath: str, data: dict) -> None:
    def _cell(col: str, row: int, scale: float = 1.0) -> float:
        return _read_scalar(filepath, "Hydro", col, row) * scale

    data["Hydro (river) (MW)"]            = _cell("B", 8)
    data["Hydro (pondage) (MWh)"]         = _cell("B", 10, 1000)
    data["Hydro (pondage) (MW)"]          = _cell("B", 11)
    data["Hydro (reservoir) (MWh)"]       = _cell("B", 13, 1000)
    data["Hydro (reservoir) (MW)"]        = _cell("B", 14)
    data["Hydro (open_ps) (MWh)"]         = _cell("B", 16, 1000)
    data["Hydro (open_ps_turbine) (MW)"]  = _cell("B", 17)
    data["Hydro (open_ps_pump) (MW)"]     = _cell("B", 18)
    data["Hydro (closed_ps) (MWh)"]       = _cell("B", 20, 1000)
    data["Hydro (closed_ps_turbine) (MW)"] = _cell("B", 21)
    data["Hydro (closed_ps_pump) (MW)"]   = _cell("B", 22)


def _read_res_capacities(filepath: str, data: dict, n_dsr: int = DSR_DEFAULT_COUNT,
                         climate_year: int | None = None) -> None:
    def _cell(sheet: str, col: str, row: int, scale: float = 1.0) -> float:
        return _read_scalar(filepath, sheet, col, row) * scale

    data["Wind (onshore) (MW)"]                  = _cell("Wind",      "B", 7, 1000)
    data["Wind (offshore) (MW)"]                 = _cell("Wind",      "B", 8, 1000)
    data["Solar (thermal) (MW)"]                 = _cell("Solar",     "B", 7, 1000)
    data["Solar (MW)"]                           = _cell("Solar",     "B", 8, 1000)
    data["Solar (rooftop) (MW)"]                 = _cell("Solar",     "B", 9, 1000)
    data["Solar (thermal_with_storage) (MW)"]    = _cell("Solar",     "B", 10, 1000)
    data["Solar (thermal_with_storage) (MWh)"]   = _cell("Solar",     "B", 11, 1000)
    for _i, _col in enumerate(_OTHER_NONRES_COLS):
        data[f"Other Non-RES{_i+1} (MW)"] = _cell("Other Non-RES", _col, 8)
    data["Other RES (biomass) (MW)"]             = _cell("Other RES", "E", 8)
    data["Other RES (geothermal) (MW)"]          = _cell("Other RES", "F", 8)
    data["Other RES (marine) (MW)"]              = _cell("Other RES", "G", 8)
    data["Other RES (waste) (MW)"]               = _cell("Other RES", "H", 8)
    data["Other RES (unknown) (MW)"]             = _cell("Other RES", "I", 8)
    dsr_mask = _dsr_climate_year_mask(filepath, _dsr_col_count(filepath), climate_year)
    for _i, _col in enumerate(_dsr_cols(n_dsr)):
        data[f"DSR{_i+1} (MW)"] = _cell("DSR", _col, 8) if (_i >= len(dsr_mask) or dsr_mask[_i]) else 0.0


def _read_storage_capacities(filepath: str, data: dict) -> None:
    def _cell(sheet: str, col: str, row: int) -> float:
        return _read_scalar(filepath, sheet, col, row)

    data["Battery (MWh)"]      = _cell("Battery",     "E", 11)
    data["Electrolyser (MW)"]  = _cell("Electrolyser", "C", 11)
    data["Electrolyser (MWh)"] = _cell("Electrolyser", "F", 11)


def _read_timeseries_capacities(filepath: str, data: dict, selected_hours: int,
                                n_dsr: int = DSR_DEFAULT_COUNT,
                                climate_year: int | None = None) -> None:
    _zeros = lambda: np.zeros((selected_hours, 1))

    def _block(sheet: str, first: str, last: str, row: int) -> pd.DataFrame:
        try:
            return pd.read_excel(
                _excel(filepath), sheet_name=sheet, usecols=f"{first}:{last}",
                header=None, skiprows=row, nrows=selected_hours,
            )
        except Exception:
            return pd.DataFrame()

    def _one(sheet: str, col: str, row: int) -> np.ndarray:
        try:
            return pd.read_excel(
                _excel(filepath), sheet_name=sheet, usecols=col, header=None,
                skiprows=row, nrows=selected_hours,
            ).to_numpy()
        except Exception:
            return _zeros()

    def _assign(df: pd.DataFrame, i: int) -> np.ndarray:
        return df.iloc[:, i:i + 1].to_numpy() if i < df.shape[1] else _zeros()

    onr = _block("Other Non-RES", "C", _OTHER_NONRES_COLS[-1], 18)
    for _i in range(len(_OTHER_NONRES_COLS)):
        data[f"Other Non-RES{_i+1} (MW/h)"] = _assign(onr, _i)

    data["Exports_non_ENTSOe (MW/h)"] = -_one("Exchanges", "C", 28)

    _w = _dsr_col_count(filepath)
    dsr = _block("DSR", "C", get_column_letter(2 + _w), 15) if _w > 0 else pd.DataFrame()
    dsr_mask = _dsr_climate_year_mask(filepath, _w, climate_year)
    for _i in range(n_dsr):
        data[f"DSR{_i+1} (MW/h)"] = (
            _assign(dsr, _i) if (_i >= len(dsr_mask) or dsr_mask[_i]) else _zeros()
        )

    ores = _block("Other RES", "E", "I", 10)
    for _i, _nm in enumerate(("biomass", "geothermal", "marine", "waste", "unknown")):
        data[f"Other RES ({_nm}) (MW/h)"] = _assign(ores, _i)


def load_tech_characteristics(
    node_df: pd.DataFrame,
    selected_zones: list[str],
    scenario: int,
    climate_year: int | None = None,
) -> pd.DataFrame:
    co2_col = get_co2_usecols(scenario)
    n_dsr = _dsr_count_for(selected_zones, scenario)
    tech_char_rows: list[dict] = []

    for code in node_df["Code"]:
        if code not in selected_zones:
            continue
        filepath = get_pemmdb_filepath(code, scenario)
        try:
            data_char = _read_single_zone_characteristics(filepath, co2_col, code, n_dsr, climate_year)
            tech_char_rows.append(data_char)
            print(f"Technology characteristics for {code}: OK")
        except FileNotFoundError:
            print(f"Technology characteristics for {code}: file not found – skipped")

    return pd.DataFrame(tech_char_rows, columns=TECH_CHAR_COLUMNS)


def _read_single_zone_characteristics(
    filepath: str, co2_col: str, code: str, n_dsr: int = DSR_DEFAULT_COUNT,
    climate_year: int | None = None,
) -> dict:
    def _arr(col: str, row: int, nrows: int = 52) -> np.ndarray:
        try:
            return pd.read_excel(
                _excel(filepath), sheet_name="Thermal", usecols=col, header=None,
                skiprows=row, nrows=nrows,
            ).to_numpy()
        except Exception:
            return np.empty((0, 1))

    def _cell(filepath_: str, sheet: str, col: str, row: int) -> object:
        return _read_scalar(filepath_, sheet, col, row)

    def _reorder(arr: np.ndarray) -> np.ndarray:
        return arr[_THERMAL_SHEET_ROW_ORDER] if len(arr) == 26 else arr

    dc: dict = {"Code": code}

    raw = _arr("D", 11); dc["Number of Units"]                  = _reorder(raw[~np.isnan(raw.astype(float))])
    raw = _arr("E", 11); dc["Number of Biofuel Units"]          = _reorder(raw[~np.isnan(raw.astype(float))])
    raw = _arr("F", 11); dc["Biofuel Usage (%)"]                = _reorder(raw[~np.isnan(raw.astype(float))])
    raw = _arr("H:S", 11)
    dc["Must Run (Number of units)"] = _reorder(raw[::2])
    dc["Must Run (%)"]               = _reorder(raw[1::2])
    raw = _arr("AG", 11); dc["Annual Forced Outage (%)"]        = _reorder(raw[~np.isnan(raw.astype(float))])
    raw = _arr("AH", 11); dc["Annual Forced Outage (Days)"]     = _reorder(raw[~np.isnan(raw.astype(float))])
    raw = _arr("AI", 11); dc["Annual Forced Outage in Winter (%)"] = _reorder(raw[~np.isnan(raw.astype(float))])
    raw = _arr("AJ", 11); dc["Minimum Stable Power (%)"]        = _reorder(raw[~np.isnan(raw.astype(float))])
    raw = _arr("AK", 11); dc["Ramp-Up Rate (MW/h)"]             = _reorder(raw[~np.isnan(raw.astype(float))])
    raw = _arr("AL", 11); dc["Ramp-Down Rate (MW/h)"]           = _reorder(raw[~np.isnan(raw.astype(float))])
    raw = _arr("AM", 11); dc["Fixed Generation Reduction (%)"]  = _reorder(raw[~np.isnan(raw.astype(float))])
    raw = _arr("AP", 11); dc["Maximum Number of Units in Maintenace"] = _reorder(raw[~np.isnan(raw.astype(float))])

    co2_raw = pd.read_excel(
        _excel(FILEPATH_CO2_FACTORS), sheet_name="CO2 emission factor",
        usecols=co2_col, header=None, skiprows=4, nrows=26,
    ).to_numpy()
    dc["CO2 Factor (ton/MWh)"] = co2_raw * 0.0036
    eff_raw = pd.read_excel(
        _excel(FILEPATH_COMMON_DATA), sheet_name="Common Data", usecols="F",
        header=None, skiprows=14, nrows=26,
    ).to_numpy()
    dc["Efficiency (%)"] = eff_raw
    price_raw = pd.read_excel(
        _excel(FILEPATH_COMMON_DATA), sheet_name="Common Data", usecols="H",
        header=None, skiprows=14, nrows=26,
    ).to_numpy()
    dc["Price (EUR/MWh)"] = price_raw

    minup_raw = pd.read_excel(
        _excel(FILEPATH_COMMON_DATA), sheet_name="Common Data", usecols="I",
        header=None, skiprows=14, nrows=26,
    ).to_numpy()
    dc["Minimum Up Time (h)"] = minup_raw
    mindown_raw = pd.read_excel(
        _excel(FILEPATH_COMMON_DATA), sheet_name="Common Data", usecols="J",
        header=None, skiprows=14, nrows=26,
    ).to_numpy()
    dc["Minimum Down Time (h)"] = mindown_raw
    sufuel_raw = pd.read_excel(
        _excel(FILEPATH_COMMON_DATA), sheet_name="Common Data", usecols="K",
        header=None, skiprows=14, nrows=26,
    ).to_numpy()
    dc["Start-up Fuel Consumption (GJ/MW)"] = sufuel_raw
    sucost_raw = pd.read_excel(
        _excel(FILEPATH_COMMON_DATA), sheet_name="Common Data", usecols="L",
        header=None, skiprows=14, nrows=26,
    ).to_numpy()
    dc["Start-up Fix Cost (EUR/MW)"] = sucost_raw

    zeros26 = np.zeros(26)
    dc["Net maximum capacity - generation perspective (MW)"] = zeros26.copy()
    dc["Net maximum capacity - demand perspective (MW)"]     = zeros26.copy()
    dc["Number of Hours (h)"] = zeros26.copy()

    for _col in _OTHER_NONRES_COLS:
        for key in ("Fixed Generation Reduction (%)", "Ramp-Up Rate (MW/h)", "Ramp-Down Rate (MW/h)"):
            dc[key] = np.append(dc[key], 0)
        dc["Number of Units"]   = np.append(dc["Number of Units"],   _cell(filepath, "Other Non-RES", _col, 9))
        dc["Price (EUR/MWh)"]   = np.append(dc["Price (EUR/MWh)"],   _cell(filepath, "Other Non-RES", _col, 12))
        dc["Efficiency (%)"]    = np.append(dc["Efficiency (%)"],    _cell(filepath, "Other Non-RES", _col, 13))
        dc["CO2 Factor (ton/MWh)"] = np.append(dc["CO2 Factor (ton/MWh)"], _cell(filepath, "Other Non-RES", _col, 14))
        dc["Net maximum capacity - generation perspective (MW)"] = np.append(dc["Net maximum capacity - generation perspective (MW)"], 0)
        dc["Net maximum capacity - demand perspective (MW)"]     = np.append(dc["Net maximum capacity - demand perspective (MW)"], 0)
        dc["Number of Hours (h)"] = np.append(dc["Number of Hours (h)"], 0)
        for key in ("Minimum Up Time (h)", "Minimum Down Time (h)",
                    "Start-up Fuel Consumption (GJ/MW)", "Start-up Fix Cost (EUR/MW)"):
            dc[key] = np.append(dc[key], 0)

    dsr_mask = _dsr_climate_year_mask(filepath, _dsr_col_count(filepath), climate_year)
    for _i, _col in enumerate(_dsr_cols(n_dsr)):
        _included = _i >= len(dsr_mask) or dsr_mask[_i]
        for key in ("Fixed Generation Reduction (%)", "Ramp-Up Rate (MW/h)", "Ramp-Down Rate (MW/h)"):
            dc[key] = np.append(dc[key], 0)
        dc["Number of Units"] = np.append(dc["Number of Units"], _cell(filepath, "DSR", _col, 9) if _included else 0)
        dc["Price (EUR/MWh)"] = np.append(dc["Price (EUR/MWh)"], _cell(filepath, "DSR", _col, 11) if _included else 0)
        dc["Efficiency (%)"]  = np.append(dc["Efficiency (%)"], 0)
        dc["CO2 Factor (ton/MWh)"] = np.append(dc["CO2 Factor (ton/MWh)"], 0)
        dc["Net maximum capacity - generation perspective (MW)"] = np.append(dc["Net maximum capacity - generation perspective (MW)"], 0)
        dc["Net maximum capacity - demand perspective (MW)"]     = np.append(dc["Net maximum capacity - demand perspective (MW)"], 0)
        dc["Number of Hours (h)"] = np.append(dc["Number of Hours (h)"], _cell(filepath, "DSR", _col, 10) if _included else 0)
        for key in ("Minimum Up Time (h)", "Minimum Down Time (h)",
                    "Start-up Fuel Consumption (GJ/MW)", "Start-up Fix Cost (EUR/MW)"):
            dc[key] = np.append(dc[key], 0)

    # Battery
    dc["Fixed Generation Reduction (%)"] = np.append(dc["Fixed Generation Reduction (%)"], 0)
    dc["Ramp-Up Rate (MW/h)"]   = np.append(dc["Ramp-Up Rate (MW/h)"],   _cell(filepath, "Battery", "H", 11))
    dc["Ramp-Down Rate (MW/h)"] = np.append(dc["Ramp-Down Rate (MW/h)"], _cell(filepath, "Battery", "I", 11))
    dc["Number of Units"] = np.append(dc["Number of Units"], _cell(filepath, "Battery", "F", 11))
    dc["Price (EUR/MWh)"] = np.append(dc["Price (EUR/MWh)"], 0)
    dc["Efficiency (%)"]  = np.append(dc["Efficiency (%)"],  _cell(filepath, "Battery", "G", 11))
    dc["CO2 Factor (ton/MWh)"] = np.append(dc["CO2 Factor (ton/MWh)"], 0)
    dc["Net maximum capacity - generation perspective (MW)"] = np.append(dc["Net maximum capacity - generation perspective (MW)"], _cell(filepath, "Battery", "C", 11))
    dc["Net maximum capacity - demand perspective (MW)"]     = np.append(dc["Net maximum capacity - demand perspective (MW)"], _cell(filepath, "Battery", "D", 11))
    dc["Number of Hours (h)"] = np.append(dc["Number of Hours (h)"], 0)
    for key in ("Minimum Up Time (h)", "Minimum Down Time (h)",
                "Start-up Fuel Consumption (GJ/MW)", "Start-up Fix Cost (EUR/MW)"):
        dc[key] = np.append(dc[key], 0)

    # Electrolyser
    dc["Fixed Generation Reduction (%)"] = np.append(dc["Fixed Generation Reduction (%)"], _cell(filepath, "Electrolyser", "I", 11))
    dc["Ramp-Up Rate (MW/h)"]   = np.append(dc["Ramp-Up Rate (MW/h)"],   _cell(filepath, "Electrolyser", "G", 11))
    dc["Ramp-Down Rate (MW/h)"] = np.append(dc["Ramp-Down Rate (MW/h)"], _cell(filepath, "Electrolyser", "H", 11))
    dc["Number of Units"] = np.append(dc["Number of Units"], _cell(filepath, "Electrolyser", "D", 11))
    dc["Price (EUR/MWh)"] = np.append(dc["Price (EUR/MWh)"], 0)
    dc["Efficiency (%)"]  = np.append(dc["Efficiency (%)"],  _cell(filepath, "Electrolyser", "E", 11))
    dc["CO2 Factor (ton/MWh)"] = np.append(dc["CO2 Factor (ton/MWh)"], 0)
    dc["Net maximum capacity - generation perspective (MW)"] = np.append(dc["Net maximum capacity - generation perspective (MW)"], 0)
    dc["Net maximum capacity - demand perspective (MW)"]     = np.append(dc["Net maximum capacity - demand perspective (MW)"], 0)
    dc["Number of Hours (h)"] = np.append(dc["Number of Hours (h)"], 0)
    for key in ("Minimum Up Time (h)", "Minimum Down Time (h)",
                "Start-up Fuel Consumption (GJ/MW)", "Start-up Fix Cost (EUR/MW)"):
        dc[key] = np.append(dc[key], 0)

    return dc


def load_reserve_requirements(
    node_df: pd.DataFrame,
    selected_zones: list[str],
    scenario: int,
) -> pd.DataFrame:
    rows: list[dict] = []
    for code in node_df["Code"]:
        if code not in selected_zones:
            continue
        filepath = get_pemmdb_filepath(code, scenario)
        try:
            def _cell(row: int) -> float:
                return _read_scalar(filepath, "Reserves", "C", row)

            rows.append({
                "Code":                  code,
                "Total (FCR) (MW/h)":    _cell(9),
                "Thermal (FCR) (MW/h)":  _cell(10),
                "Hydro (FCR) (MW/h)":    _cell(11),
                "Total (FRR) (MW/h)":    _cell(15),
                "Thermal (FRR) (MW/h)":  _cell(16),
                "Hydro (FRR) (MW/h)":    _cell(17),
            })
            print(f"Reserve requirements for {code}: OK")
        except FileNotFoundError:
            print(f"Reserve requirements for {code}: file not found – skipped")

    return pd.DataFrame(rows, columns=RESERVE_COLUMNS)


# Cross-border exchange results loader


def load_crossborder_exchanges(
    scenario: int,
    selected_hours: int,
    filtered_edges_e_df: pd.DataFrame,
    selected_zones: list[str],
) -> pd.DataFrame:
    filepath = f"inputs/MMStandardOutputFile_NT{scenario}_Plexos_CY2009_2.5_v40.xlsx"
    unique_nodes = pd.unique(
        pd.concat([
            filtered_edges_e_df["Start_Node"],
            filtered_edges_e_df["End_Node"],
        ]).astype(str)
    )
    unique_nodes_no_selected = [n for n in unique_nodes if n not in [str(z) for z in selected_zones]]

    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
    ws = wb["Crossborder exchanges"]

    header_row = 11
    headers: list[tuple[int, str]] = []
    col_idx = 3
    while True:
        val = ws.cell(row=header_row, column=col_idx).value
        if val is None or str(val).strip() == "":
            break
        headers.append((col_idx, str(val).strip()))
        col_idx += 1

    specs: list[tuple[int, str, str]] = []
    for col, header in headers:
        for zone in selected_zones:
            zone_str = str(zone)
            if header.startswith(f"{zone_str}->"):
                node = header.split("->", 1)[1]
                direction = "from"
            elif header.endswith(f"->{zone_str}"):
                node = header.split("->", 1)[0]
                direction = "to"
            else:
                continue
            if str(node).startswith("X"):
                name = f"Exports_{zone_str}_XX (MW/h)"
            elif node in unique_nodes_no_selected:
                name = f"Exports_{zone_str}_{node} (MW/h)"
            else:
                continue
            specs.append((col, name, direction))

    row_start = header_row + 1
    row_end = row_start + selected_hours
    col_data: dict[int, list] = {}
    for col in sorted({c for c, _, _ in specs}):
        col_data[col] = [
            v[0] for v in ws.iter_rows(
                min_row=row_start, max_row=row_end - 1,
                min_col=col, max_col=col, values_only=True,
            )
        ]

    wb.close()

    export_df_dict: dict[str, list] = {}
    for col, name, direction in specs:
        raw = col_data[col]
        values = raw if direction == "from" else [-v if v is not None else None for v in raw]
        if name in export_df_dict:
            export_df_dict[name] = [(a or 0) + (b or 0) for a, b in zip(export_df_dict[name], values)]
        else:
            export_df_dict[name] = values

    return pd.DataFrame(export_df_dict)


def load_crossborder_h2_exchanges(
    scenario: int,
    selected_hours: int,
    selected_zones: list[str],
    main_zone_map: dict[str, str],
) -> pd.DataFrame:
    filepath = f"inputs/MMStandardOutputFile_NT{scenario}_Plexos_CY2009_2.5_v40.xlsx"
    selected_countries = {str(z)[:2] for z in selected_zones}

    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
    if "Crossborder H2 exchanges" not in wb.sheetnames:
        wb.close()
        return pd.DataFrame()
    ws = wb["Crossborder H2 exchanges"]

    header_row = 11
    headers: list[tuple[int, str]] = []
    col_idx = 3
    while True:
        val = ws.cell(row=header_row, column=col_idx).value
        if val is None or str(val).strip() == "":
            break
        headers.append((col_idx, str(val).strip()))
        col_idx += 1

    def _cc(node: str) -> str:
        n = str(node).strip()
        return n[:-3] if n.endswith("_H2") else n

    def _is_hub(node: str) -> bool:
        return str(node).startswith("IB") and str(node).endswith("_H2")

    hub_sinks: dict[str, list[str]] = {}
    for _, header in headers:
        if "->" not in header:
            continue
        left, right = [p.strip() for p in header.split("->", 1)]
        if _is_hub(left) and not _is_hub(right):
            hub_sinks.setdefault(left, []).append(right)

    edges: list[tuple[str, str, int]] = []
    for col, header in headers:
        if "->" not in header:
            continue
        left, right = [p.strip() for p in header.split("->", 1)]
        if _is_hub(left):
            continue
        if _is_hub(right):
            for sink in hub_sinks.get(right, []):
                edges.append((left, sink, col))
        else:
            edges.append((left, right, col))

    specs: list[tuple[int, str, str]] = []
    for left, right, col in edges:
        xc, yc = _cc(left), _cc(right)
        if xc in selected_countries and yc not in selected_countries:
            interested, neigh_raw, neigh_cc, direction = xc, right, yc, "from"
        elif yc in selected_countries and xc not in selected_countries:
            interested, neigh_raw, neigh_cc, direction = yc, left, xc, "to"
        else:
            continue
        main = main_zone_map.get(interested, f"{interested}00")
        if str(neigh_raw).startswith("X"):
            name = f"H2Exports_{main}_XX (MW/h)"
        elif str(neigh_raw).endswith("_H2"):
            name = f"H2Exports_{main}_{neigh_cc}00 (MW/h)"
        else:
            name = f"H2Exports_{main}_{neigh_raw} (MW/h)"
        specs.append((col, name, direction))

    row_start = header_row + 1
    row_end = row_start + selected_hours
    col_data: dict[int, list] = {}
    for col in sorted({c for c, _, _ in specs}):
        col_data[col] = [
            v[0] for v in ws.iter_rows(
                min_row=row_start, max_row=row_end - 1,
                min_col=col, max_col=col, values_only=True,
            )
        ]

    smr_by_main: dict[str, list] = {}
    discharge_by_main: dict[str, list] = {}
    charge_by_main: dict[str, list] = {}
    if "Hourly H2 Data" in wb.sheetnames:
        sws = wb["Hourly H2 Data"]
        smr_data_start = 14
        c = 3
        while c < 3000:
            cat = sws.cell(row=11, column=c).value
            ctry = sws.cell(row=12, column=c).value
            if cat is None and ctry is None:
                break
            if cat and ctry:
                cat_s = str(cat)
                target = None
                if "Steam methane reformer" in cat_s:
                    target = smr_by_main
                elif "H2 storage discharge" in cat_s:
                    target = discharge_by_main
                elif "H2 storage charge" in cat_s:
                    target = charge_by_main
                if target is not None:
                    cc = str(ctry)[:-3] if str(ctry).endswith("_H2") else str(ctry)
                    if cc in selected_countries:
                        main = main_zone_map.get(cc, f"{cc}00")
                        target[main] = [
                            v[0] for v in sws.iter_rows(
                                min_row=smr_data_start,
                                max_row=smr_data_start + selected_hours - 1,
                                min_col=c, max_col=c, values_only=True,
                            )
                        ]
            c += 1

    wb.close()

    out: dict[str, list] = {}
    for col, name, direction in specs:
        raw = col_data[col]
        values = raw if direction == "from" else [(-v if v is not None else None) for v in raw]
        if name in out:
            out[name] = [(a or 0) + (b or 0) for a, b in zip(out[name], values)]
        else:
            out[name] = values

    # Net credit at the "XX" (unmodeled/rest-of-world) bucket: SMR and storage
    # discharge behave as extra supply (subtract from required import), while
    # storage charge behaves as extra consumption (add to required import).
    mains = set(smr_by_main) | set(discharge_by_main) | set(charge_by_main)
    for main in mains:
        smr = smr_by_main.get(main)
        discharge = discharge_by_main.get(main)
        charge = charge_by_main.get(main)
        n = len(smr or discharge or charge or [])
        credit = [
            (charge[i] or 0 if charge else 0)
            - (discharge[i] or 0 if discharge else 0)
            - (smr[i] or 0 if smr else 0)
            for i in range(n)
        ]
        name = f"H2Exports_{main}_XX (MW/h)"
        if name in out:
            out[name] = [(a or 0) + b for a, b in zip(out[name], credit)]
        else:
            out[name] = credit

    return pd.DataFrame(out)


# PLEXOS market-model result overrides
#
# load_plexos_h2_demand_profiles is an optional override used only when the
# "Data Correction" option is enabled. load_plexos_wind_offshore_cf backs an
# always-on base-pipeline fix (PECD has no offshore wind file at all for some
# zones, e.g. BEOF) and runs regardless of that option.


def load_plexos_h2_demand_profiles(
    node_df: pd.DataFrame,
    selected_zones: list[str],
    scenario: int,
    selected_hours: int,
) -> dict[str, list[dict]]:
    filepath = f"inputs/MMStandardOutputFile_NT{scenario}_Plexos_CY2009_2.5_v40.xlsx"
    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
    ws = wb["Hourly H2 Data"]
    rows = list(ws.iter_rows(values_only=True))
    cat, ctry = rows[10], rows[11]
    dem_col: dict[str, int] = {}
    for c in range(2, len(cat)):
        if cat[c] and str(cat[c]).startswith("Demand") and ctry[c]:
            cc = str(ctry[c])[:-3] if str(ctry[c]).endswith("_H2") else str(ctry[c])
            dem_col[cc] = c
    series: dict[str, np.ndarray] = {cc: np.zeros(selected_hours) for cc in dem_col}
    for i, rw in enumerate(rows[13:13 + selected_hours]):
        for cc, c in dem_col.items():
            v = rw[c]
            if isinstance(v, (int, float)):
                series[cc][i] = v
    wb.close()

    results: list[dict] = []
    for code in node_df["Code"]:
        if code not in selected_zones:
            continue
        data = series.get(str(code)[:2], np.zeros(selected_hours))
        results.append({"Code": code, "Year": None, "Data": np.asarray(data, dtype=float)})
    return {"Hydrogen Demand Profile": results}


def load_plexos_wind_offshore_cf(
    tech_cap_df: pd.DataFrame,
    scenario: int,
    selected_hours: int,
    zones: list[str],
) -> dict[str, list[dict]]:
    filepath = f"inputs/MMStandardOutputFile_NT{scenario}_Plexos_CY2009_2.5_v40.xlsx"
    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
    ws = wb["Hourly Market Data"]
    rows = list(ws.iter_rows(values_only=True))
    cat, ctry = rows[10], rows[11]
    gen_col: dict[str, int] = {}
    for c in range(2, len(cat)):
        if cat[c] and str(cat[c]).strip() == "Wind Offshore [MW]" and ctry[c] in zones:
            gen_col[str(ctry[c])] = c
    series: dict[str, np.ndarray] = {z: np.zeros(selected_hours) for z in gen_col}
    for i, rw in enumerate(rows[13:13 + selected_hours]):
        for z, c in gen_col.items():
            v = rw[c]
            if isinstance(v, (int, float)):
                series[z][i] = v
    wb.close()

    cap_by_zone = dict(zip(tech_cap_df["Code"], tech_cap_df["Wind (offshore) (MW)"]))

    results: list[dict] = []
    for z, gen in series.items():
        cap = cap_by_zone.get(z, 0.0)
        cf = gen / cap if cap else np.zeros(selected_hours)
        results.append({"Code": z, "Year": None, "Data": np.asarray(cf, dtype=float)})
    return {"Wind_Offshore Profile": results}


# Demand profile loaders


def load_electricity_demand_profiles(
    node_df: pd.DataFrame,
    selected_zones: list[str],
    scenario: int,
    climate_year: int,
    selected_hours: int,
) -> dict[str, list[dict]]:
    if scenario == 2050:
        raise FileNotFoundError("Electricity demand profiles are not available for scenario 2050")

    paths = {
        2030: r"inputs/Demand Profiles/NT/Electricity demand profiles/2030_National Trends.xlsx",
        2040: r"inputs/Demand Profiles/NT/Electricity demand profiles/2040_National Trends.xlsx",
    }
    sheet_year_row = 6
    results: list[dict] = []

    for code in node_df["Code"]:
        if code not in selected_zones:
            continue
        entry = _load_excel_demand_profile(
            filepath=paths[scenario],
            code=code,
            climate_year=climate_year,
            selected_hours=selected_hours,
            sheet_year_row=sheet_year_row,
            profile_key="Electricity Demand Profile",
        )
        results.append(entry)

    return {"Electricity Demand Profile": results}


def load_hydrogen_demand_profiles(
    node_df: pd.DataFrame,
    selected_zones: list[str],
    scenario: int,
    climate_year: int,
    selected_hours: int,
) -> dict[str, list[dict]]:
    if scenario == 2050:
        raise FileNotFoundError("Hydrogen demand profiles are not available for scenario 2050")

    paths = {
        2030: r"inputs\Demand Profiles\NT\H2 demand profiles\H2 2030\NT_2030.xlsx",
        2040: r"inputs\Demand Profiles\NT\H2 demand profiles\H2 2040\NT_2040.xlsx",
    }
    sheet_year_row = 9
    results: list[dict] = []

    try:
        _h2_sheets = set(_excel(paths[scenario]).sheet_names)
    except Exception:
        _h2_sheets = set()
    country_zones: dict[str, list[str]] = {}
    for z in node_df["Code"]:
        country_zones.setdefault(str(z)[:2], []).append(str(z))

    def _h2_sheet_for(prefix: str) -> str | None:
        for cand in country_zones.get(prefix, []) + [f"{prefix}00"]:
            if cand in _h2_sheets:
                return cand
        return None

    _sheet_cache: dict[str, str | None] = {}
    for code in node_df["Code"]:
        if code not in selected_zones:
            continue
        pref = str(code)[:2]
        if pref not in _sheet_cache:
            _sheet_cache[pref] = _h2_sheet_for(pref)
        h2_sheet = _sheet_cache[pref]
        if h2_sheet is None:
            results.append({"Code": code, "Year": climate_year,
                            "Data": np.zeros(selected_hours)})
            continue
        entry = _load_excel_demand_profile(
            filepath=paths[scenario],
            code=h2_sheet,
            climate_year=climate_year,
            selected_hours=selected_hours,
            sheet_year_row=sheet_year_row,
            profile_key="Hydrogen Demand Profile",
        )
        entry["Code"] = code
        results.append(entry)

    return {"Hydrogen Demand Profile": results}


def load_gas_demand_profiles(
    node_df: pd.DataFrame,
    selected_zones: list[str],
    climate_year: int,
    selected_hours: int,
) -> dict[str, list[dict]]:
    results: list[dict] = []
    for code in node_df["Code"]:
        if code not in selected_zones:
            continue
        results.append({"Code": code, "Year": climate_year, "Data": np.zeros(selected_hours)})
        print(f"Gas demand (zero placeholder) for {code}: recorded")
    return {"Gas Demand Profile": results}


def _load_excel_demand_profile(
    filepath: str,
    code: str,
    climate_year: int,
    selected_hours: int,
    sheet_year_row: int,
    profile_key: str,
) -> dict:
    try:
        df = pd.read_excel(filepath, sheet_name=code, header=0)
    except (ValueError, FileNotFoundError):
        print(f"{profile_key} – worksheet '{code}' not found in {filepath}")
        return {"Code": code, "Year": 0, "Data": np.zeros(selected_hours)}

    if df.shape[0] <= sheet_year_row:
        return {"Code": code, "Year": climate_year, "Data": np.zeros(selected_hours)}

    year_row = df.iloc[sheet_year_row]
    col_idx = None
    for idx, val in zip(year_row.index[::-1], year_row.iloc[::-1]):
        if isinstance(val, (int, float)) and not pd.isna(val) and int(val) == climate_year:
            col_idx = idx
            break

    if col_idx is None:
        print(f"{profile_key} – climate year {climate_year} not found for {code}")
        return {"Code": code, "Year": climate_year, "Data": np.zeros(selected_hours)}

    data_start = sheet_year_row + 1
    profile_col = df.columns.get_loc(col_idx)
    raw = df.iloc[data_start: data_start + selected_hours, profile_col]
    arr = pd.to_numeric(raw, errors="coerce").to_numpy()
    if arr.shape[0] < selected_hours:
        arr = np.pad(arr, (0, selected_hours - arr.shape[0]), constant_values=np.nan)

    print(f"{profile_key} for {code}: OK")
    return {"Code": code, "Year": climate_year, "Data": arr}


# Generic PECD CSV profile loader


def _resolve_pecd_path(file_template: str, code: str) -> str | None:
    exact = file_template.format(code)
    if os.path.exists(exact):
        return exact
    pattern = re.sub(r"edition [\d.]+\.csv$", "edition *.csv", exact)
    matches = glob.glob(pattern)
    return matches[0] if matches else None


def _load_pecd_csv_profiles(
    node_df: pd.DataFrame,
    selected_zones: list[str],
    scenario: int,
    climate_year: int,
    selected_hours: int,
    profile_key: str,
    year_row_idx: int = 9,
    target_len: int | None = None,
) -> list[dict]:
    if target_len is None:
        target_len = selected_hours

    file_template = PECD_FILE_TEMPLATES[profile_key][scenario]
    results: list[dict] = []

    for code in node_df["Code"]:
        if code not in selected_zones:
            continue
        path = _resolve_pecd_path(file_template, code)
        if path is None:
            print(f"{profile_key} for {code}: file not found – zeros used")
            results.append({"Code": code, "Year": 0, "Data": np.zeros(target_len)})
            continue
        df = pd.read_csv(path, header=0)

        col_idx = None
        if df.shape[0] > year_row_idx:
            year_row = df.iloc[year_row_idx]
            for idx, val in zip(year_row.index[::-1], year_row.iloc[::-1]):
                if isinstance(val, (int, float)) and not pd.isna(val) and int(val) == climate_year:
                    col_idx = idx
                    break

        if col_idx is None:
            print(f"{profile_key} for {code}: climate year {climate_year} not found – zeros used")
            results.append({"Code": code, "Year": climate_year, "Data": np.zeros(target_len)})
            continue

        data_start = year_row_idx + 1
        profile_col = df.columns.get_loc(col_idx)
        raw = df.iloc[data_start: data_start + target_len, profile_col]
        arr = pd.to_numeric(raw, errors="coerce").to_numpy()
        if arr.shape[0] < target_len:
            arr = np.pad(arr, (0, target_len - arr.shape[0]), constant_values=np.nan)

        results.append({"Code": code, "Year": climate_year, "Data": arr})
        print(f"{profile_key} for {code}: OK")

    return results


# Named PECD profile loaders (thin wrappers)


def load_csp_no_storage_profiles(
    node_df: pd.DataFrame, selected_zones: list[str],
    scenario: int, climate_year: int, selected_hours: int,
) -> dict[str, list[dict]]:
    key = "CSP_noStorage Profile"
    return {key: _load_pecd_csv_profiles(node_df, selected_zones, scenario, climate_year, selected_hours, key)}


def load_csp_dispatch_profiles(
    node_df: pd.DataFrame, selected_zones: list[str],
    scenario: int, climate_year: int, selected_hours: int,
) -> dict[str, list[dict]]:
    key = "CSP_withStorage_D Profile"
    return {key: _load_pecd_csv_profiles(node_df, selected_zones, scenario, climate_year, selected_hours, key)}


def load_csp_predispatch_profiles(
    node_df: pd.DataFrame, selected_zones: list[str],
    scenario: int, climate_year: int, selected_hours: int,
) -> dict[str, list[dict]]:
    key = "CSP_withStorage_PreD Profile"
    return {key: _load_pecd_csv_profiles(node_df, selected_zones, scenario, climate_year, selected_hours, key)}


def load_solar_profiles(
    node_df: pd.DataFrame, selected_zones: list[str],
    scenario: int, climate_year: int, selected_hours: int,
) -> dict[str, list[dict]]:
    key = "Solar Profile"
    return {key: _load_pecd_csv_profiles(node_df, selected_zones, scenario, climate_year, selected_hours, key)}


def load_solar_rooftop_profiles(
    node_df: pd.DataFrame, selected_zones: list[str],
    scenario: int, climate_year: int, selected_hours: int,
) -> dict[str, list[dict]]:
    key = "Solar_Rooftop Profile"
    return {key: _load_pecd_csv_profiles(
        node_df, selected_zones, scenario, climate_year, selected_hours, key,
        target_len=SOLAR_ROOFTOP_TARGET_LEN,
    )}


def load_solar_utility_profiles(
    node_df: pd.DataFrame, selected_zones: list[str],
    scenario: int, climate_year: int, selected_hours: int,
) -> dict[str, list[dict]]:
    key = "Solar_Utility Profile"
    return {key: _load_pecd_csv_profiles(node_df, selected_zones, scenario, climate_year, selected_hours, key)}


def load_wind_offshore_profiles(
    node_df: pd.DataFrame, selected_zones: list[str],
    scenario: int, climate_year: int, selected_hours: int,
) -> dict[str, list[dict]]:
    key = "Wind_Offshore Profile"
    return {key: _load_pecd_csv_profiles(node_df, selected_zones, scenario, climate_year, selected_hours, key)}


def load_wind_onshore_profiles(
    node_df: pd.DataFrame, selected_zones: list[str],
    scenario: int, climate_year: int, selected_hours: int,
) -> dict[str, list[dict]]:
    key = "Wind_Onshore Profile"
    return {key: _load_pecd_csv_profiles(node_df, selected_zones, scenario, climate_year, selected_hours, key)}


# Generic hydro inflow loader


def _load_hydro_inflow_profiles(
    node_df: pd.DataFrame,
    selected_zones: list[str],
    scenario: int,
    climate_year: int,
    profile_key: str,
    scale_factor: float = HYDRO_SCALE_FACTOR,
) -> list[dict]:
    file_template = HYDRO_FILE_TEMPLATES[scenario]
    sheet_name = HYDRO_SHEET_NAMES[profile_key]
    target_len = HYDRO_TARGET_LENGTHS[profile_key]
    results: list[dict] = []

    for code in node_df["Code"]:
        if code not in selected_zones:
            continue
        path = file_template.format(code)
        try:
            df = pd.read_excel(_excel(path), header=0, sheet_name=sheet_name)
        except FileNotFoundError:
            print(f"{profile_key} for {code}: file not found – zeros used")
            results.append({"Code": code, "Year": 0, "Data": np.zeros(target_len)})
            continue

        year_row = df.iloc[0]
        col_idx = None
        for idx, val in zip(year_row.index[::-1], year_row.iloc[::-1]):
            if isinstance(val, (int, float)) and not pd.isna(val) and int(val) == climate_year:
                col_idx = idx
                break

        if col_idx is None:
            print(f"{profile_key} for {code}: climate year {climate_year} not found – zeros used")
            results.append({"Code": code, "Year": climate_year, "Data": np.zeros(target_len)})
            continue

        profile_col = df.columns.get_loc(col_idx)
        raw = df.iloc[1: 1 + target_len, profile_col]
        arr = pd.to_numeric(raw, errors="coerce").to_numpy()
        if arr.shape[0] < target_len:
            arr = np.pad(arr, (0, target_len - arr.shape[0]), constant_values=np.nan)

        results.append({"Code": code, "Year": climate_year, "Data": arr * scale_factor})
        print(f"{profile_key} for {code}: OK")

    return results


# Named hydro inflow loaders (thin wrappers)


def load_river_flow_profiles(
    node_df: pd.DataFrame, selected_zones: list[str],
    scenario: int, climate_year: int,
) -> dict[str, list[dict]]:
    key = "River Flow Energy"
    return {key: _load_hydro_inflow_profiles(node_df, selected_zones, scenario, climate_year, key)}


def load_pondage_flow_profiles(
    node_df: pd.DataFrame, selected_zones: list[str],
    scenario: int, climate_year: int,
) -> dict[str, list[dict]]:
    key = "Pondage Flow Energy"
    return {key: _load_hydro_inflow_profiles(node_df, selected_zones, scenario, climate_year, key)}


def load_reservoir_flow_profiles(
    node_df: pd.DataFrame, selected_zones: list[str],
    scenario: int, climate_year: int,
) -> dict[str, list[dict]]:
    key = "Reservoir Flow Energy"
    return {key: _load_hydro_inflow_profiles(node_df, selected_zones, scenario, climate_year, key)}


def load_open_ps_flow_profiles(
    node_df: pd.DataFrame, selected_zones: list[str],
    scenario: int, climate_year: int,
) -> dict[str, list[dict]]:
    key = "Open_PS Flow Energy"
    return {key: _load_hydro_inflow_profiles(node_df, selected_zones, scenario, climate_year, key)}


def load_closed_ps_flow_profiles(
    node_df: pd.DataFrame, selected_zones: list[str],
    scenario: int, climate_year: int,
) -> dict[str, list[dict]]:
    key = "Closed_PS Flow Energy"
    return {key: _load_hydro_inflow_profiles(node_df, selected_zones, scenario, climate_year, key)}


# Convenience: load everything at once


def load_all_profiles(
    node_df: pd.DataFrame,
    selected_zones: list[str],
    scenario: int,
    climate_year: int,
    selected_hours: int,
) -> dict[str, list[dict]]:
    combined: dict[str, list[dict]] = {}
    loaders = [
        lambda: load_electricity_demand_profiles(node_df, selected_zones, scenario, climate_year, selected_hours),
        lambda: load_hydrogen_demand_profiles(node_df, selected_zones, scenario, climate_year, selected_hours),
        lambda: load_gas_demand_profiles(node_df, selected_zones, climate_year, selected_hours),
        lambda: load_csp_no_storage_profiles(node_df, selected_zones, scenario, climate_year, selected_hours),
        lambda: load_csp_dispatch_profiles(node_df, selected_zones, scenario, climate_year, selected_hours),
        lambda: load_csp_predispatch_profiles(node_df, selected_zones, scenario, climate_year, selected_hours),
        lambda: load_solar_profiles(node_df, selected_zones, scenario, climate_year, selected_hours),
        lambda: load_solar_rooftop_profiles(node_df, selected_zones, scenario, climate_year, selected_hours),
        lambda: load_solar_utility_profiles(node_df, selected_zones, scenario, climate_year, selected_hours),
        lambda: load_wind_offshore_profiles(node_df, selected_zones, scenario, climate_year, selected_hours),
        lambda: load_wind_onshore_profiles(node_df, selected_zones, scenario, climate_year, selected_hours),
        lambda: load_river_flow_profiles(node_df, selected_zones, scenario, climate_year),
        lambda: load_pondage_flow_profiles(node_df, selected_zones, scenario, climate_year),
        lambda: load_reservoir_flow_profiles(node_df, selected_zones, scenario, climate_year),
        lambda: load_open_ps_flow_profiles(node_df, selected_zones, scenario, climate_year),
        lambda: load_closed_ps_flow_profiles(node_df, selected_zones, scenario, climate_year),
    ]

    for loader in loaders:
        try:
            combined.update(loader())
        except (FileNotFoundError, KeyError) as exc:
            print(f"Warning: profile loader skipped – {exc}")

    return combined


def load_commodity_prices(
    scenario_year: int,
    filepath: str = FILEPATH_COMMODITY_PRICES,
) -> dict[str, float]:
    try:
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    except Exception as exc:
        print(f"Warning: commodity prices file not found – {exc}")
        return {}

    ws = wb["Matrix 2024"]
    year_col: int | None = None
    fuel_prices: dict[str, float] = {}

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 2:
            for j, val in enumerate(row):
                if val == scenario_year:
                    year_col = j
                    break
            if year_col is None:
                year_col = 3
        elif i >= 3 and year_col is not None:
            fuel = row[1]
            if fuel is None:
                continue
            price = row[year_col]
            if price is not None:
                try:
                    fuel_prices[str(fuel).strip()] = float(price) * 3.6
                except (TypeError, ValueError):
                    pass
        if i > 25:
            break

    def _p(key: str) -> float:
        return round(fuel_prices.get(key, 0.0), 4)

    return {
        "Nuclear":     _p("Nuclear"),
        "Hard_coal":   _p("Hard coal"),
        "Lignite_G1":  _p("Lignite G1 (BG - MK - CZ)"),
        "Lignite_G2":  _p("Lignite G2 (SK - DE - RS - PL - ME - UKNI - BA - IE)"),
        "Lignite_G3":  _p("Lignite G3 (SL - RO - HU)"),
        "Lignite_G4":  _p("Lignite G4 (GR - TR)"),
        "Natural_Gas": _p("Natural Gas"),
        "Crude_oil":   _p("Crude oil"),
        "Light_oil":   _p("Light oil"),
        "Heavy_oil":   _p("Heavy oil"),
        "Oil_shale":   _p("Oil Shale"),
        "Hydrogen":    _p("Hydrogen (blue )"),
        "Biomethane":  _p("Biomethane"),
        "Gas_blend_NT": _p("Gas (blend of biomethane, synthetic gas and NG) NT+"),
        "CO2_price":   round(fuel_prices.get("CO2 price", 0.0) / 3.6, 4),
    }


def load_lignite_groups(
    filepath: str = FILEPATH_COMMODITY_PRICES,
) -> dict[str, str]:
    try:
        wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    except Exception as exc:
        print(f"Warning: commodity prices file not found – {exc}")
        return {}

    ws = wb["Matrix 2024"]
    result: dict[str, str] = {}

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 3:
            continue
        fuel = str(row[1]).strip() if row[1] else ""
        m = re.match(r"Lignite\s+G(\d+)\s*\(([^)]+)\)", fuel)
        if m:
            key = f"Lignite_G{m.group(1)}"
            for country in re.split(r"\s*-\s*", m.group(2)):
                country = country.strip()
                if country:
                    result[country] = key
        if i > 10:
            break

    return result
