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


# Geographic calculations


def haversine_km(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
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


# Network edge filtering


def filter_electricity_edges(
    edges_e_df: pd.DataFrame,
    selected_zones: list[str],
) -> pd.DataFrame:
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
    validate_option(hydrogen_pipe, HYDROGEN_PIPE_OPTIONS, "hydrogen_pipe")
    col_map = {"PCI/PMI": (3, 4), "Advanced": (5, 6), "Less-Advanced": (7, 8), "ENTSO-E": (9, 10)}
    from_col, to_col = col_map[hydrogen_pipe]

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
    df = df[
        (df["Start_Node"].isin(sel_set) | df["End_Node"].isin(sel_set))
        & (df["Start_Node"] != df["End_Node"])
    ].copy()
    df[["Capacity (From)", "Capacity (To)"]] = (
        df[["Capacity (From)", "Capacity (To)"]].astype(float) * GAS_UNIT_FACTOR
    )
    return df[["Start_Node", "End_Node", "Capacity (From)", "Capacity (To)"]]


# Storage / terminal filtering


def filter_gas_storages(
    storages_g_df: pd.DataFrame,
    selected_zones: list[str],
    gas_storage: str,
) -> pd.DataFrame:
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
    validate_option(hydrogen_terminal, HYDROGEN_TERMINAL_OPTIONS, "hydrogen_terminal")
    col_map = {"PCI/PMI": 2, "Advanced": 3, "Less-Advanced": 4}
    imp_col = col_map[hydrogen_terminal]

    mask = terminals_h_df["Code"].astype(str).isin([str(z) for z in selected_zones])
    df = terminals_h_df[mask].copy()
    df = df.rename(columns={df.columns[imp_col]: "Import"})
    df[["Import"]] = df[["Import"]].astype(float) * GAS_UNIT_FACTOR
    return df[["Code", "Import"]]


# High-level network / storage / terminal assemblers


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
    return {
        "Terminal (Gas)": filter_gas_terminals(
            terminals_g_df, selected_zones, gas_terminal
        ).to_numpy(),
        "Terminal (Hydrogen)": filter_hydrogen_terminals(
            terminals_h_df, selected_zones, hydrogen_terminal
        ).to_numpy(),
    }


# Profile normalisation


def normalise_profiles_to_hourly(
    profiles_df: dict[str, list[dict]],
    selected_hours: int,
) -> dict[str, list[dict]]:
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
