"""Preprocessing and transformation functions for network, storage, and profile data."""

from __future__ import annotations

import numpy as np
import pandas as pd

from collector.utils.config import (
    DEFAULT_LOSS_PER_100KM,
    EARTH_RADIUS_KM,
    GAS_PIPE_OPTIONS,
    GAS_STORAGE_OPTIONS,
    GAS_TERMINAL_OPTIONS,
    GAS_UNIT_FACTOR,
    HYDROGEN_PIPE_OPTIONS,
    HYDROGEN_STORAGE_OPTIONS,
    HYDROGEN_TERMINAL_OPTIONS,
)
from collector.utils.helpers import expand_profile_to_hourly, validate_option


# ---------------------------------------------------------------------------
# Geographic calculations
# ---------------------------------------------------------------------------


def haversine_km(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """Calculate the great-circle distance between two points on Earth.

    Uses the Haversine formula with the mean Earth radius
    :data:`~collector.utils.config.EARTH_RADIUS_KM`.

    Args:
        lat1 (float): Latitude of point 1 in decimal degrees.
        lon1 (float): Longitude of point 1 in decimal degrees.
        lat2 (float): Latitude of point 2 in decimal degrees.
        lon2 (float): Longitude of point 2 in decimal degrees.

    Returns:
        float: Distance in kilometres.

    Example:
        >>> round(haversine_km(40.4, -3.7, 38.7, -9.1), 1)
        495.6
    """
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def compute_lengths_and_losses(
    node_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    selected_zones: list[str],
    between_only: bool = True,
    loss_per_100km: float = DEFAULT_LOSS_PER_100KM,
) -> pd.DataFrame:
    """Compute line lengths and loss fractions for a network edge table.

    Adds a ``Length_km`` column (Haversine distance) and a
    ``Loss_fraction`` column (length × loss_per_km) to a filtered copy of
    *edges_df*.

    Args:
        node_df (pd.DataFrame): Nodes table with ``Code``, ``Latitude``, and
            ``Longitude`` columns.
        edges_df (pd.DataFrame): Edge table with ``Start_Node`` and
            ``End_Node`` columns.
        selected_zones (list[str]): Study-area zone codes.
        between_only (bool): When ``True`` (default), keep only edges where
            *both* endpoints are in *selected_zones*.  When ``False``, keep
            any edge that touches at least one selected zone.
        loss_per_100km (float): Percentage transmission loss per 100 km.
            Defaults to :data:`~collector.utils.config.DEFAULT_LOSS_PER_100KM`.

    Returns:
        pd.DataFrame: Columns ``Start_Node``, ``End_Node``, ``Length_km``,
            ``Loss_fraction``.

    Example:
        >>> result = compute_lengths_and_losses(nodes, edges_e, ["ES00", "PT00"])
        >>> "Loss_fraction" in result.columns
        True
    """
    nodes = (
        node_df[["Code", "Latitude", "Longitude"]]
        .drop_duplicates(subset=["Code"])
        .rename(columns={"Latitude": "lat", "Longitude": "lon"})
    )

    edges = edges_df.copy()
    if between_only:
        edges = edges[
            edges["Start_Node"].isin(selected_zones) &
            edges["End_Node"].isin(selected_zones)
        ]
    else:
        edges = edges[
            edges["Start_Node"].apply(lambda x: any(z in str(x) for z in selected_zones)) |
            edges["End_Node"].apply(lambda x: any(z in str(x) for z in selected_zones))
        ]

    edges = (
        edges
        .merge(nodes, left_on="Start_Node", right_on="Code", how="left")
        .rename(columns={"lat": "start_lat", "lon": "start_lon"})
        .drop(columns=["Code"])
        .merge(nodes, left_on="End_Node", right_on="Code", how="left")
        .rename(columns={"lat": "end_lat", "lon": "end_lon"})
        .drop(columns=["Code"])
    )

    edges["Length_km"] = haversine_km(
        edges["start_lat"].values, edges["start_lon"].values,
        edges["end_lat"].values,   edges["end_lon"].values,
    )

    loss_per_km = (loss_per_100km / 100.0) / 100.0
    edges["Loss_fraction"] = edges["Length_km"] * loss_per_km

    return edges[["Start_Node", "End_Node", "Length_km", "Loss_fraction"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Network edge filtering
# ---------------------------------------------------------------------------


def filter_electricity_edges(
    edges_e_df: pd.DataFrame,
    selected_zones: list[str],
) -> pd.DataFrame:
    """Filter electricity edges to those touching selected zones and rename capacity columns.

    Args:
        edges_e_df (pd.DataFrame): Full electricity edge table.
        selected_zones (list[str]): Zone codes defining the study area.

    Returns:
        pd.DataFrame: Filtered frame with columns ``Start_Node``, ``End_Node``,
            ``Capacity (From)``, and ``Capacity (To)``.

    Example:
        >>> filtered = filter_electricity_edges(edges_e, ["ES00", "PT00"])
    """
    mask = (
        edges_e_df["Start_Node"].astype(str).isin([str(z) for z in selected_zones]) |
        edges_e_df["End_Node"].astype(str).isin([str(z) for z in selected_zones])
    )
    df = edges_e_df[mask].copy()
    df = df.rename(columns={
        df.columns[3]: "Capacity (From)",
        df.columns[4]: "Capacity (To)",
    })
    return df[["Start_Node", "End_Node", "Capacity (From)", "Capacity (To)"]]


def filter_gas_edges(
    edges_g_df: pd.DataFrame,
    selected_zones: list[str],
    gas_pipe: str,
) -> pd.DataFrame:
    """Filter gas pipeline edges and select the capacity columns for the chosen scenario.

    Column index mapping for gas pipe variants:
    * ``'Existing'`` → columns 3–4
    * ``'Low'``      → columns 5–6
    * ``'Advanced'`` → columns 7–8
    * ``'High'``     → columns 9–10

    Capacity values are converted from GWh/day to MW via
    :data:`~collector.utils.config.GAS_UNIT_FACTOR`.

    Args:
        edges_g_df (pd.DataFrame): Full gas pipeline edge table.
        selected_zones (list[str]): Zone codes defining the study area.
        gas_pipe (str): Pipeline scenario – one of
            :data:`~collector.utils.config.GAS_PIPE_OPTIONS`.

    Returns:
        pd.DataFrame: Columns ``Start_Node``, ``End_Node``,
            ``Capacity (From)``, ``Capacity (To)`` in MW.

    Raises:
        ValueError: When *gas_pipe* is not a recognised option.

    Example:
        >>> filtered = filter_gas_edges(edges_g, ["ES00"], "Low")
    """
    validate_option(gas_pipe, GAS_PIPE_OPTIONS, "gas_pipe")
    col_map = {"Existing": (3, 4), "Low": (5, 6), "Advanced": (7, 8), "High": (9, 10)}
    from_col, to_col = col_map[gas_pipe]

    mask = (
        edges_g_df["Start_Node"].astype(str).isin([str(z) for z in selected_zones]) |
        edges_g_df["End_Node"].astype(str).isin([str(z) for z in selected_zones])
    )
    df = edges_g_df[mask].copy()
    df = df.rename(columns={
        df.columns[from_col]: "Capacity (From)",
        df.columns[to_col]:   "Capacity (To)",
    })
    df[["Capacity (From)", "Capacity (To)"]] = (
        df[["Capacity (From)", "Capacity (To)"]].astype(float) * GAS_UNIT_FACTOR
    )
    return df[["Start_Node", "End_Node", "Capacity (From)", "Capacity (To)"]]


def filter_hydrogen_edges(
    edges_h_df: pd.DataFrame,
    selected_zones: list[str],
    hydrogen_pipe: str,
) -> pd.DataFrame:
    """Filter hydrogen pipeline edges and select capacity columns for the chosen scenario.

    Column index mapping for hydrogen pipe variants:
    * ``'PCI/PMI'``       → columns 3–4
    * ``'Advanced'``      → columns 5–6
    * ``'Less-Advanced'`` → columns 7–8

    Capacity values are converted from GWh/day to MW via
    :data:`~collector.utils.config.GAS_UNIT_FACTOR`.

    Args:
        edges_h_df (pd.DataFrame): Full hydrogen pipeline edge table.
        selected_zones (list[str]): Zone codes defining the study area.
        hydrogen_pipe (str): Pipeline scenario – one of
            :data:`~collector.utils.config.HYDROGEN_PIPE_OPTIONS`.

    Returns:
        pd.DataFrame: Columns ``Start_Node``, ``End_Node``,
            ``Capacity (From)``, ``Capacity (To)`` in MW.

    Raises:
        ValueError: When *hydrogen_pipe* is not a recognised option.

    Example:
        >>> filtered = filter_hydrogen_edges(edges_h, ["ES00"], "PCI/PMI")
    """
    validate_option(hydrogen_pipe, HYDROGEN_PIPE_OPTIONS, "hydrogen_pipe")
    col_map = {"PCI/PMI": (3, 4), "Advanced": (5, 6), "Less-Advanced": (7, 8)}
    from_col, to_col = col_map[hydrogen_pipe]

    # The hydrogen network has one node per country whose code can differ from the
    # electricity zone code (e.g. BEOF vs BE00, NLLL vs NL00, DKNS vs DKE1). Map
    # each H2 endpoint to a selected electricity zone by country prefix (first two
    # characters): keep it if it is already a selected zone, otherwise use the
    # first selected zone of the same country.
    sel = [str(z) for z in selected_zones]
    sel_set = set(sel)
    country_zone: dict[str, str] = {}
    for z in sel:
        country_zone.setdefault(z[:2], z)

    def _to_zone(node: object) -> str:
        n = str(node)
        return n if n in sel_set else country_zone.get(n[:2], n)

    df = edges_h_df.copy()
    df = df.rename(columns={
        df.columns[from_col]: "Capacity (From)",
        df.columns[to_col]:   "Capacity (To)",
    })
    df["Start_Node"] = df["Start_Node"].map(_to_zone)
    df["End_Node"]   = df["End_Node"].map(_to_zone)
    # Keep only cross-border pipes whose (mapped) endpoints are both selected.
    df = df[
        df["Start_Node"].isin(sel_set)
        & df["End_Node"].isin(sel_set)
        & (df["Start_Node"] != df["End_Node"])
    ].copy()
    df[["Capacity (From)", "Capacity (To)"]] = (
        df[["Capacity (From)", "Capacity (To)"]].astype(float) * GAS_UNIT_FACTOR
    )
    return df[["Start_Node", "End_Node", "Capacity (From)", "Capacity (To)"]]


# ---------------------------------------------------------------------------
# Storage / terminal filtering
# ---------------------------------------------------------------------------


def filter_gas_storages(
    storages_g_df: pd.DataFrame,
    selected_zones: list[str],
    gas_storage: str,
) -> pd.DataFrame:
    """Filter gas storage rows and select the capacity columns for the scenario.

    Column index mapping:
    * ``'Low'``      → columns 2–3 (Injection, Withdrawal)
    * ``'Advanced'`` → columns 4–5
    * ``'High'``     → columns 6–7

    Values are converted from GWh/day to MW.

    Args:
        storages_g_df (pd.DataFrame): Full gas storage table.
        selected_zones (list[str]): Zone codes defining the study area.
        gas_storage (str): Storage scenario – one of
            :data:`~collector.utils.config.GAS_STORAGE_OPTIONS`.

    Returns:
        pd.DataFrame: Columns ``Code``, ``Capacity (Injection)``,
            ``Capacity (Withdraw)`` in MW.

    Raises:
        ValueError: When *gas_storage* is not a recognised option.

    Example:
        >>> filtered = filter_gas_storages(storages_g, ["ES00"], "Low")
    """
    validate_option(gas_storage, GAS_STORAGE_OPTIONS, "gas_storage")
    col_map = {"Low": (2, 3), "Advanced": (4, 5), "High": (6, 7)}
    inj_col, wdraw_col = col_map[gas_storage]

    mask = storages_g_df["Code"].astype(str).isin([str(z) for z in selected_zones])
    df = storages_g_df[mask].copy()
    df = df.rename(columns={
        df.columns[inj_col]:   "Capacity (Injection)",
        df.columns[wdraw_col]: "Capacity (Withdraw)",
    })
    df[["Capacity (Injection)", "Capacity (Withdraw)"]] = (
        df[["Capacity (Injection)", "Capacity (Withdraw)"]].astype(float) * GAS_UNIT_FACTOR
    )
    return df[["Code", "Capacity (Injection)", "Capacity (Withdraw)"]]


def filter_hydrogen_storages(
    storages_h_df: pd.DataFrame,
    selected_zones: list[str],
    hydrogen_storage: str,
) -> pd.DataFrame:
    """Filter hydrogen storage rows and select capacity columns for the scenario.

    Column index mapping (the sheet has two leading columns, ``Zones`` and
    ``Code``, then Injection/Withdraw pairs per scenario):
    * ``'PCI/PMI'``       → columns 2–3 (Injection, Withdraw)
    * ``'Advanced'``      → columns 4–5
    * ``'Less-Advanced'`` → columns 6–7

    Values are converted from GWh/day to MW.

    Args:
        storages_h_df (pd.DataFrame): Full hydrogen storage table.
        selected_zones (list[str]): Zone codes defining the study area.
        hydrogen_storage (str): Storage scenario – one of
            :data:`~collector.utils.config.HYDROGEN_STORAGE_OPTIONS`.

    Returns:
        pd.DataFrame: Columns ``Code``, ``Capacity (Injection)``,
            ``Capacity (Withdraw)`` in MW.

    Raises:
        ValueError: When *hydrogen_storage* is not a recognised option.

    Example:
        >>> filtered = filter_hydrogen_storages(storages_h, ["ES00"], "PCI/PMI")
    """
    validate_option(hydrogen_storage, HYDROGEN_STORAGE_OPTIONS, "hydrogen_storage")
    col_map = {"PCI/PMI": (2, 3), "Advanced": (4, 5), "Less-Advanced": (6, 7)}
    inj_col, wdraw_col = col_map[hydrogen_storage]

    mask = storages_h_df["Code"].astype(str).isin([str(z) for z in selected_zones])
    df = storages_h_df[mask].copy()
    df = df.rename(columns={
        df.columns[inj_col]:   "Capacity (Injection)",
        df.columns[wdraw_col]: "Capacity (Withdraw)",
    })
    df[["Capacity (Injection)", "Capacity (Withdraw)"]] = (
        df[["Capacity (Injection)", "Capacity (Withdraw)"]].astype(float) * GAS_UNIT_FACTOR
    )
    return df[["Code", "Capacity (Injection)", "Capacity (Withdraw)"]]


def filter_gas_terminals(
    terminals_g_df: pd.DataFrame,
    selected_zones: list[str],
    gas_terminal: str,
) -> pd.DataFrame:
    """Filter gas terminal rows and select the import capacity column.

    Column index mapping:
    * ``'Low'``      → column 2
    * ``'Advanced'`` → column 3
    * ``'High'``     → column 4

    Values are converted from GWh/day to MW.

    Args:
        terminals_g_df (pd.DataFrame): Full gas terminal table.
        selected_zones (list[str]): Zone codes defining the study area.
        gas_terminal (str): Terminal scenario – one of
            :data:`~collector.utils.config.GAS_TERMINAL_OPTIONS`.

    Returns:
        pd.DataFrame: Columns ``Code`` and ``Import`` in MW.

    Raises:
        ValueError: When *gas_terminal* is not a recognised option.

    Example:
        >>> filtered = filter_gas_terminals(terminals_g, ["ES00"], "Low")
    """
    validate_option(gas_terminal, GAS_TERMINAL_OPTIONS, "gas_terminal")
    col_map = {"Low": 2, "Advanced": 3, "High": 4}
    imp_col = col_map[gas_terminal]

    mask = terminals_g_df["Code"].astype(str).isin([str(z) for z in selected_zones])
    df = terminals_g_df[mask].copy()
    df = df.rename(columns={df.columns[imp_col]: "Import"})
    df[["Import"]] = df[["Import"]].astype(float) * GAS_UNIT_FACTOR
    return df[["Code", "Import"]]


def filter_hydrogen_terminals(
    terminals_h_df: pd.DataFrame,
    selected_zones: list[str],
    hydrogen_terminal: str,
) -> pd.DataFrame:
    """Filter hydrogen terminal rows and select the import capacity column.

    Column index mapping (two leading columns, ``Zones`` and ``Code``, then one
    import-capacity column per scenario):
    * ``'PCI/PMI'``       → column 2
    * ``'Advanced'``      → column 3
    * ``'Less-Advanced'`` → column 4

    Values are converted from GWh/day to MW.

    Args:
        terminals_h_df (pd.DataFrame): Full hydrogen terminal table.
        selected_zones (list[str]): Zone codes defining the study area.
        hydrogen_terminal (str): Terminal scenario – one of
            :data:`~collector.utils.config.HYDROGEN_TERMINAL_OPTIONS`.

    Returns:
        pd.DataFrame: Columns ``Code`` and ``Import`` in MW.

    Raises:
        ValueError: When *hydrogen_terminal* is not a recognised option.

    Example:
        >>> filtered = filter_hydrogen_terminals(terminals_h, ["ES00"], "PCI/PMI")
    """
    validate_option(hydrogen_terminal, HYDROGEN_TERMINAL_OPTIONS, "hydrogen_terminal")
    col_map = {"PCI/PMI": 2, "Advanced": 3, "Less-Advanced": 4}
    imp_col = col_map[hydrogen_terminal]

    mask = terminals_h_df["Code"].astype(str).isin([str(z) for z in selected_zones])
    df = terminals_h_df[mask].copy()
    df = df.rename(columns={df.columns[imp_col]: "Import"})
    df[["Import"]] = df[["Import"]].astype(float) * GAS_UNIT_FACTOR
    return df[["Code", "Import"]]


# ---------------------------------------------------------------------------
# High-level network / storage / terminal assemblers
# ---------------------------------------------------------------------------


def build_network_data(
    node_df: pd.DataFrame,
    edges_e_df: pd.DataFrame,
    edges_g_df: pd.DataFrame,
    edges_h_df: pd.DataFrame,
    selected_zones: list[str],
    gas_pipe: str,
    hydrogen_pipe: str,
    loss_per_100km: float = DEFAULT_LOSS_PER_100KM,
) -> dict[str, np.ndarray]:
    """Assemble the full network data dict (loss fractions + line capacities).

    Args:
        node_df (pd.DataFrame): Nodes table with lat/lon columns.
        edges_e_df (pd.DataFrame): Raw electricity edge table.
        edges_g_df (pd.DataFrame): Raw gas pipeline edge table.
        edges_h_df (pd.DataFrame): Raw hydrogen pipeline edge table.
        selected_zones (list[str]): Study-area zone codes.
        gas_pipe (str): Gas pipeline capacity scenario.
        hydrogen_pipe (str): Hydrogen pipeline capacity scenario.
        loss_per_100km (float): Transmission loss rate (%/100 km).

    Returns:
        dict[str, np.ndarray]: Keys are ``'Loss Fraction (Electricity)'``,
            ``'Loss Fraction (Gas)'``, ``'Loss Fraction (Hydrogen)'``,
            ``'Line Capacity (Electricity)'``, ``'Line Capacity (Gas)'``,
            and ``'Line Capacity (Hydrogen)'``.  Each value is a numpy array.

    Example:
        >>> nd = build_network_data(nodes, edges_e, edges_g, edges_h,
        ...                         ["ES00", "PT00"], "Low", "PCI/PMI")
    """
    result: dict[str, np.ndarray] = {}

    for label, raw_edges in [
        ("Electricity", edges_e_df),
        ("Gas", edges_g_df),
        ("Hydrogen", edges_h_df),
    ]:
        loss_df = compute_lengths_and_losses(
            node_df, raw_edges, selected_zones,
            between_only=True, loss_per_100km=loss_per_100km,
        )
        result[f"Loss Fraction ({label})"] = loss_df.to_numpy()

    result["Line Capacity (Electricity)"] = filter_electricity_edges(
        edges_e_df, selected_zones
    ).to_numpy()
    result["Line Capacity (Gas)"] = filter_gas_edges(
        edges_g_df, selected_zones, gas_pipe
    ).to_numpy()
    result["Line Capacity (Hydrogen)"] = filter_hydrogen_edges(
        edges_h_df, selected_zones, hydrogen_pipe
    ).to_numpy()

    return result


def build_storage_data(
    storages_g_df: pd.DataFrame,
    storages_h_df: pd.DataFrame,
    selected_zones: list[str],
    gas_storage: str,
    hydrogen_storage: str,
) -> dict[str, np.ndarray]:
    """Assemble the storage capacity data dict.

    Args:
        storages_g_df (pd.DataFrame): Raw gas storage table.
        storages_h_df (pd.DataFrame): Raw hydrogen storage table.
        selected_zones (list[str]): Study-area zone codes.
        gas_storage (str): Gas storage capacity scenario.
        hydrogen_storage (str): Hydrogen storage capacity scenario.

    Returns:
        dict[str, np.ndarray]: Keys ``'Storage Capacity (Gas)'`` and
            ``'Storage Capacity (Hydrogen)'``.

    Example:
        >>> sd = build_storage_data(sg, sh, ["ES00"], "Low", "PCI/PMI")
    """
    return {
        "Storage Capacity (Gas)": filter_gas_storages(
            storages_g_df, selected_zones, gas_storage
        ).to_numpy(),
        "Storage Capacity (Hydrogen)": filter_hydrogen_storages(
            storages_h_df, selected_zones, hydrogen_storage
        ).to_numpy(),
    }


def build_terminal_data(
    terminals_g_df: pd.DataFrame,
    terminals_h_df: pd.DataFrame,
    selected_zones: list[str],
    gas_terminal: str,
    hydrogen_terminal: str,
) -> dict[str, np.ndarray]:
    """Assemble the terminal import capacity data dict.

    Args:
        terminals_g_df (pd.DataFrame): Raw gas terminal table.
        terminals_h_df (pd.DataFrame): Raw hydrogen terminal table.
        selected_zones (list[str]): Study-area zone codes.
        gas_terminal (str): Gas terminal capacity scenario.
        hydrogen_terminal (str): Hydrogen terminal capacity scenario.

    Returns:
        dict[str, np.ndarray]: Keys ``'Terminal (Gas)'`` and
            ``'Terminal (Hydrogen)'``.

    Example:
        >>> td = build_terminal_data(tg, th, ["ES00"], "Low", "PCI/PMI")
    """
    return {
        "Terminal (Gas)": filter_gas_terminals(
            terminals_g_df, selected_zones, gas_terminal
        ).to_numpy(),
        "Terminal (Hydrogen)": filter_hydrogen_terminals(
            terminals_h_df, selected_zones, hydrogen_terminal
        ).to_numpy(),
    }


# ---------------------------------------------------------------------------
# Profile normalisation
# ---------------------------------------------------------------------------


def normalise_profiles_to_hourly(
    profiles_df: dict[str, list[dict]],
    selected_hours: int,
) -> dict[str, list[dict]]:
    """Expand all non-hourly profile entries to *selected_hours* resolution.

    Iterates over every entry in *profiles_df*; when the ``Data`` array has
    length != *selected_hours*, it is passed through
    :func:`~collector.utils.helpers.expand_profile_to_hourly` before being
    written back.  The original dict is mutated in place and also returned.

    Args:
        profiles_df (dict[str, list[dict]]): Profiles dict as returned by the
            loader functions.  Modified in place.
        selected_hours (int): Required hourly series length.

    Returns:
        dict[str, list[dict]]: The same dict with all arrays normalised.

    Example:
        >>> normalise_profiles_to_hourly(profiles, 8736)
    """
    for profile_type, profile_list in profiles_df.items():
        for entry in profile_list:
            data = entry.get("Data")
            if data is None:
                entry["Data"] = np.zeros(selected_hours)
                continue
            arr = np.asarray(data, dtype=float) if not isinstance(data, np.ndarray) else data
            if len(arr) != selected_hours:
                entry["Data"] = expand_profile_to_hourly(arr, selected_hours)
    return profiles_df
