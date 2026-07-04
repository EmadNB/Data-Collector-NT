"""Shared utility functions used across the collector package."""

import os
from typing import Optional

import numpy as np
import pandas as pd

from collector.utils.config import VALID_SCENARIOS


# ---------------------------------------------------------------------------
# Directory management
# ---------------------------------------------------------------------------


def clear_output_files(base_path: str, output_mode: str) -> None:
    """Delete stale output files before a new generation run.

    Removes every file in ``outputs/HTMLs/`` and every file in the
    mode-specific Excel folder (``outputs/Excel Files/Normal`` or
    ``outputs/Excel Files/openTEPES``).  Directories themselves are kept so
    ``create_output_directories`` does not need to re-create them.

    Args:
        base_path (str): Root directory that contains ``outputs/``.
        output_mode (str): ``'Normal'`` or ``'openTEPES'``.
    """
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
    """Create the standard output folder hierarchy under *base_path*.

    Creates ``Outputs/HTMLs`` and ``Outputs/Excel Files/{Normal,openTEPES}``
    if they do not already exist; existing directories are left untouched.

    Args:
        base_path (str): Root directory under which ``Outputs/`` is created.
            Defaults to the current working directory.

    Returns:
        None

    Example:
        >>> create_output_directories(".")
    """
    paths = [
        os.path.join(base_path, "outputs", "HTMLs"),
        os.path.join(base_path, "outputs", "Excel Files", "Normal"),
        os.path.join(base_path, "outputs", "Excel Files", "openTEPES"),
    ]
    for path in paths:
        os.makedirs(path, exist_ok=True)


# ---------------------------------------------------------------------------
# PEMMDB file helpers
# ---------------------------------------------------------------------------


def get_pemmdb_filepath(code: str, scenario: int) -> str:
    """Return the PEMMDB Excel file path for a given zone code and scenario.

    Args:
        code (str): Zone code (e.g. ``'ES00'``).
        scenario (int): Scenario year – one of ``2030``, ``2040``, ``2050``.

    Returns:
        str: Relative path to the PEMMDB Excel file.

    Raises:
        ValueError: When *scenario* is not one of the valid scenario years.

    Example:
        >>> get_pemmdb_filepath("ES00", 2030)
        'Data/PEMMDB2/2030/PEMMDB_ES00_NationalTrends_2030.xlsx'
    """
    if scenario not in VALID_SCENARIOS:
        raise ValueError(f"scenario must be one of {VALID_SCENARIOS}, got {scenario!r}")
    return f"inputs/PEMMDB2/{scenario}/PEMMDB_{code}_NationalTrends_{scenario}.xlsx"


def get_co2_usecols(scenario: int) -> str:
    """Return the Excel column letter for CO2 emission factors given the scenario.

    The CO2 factor spreadsheet stores different scenario columns under
    different column letters (F→2030, G→2040, E→2050).

    Args:
        scenario (int): Scenario year – one of ``2030``, ``2040``, ``2050``.

    Returns:
        str: Single Excel column letter (``'E'``, ``'F'``, or ``'G'``).

    Raises:
        ValueError: When *scenario* is not a recognised scenario year.

    Example:
        >>> get_co2_usecols(2030)
        'F'
    """
    mapping = {2030: "F", 2040: "G", 2050: "E"}
    if scenario not in mapping:
        raise ValueError(f"scenario must be one of {VALID_SCENARIOS}, got {scenario!r}")
    return mapping[scenario]


# ---------------------------------------------------------------------------
# Zone / display-name helpers
# ---------------------------------------------------------------------------


