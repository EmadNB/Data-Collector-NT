import os
from typing import Optional

import numpy as np
import pandas as pd

from collector.utils.config import VALID_SCENARIOS


# Directory management


def clear_output_files(base_path: str, output_mode: str) -> None:
    html_dir  = os.path.join(base_path, "outputs", "HTMLs")
    excel_dir = os.path.join(base_path, "outputs", "Excel Files", output_mode)

    for directory in (html_dir, excel_dir):
        if not os.path.isdir(directory):
            continue
        for fname in os.listdir(directory):
            fpath = os.path.join(directory, fname)
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                except OSError:
                    pass


def create_output_directories(base_path: str = ".") -> None:
    paths = [
        os.path.join(base_path, "outputs", "HTMLs"),
        os.path.join(base_path, "outputs", "Excel Files", "Normal"),
        os.path.join(base_path, "outputs", "Excel Files", "openTEPES"),
    ]
    for path in paths:
        os.makedirs(path, exist_ok=True)


# PEMMDB file helpers


def get_pemmdb_filepath(code: str, scenario: int) -> str:
    if scenario not in VALID_SCENARIOS:
        raise ValueError(f"scenario must be one of {VALID_SCENARIOS}, got {scenario!r}")
    return f"inputs/PEMMDB2/{scenario}/PEMMDB_{code}_NationalTrends_{scenario}.xlsx"


def get_co2_usecols(scenario: int) -> str:
    mapping = {2030: "F", 2040: "G", 2050: "E"}
    if scenario not in mapping:
        raise ValueError(f"scenario must be one of {VALID_SCENARIOS}, got {scenario!r}")
    return mapping[scenario]


# Zone / display-name helpers


def build_zone_display_map(
    node_df: pd.DataFrame,
    selected_zones: list[str],
) -> dict[str, str]:
    code_to_location: dict[str, str] = {}
    if isinstance(node_df, pd.DataFrame) and {"Code", "Location"}.issubset(node_df.columns):
        code_to_location = dict(zip(node_df["Code"], node_df["Location"]))

    result: dict[str, str] = {}
    for zone in selected_zones:
        location = code_to_location.get(zone)
        result[zone] = f"{location} ({zone})" if location else zone
    return result


# Profile temporal expansion


def expand_profile_to_hourly(
    data: list | np.ndarray,
    target_len: int,
) -> np.ndarray:
    data_list = list(data) if not isinstance(data, list) else data
    n = len(data_list)

    if n in (365, 366):
        return _convert_daily_to_hourly(data_list, target_len)
    if n in (52, 53):
        return _convert_weekly_to_hourly(data_list, target_len)

    try:
        arr = np.array(data_list, dtype=float)
    except (TypeError, ValueError):
        arr = np.zeros(target_len)

    if len(arr) > target_len:
        return arr[:target_len]
    if len(arr) < target_len:
        return np.pad(arr, (0, target_len - len(arr)), "constant")
    return arr


def _convert_daily_to_hourly(data_list: list, target_len: int) -> np.ndarray:
    repeated: list[float] = []
    for value in data_list:
        v = _safe_float(value)
        repeated.extend([v / 24.0] * 24)
    return _clip_or_pad(repeated, target_len)


def _convert_weekly_to_hourly(data_list: list, target_len: int) -> np.ndarray:
    hours_per_week = 24 * 7
    repeated: list[float] = []
    for value in data_list:
        v = _safe_float(value)
        repeated.extend([v / float(hours_per_week)] * hours_per_week)
    return _clip_or_pad(repeated, target_len)


def _safe_float(value: object) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clip_or_pad(data: list[float], target_len: int) -> np.ndarray:
    arr = np.array(data, dtype=float)
    if len(arr) > target_len:
        return arr[:target_len]
    if len(arr) < target_len:
        return np.pad(arr, (0, target_len - len(arr)), "constant")
    return arr


# Validation helpers


def validate_scenario(scenario: int) -> None:
    if scenario not in VALID_SCENARIOS:
        raise ValueError(f"scenario must be one of {VALID_SCENARIOS}, got {scenario!r}")


def validate_option(value: str, options: list[str], name: str) -> None:
    if value not in options:
        raise ValueError(f"{name} must be one of {options}, got {value!r}")