def build_zone_display_map(
    node_df: pd.DataFrame,
    selected_zones: list[str],
) -> dict[str, str]:
    """Build a mapping from zone code to a human-readable display label.

    If the *node_df* contains a ``Location`` column, display labels take the
    form ``"<Location> (<Code>)"``; otherwise the code is used as-is.

    Args:
        node_df (pd.DataFrame): Nodes table with at least a ``Code`` column
            and optionally a ``Location`` column.
        selected_zones (list[str]): Zone codes to include in the map.

    Returns:
        dict[str, str]: Mapping ``{code: display_label}`` for every code in
            *selected_zones*.

    Example:
        >>> import pandas as pd
        >>> df = pd.DataFrame({"Code": ["ES00"], "Location": ["Spain"]})
        >>> build_zone_display_map(df, ["ES00"])
        {'ES00': 'Spain (ES00)'}
    """
    code_to_location: dict[str, str] = {}
    if isinstance(node_df, pd.DataFrame) and {"Code", "Location"}.issubset(node_df.columns):
        code_to_location = dict(zip(node_df["Code"], node_df["Location"]))

    result: dict[str, str] = {}
    for zone in selected_zones:
        location = code_to_location.get(zone)
        result[zone] = f"{location} ({zone})" if location else zone
    return result


# ---------------------------------------------------------------------------
# Profile temporal expansion
# ---------------------------------------------------------------------------


def expand_profile_to_hourly(
    data: list | np.ndarray,
    target_len: int,
) -> np.ndarray:
    """Convert a daily or weekly energy series to an hourly array.

    Dispatches to the appropriate sub-converter based on the length of *data*:

    * 365 or 366 values → daily series, each value split equally across 24 h
      (``value / 24`` per hour).
    * 52 or 53 values → weekly series, each value split equally across 168 h
      (``value / 168`` per hour).
    * Any other length → cast to float array and padded/truncated to
      *target_len*.

    Args:
        data (list | np.ndarray): Input energy series.
        target_len (int): Required output length in hours.

    Returns:
        np.ndarray: Float array of length *target_len*.

    Example:
        >>> import numpy as np
        >>> daily = np.ones(365)
        >>> hourly = expand_profile_to_hourly(daily, 8760)
        >>> hourly.shape
        (8760,)
    """
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
    """Expand a daily series to hourly by distributing each day over 24 h."""
    repeated: list[float] = []
    for value in data_list:
        v = _safe_float(value)
        repeated.extend([v / 24.0] * 24)
    return _clip_or_pad(repeated, target_len)


def _convert_weekly_to_hourly(data_list: list, target_len: int) -> np.ndarray:
    """Expand a weekly series to hourly by distributing each week over 168 h."""
    hours_per_week = 24 * 7
    repeated: list[float] = []
    for value in data_list:
        v = _safe_float(value)
        repeated.extend([v / float(hours_per_week)] * hours_per_week)
    return _clip_or_pad(repeated, target_len)


def _safe_float(value: object) -> float:
    """Return ``float(value)`` or ``0.0`` for None / empty strings."""
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clip_or_pad(data: list[float], target_len: int) -> np.ndarray:
    """Truncate or zero-pad *data* to exactly *target_len* elements."""
    arr = np.array(data, dtype=float)
    if len(arr) > target_len:
        return arr[:target_len]
    if len(arr) < target_len:
        return np.pad(arr, (0, target_len - len(arr)), "constant")
    return arr


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_scenario(scenario: int) -> None:
    """Raise ValueError if *scenario* is not in VALID_SCENARIOS.

    Args:
        scenario (int): Scenario year to validate.

    Returns:
        None

    Raises:
        ValueError: When *scenario* is not one of the valid scenario years.

    Example:
        >>> validate_scenario(2030)  # no error
        >>> validate_scenario(2035)  # raises ValueError
    """
    if scenario not in VALID_SCENARIOS:
        raise ValueError(f"scenario must be one of {VALID_SCENARIOS}, got {scenario!r}")


def validate_option(value: str, options: list[str], name: str) -> None:
    """Raise ValueError if *value* is not in *options*.

    Args:
        value (str): The value to check.
        options (list[str]): Allowed values.
        name (str): Parameter name used in the error message.

    Returns:
        None

    Raises:
        ValueError: When *value* is not in *options*.

    Example:
        >>> validate_option("Low", ["Low", "High"], "gas_storage")
    """
    if value not in options:
        raise ValueError(f"{name} must be one of {options}, got {value!r}")
