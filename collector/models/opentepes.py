"""Export pipeline data to openTEPES CSV input format.

One call to :func:`export_opentepes` produces the complete set of
``oT_Data_*`` and ``oT_Dict_*`` CSV files expected by openTEPES, placed
inside *output_folder*.  The mapping follows the 2-node reference model
found in ``opentepes/2n/inputs/``.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any

import numpy as np
import pandas as pd


def _clean_area(name: object) -> str:
    """Normalise an area/location name to a plain-ASCII, underscore token.

    Node locations can contain non-breaking spaces (U+00A0) and accented
    characters that get mojibaked on CSV round-trips, causing openTEPES to fail
    matching the same area across its input files. This strips those to ASCII.
    """
    s = str(name).replace("\xa0", " ")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", "_", s.strip())
    return re.sub(r"_+", "_", s).strip("_")


# ---------------------------------------------------------------------------
# Technology table
# ---------------------------------------------------------------------------
# (capacity_col, generator_suffix, opentepes_technology, is_RES, char_row_idx)
# char_row_idx: 0-based index into the tech-characteristic arrays stored in
# tech_char_df for thermal units; None for RES / hydro / other.

def _tech_label(cap_col: str) -> str:
    """Convert a TECH_COLUMNS name to a clean snake_case label.

    'Hard Coal (old1) (MW)' -> 'Hard_Coal_old1'
    'Battery (MWh)'         -> 'Battery'
    'Gas (ccgt_old1) (MW)'  -> 'Gas_ccgt_old1'
    """
    s = re.sub(r'\s*\([A-Za-z/]+\)\s*$', '', cap_col)  # strip trailing unit
    s = re.sub(r'[()]', '', s)                           # remove remaining parens
    s = re.sub(r'[\s\-]+', '_', s.strip())              # spaces/hyphens -> _
    s = re.sub(r'_+', '_', s).strip('_')
    return s.replace('_turbine', '')                     # Hydro_open_ps_turbine -> Hydro_open_ps


# For techs where max_power (and max_charge) come from tech_char_df rather than
# tech_cap_df (e.g. Battery where the cap_col stores MWh, not MW):
# cap_col -> (char_col_for_max_p, char_col_for_max_charge, char_idx)
_CHAR_POWER_ENTRIES: dict[str, tuple[str, str, int]] = {
    "Battery (MWh)": (
        "Net maximum capacity - generation perspective (MW)",
        "Net maximum capacity - demand perspective (MW)",
        37,
    ),
}

_TECH_ENTRIES: list[tuple[str, str, str, bool, int | None]] = [
    # â"€â"€ Thermal / conventional â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    ("Nuclear (MW)",           "Nuclear",      "Nuclear",      False,  0),
    ("Hard Coal (old1) (MW)",  "Coal_old1",    "Coal",         False,  1),
    ("Hard Coal (old2) (MW)",  "Coal_old2",    "Coal",         False,  2),
    ("Hard Coal (new) (MW)",   "Coal_new",     "Coal",         False,  3),
    ("Hard Coal (ccs) (MW)",   "Coal_ccs",     "Coal",         False,  4),
    ("Lignite (old1) (MW)",    "Lignite_old1", "Lignite",      False,  5),
    ("Lignite (old2) (MW)",    "Lignite_old2", "Lignite",      False,  6),
    ("Lignite (new) (MW)",     "Lignite_new",  "Lignite",      False,  7),
    ("Lignite (ccs) (MW)",     "Lignite_ccs",  "Lignite",      False,  8),
    ("Gas (conv_old1) (MW)",   "Gas_conv1",    "Gas",          False,  9),
    ("Gas (conv_old2) (MW)",   "Gas_conv2",    "Gas",          False, 10),
    ("Gas (ccgt_old1) (MW)",   "Gas_ccgt1",    "Gas",          False, 11),
    ("Gas (ccgt_old2) (MW)",   "Gas_ccgt2",    "Gas",          False, 12),
    ("Gas (ccgt_new) (MW)",    "Gas_ccgt_new", "Gas",          False, 13),
    ("Gas (ccgt_ccs) (MW)",    "Gas_ccgt_ccs", "Gas",          False, 14),
    ("Gas (ocgt_old) (MW)",    "Gas_ocgt1",    "Gas",          False, 15),
    ("Gas (ocgt_new) (MW)",    "Gas_ocgt2",    "Gas",          False, 16),
    ("Light Oil (MW)",         "Oil_light",    "Oil",          False, 17),
    ("Heavy oil (old1) (MW)",  "Oil_heavy1",   "Oil",          False, 18),
    ("Heavy oil (old2) (MW)",  "Oil_heavy2",   "Oil",          False, 19),
    ("Oil shale (old) (MW)",   "OilShale1",    "Oil",          False, 20),
    ("Oil shale (new) (MW)",   "OilShale2",    "Oil",          False, 21),
    ("Gas (ccgt_pre1) (MW)",   "Gas_pre1",     "Gas",          False, 22),
    ("Gas (ccgt_pre2) (MW)",   "Gas_pre2",     "Gas",          False, 23),
    ("Hydrogen (fc) (MW)",     "H2_fc",        "Hydrogen",     False, 24),
    ("Hydrogen (ccgt) (MW)",   "H2_ccgt",      "Hydrogen",     False, 25),
    ("Other Non-RES (MW)",     "OtherNonRES",  "Other",        False, 26),
    *[(f"DSR{i+1} (MW)", f"DSR{i+1}", "DSR", False, 27 + i) for i in range(10)],
    ("Battery (MWh)",          "Battery",      "Battery",      False, 37),
    ("Electrolyser (MW)",      "Electr",       "Electrolyser", False, None),
    # â"€â"€ RES â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    ("Wind (onshore) (MW)",    "WindOn",       "Wind",         True,  None),
    ("Wind (offshore) (MW)",   "WindOff",      "Wind",         True,  None),
    ("Solar (MW)",             "Solar",        "Solar",        True,  None),
    ("Solar (rooftop) (MW)",   "SolarRoof",    "Solar",        True,  None),
    ("Solar (thermal) (MW)",   "SolarCSP",     "Solar",        True,  None),
    ("Solar (thermal_with_storage) (MW)", "SolarCSP_S", "Solar", True, None),
    ("Hydro (river) (MW)",     "HydroRoR",     "Hydro",        True,  None),
    # â"€â"€ Hydro with storage â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    ("Hydro (pondage) (MW)",         "HydroPond",   "Hydro", False, None),
    ("Hydro (reservoir) (MW)",       "HydroRes",    "Hydro", False, None),
    ("Hydro (open_ps_turbine) (MW)", "HydroPS_o",   "Hydro", False, None),
    ("Hydro (closed_ps_turbine) (MW)", "HydroPS_c", "Hydro", False, None),
    # â"€â"€ Other RES â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    ("Other RES (biomass) (MW)",    "Biomass",  "Biomass",    False, None),
    ("Other RES (geothermal) (MW)", "Geo",      "Geothermal", True,  None),
    ("Other RES (marine) (MW)",     "Marine",   "Marine",     True,  None),
    ("Other RES (waste) (MW)",      "Waste",    "Biomass",    False, None),
    ("Other RES (unknown) (MW)",    "RES_unk",  "RES",        True,  None),
]

# Storage MW columns (turbine side already in _TECH_ENTRIES; here are MWh caps)
_STORAGE_MW_PAIRS: dict[str, str] = {
    "Hydro (pondage) (MW)":         "Hydro (pondage) (MWh)",
    "Hydro (reservoir) (MW)":       "Hydro (reservoir) (MWh)",
    "Hydro (open_ps_turbine) (MW)": "Hydro (open_ps) (MWh)",
    "Hydro (closed_ps_turbine) (MW)": "Hydro (closed_ps) (MWh)",
}

_PUMP_PAIRS: dict[str, str] = {
    "Hydro (open_ps_turbine) (MW)":  "Hydro (open_ps_pump) (MW)",
    "Hydro (closed_ps_turbine) (MW)": "Hydro (closed_ps_pump) (MW)",
}

# openTEPES technology -> commodity price key
_OT_TECH_FUEL: dict[str, str] = {
    "Nuclear":  "Nuclear",
    "Coal":     "Hard_coal",
    "Gas":      "Natural_Gas",
    "Hydrogen": "Hydrogen",
    "Biomass":  "Biomethane",
}
# generator suffix overrides for Oil sub-types
_SUFFIX_FUEL: dict[str, str] = {
    "Oil_light":  "Light_oil",
    "Oil_heavy1": "Heavy_oil",
    "Oil_heavy2": "Heavy_oil",
    "OilShale1":  "Oil_shale",
    "OilShale2":  "Oil_shale",
}

# Profile type â†’ generator suffix (which RES generators get a variable profile)
_PROFILE_TO_SUFFIX: dict[str, str] = {
    "Wind_Onshore Profile":        "WindOn",
    "Wind_Offshore Profile":       "WindOff",
    "Solar Profile":               "Solar",
    "Solar_Rooftop Profile":       "SolarRoof",
    "CSP_noStorage Profile":       "SolarCSP",
    "CSP_withStorage_D Profile":   "SolarCSP_S",
    "River Flow Energy":           "HydroRoR",
    "Pondage Flow Energy":         "HydroPond",
    "Reservoir Flow Energy":       "HydroRes",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv(folder: str, name: str, df: pd.DataFrame) -> None:
    df.to_csv(os.path.join(folder, name), index=False)


def _make_loadlevels(n_hours: int) -> list[str]:
    """Generate n_hours timestamps starting 01-01 00:00:00+01:00."""
    base = pd.Timestamp("2000-01-01 00:00:00")
    return [
        (base + pd.Timedelta(hours=h)).strftime("%m-%d %H:%M:%S+01:00")
        for h in range(n_hours)
    ]


def _safe_scalar(arr: Any, idx: int, default: float = 0.0) -> float:
    """Safely extract scalar from a numpy array / list at position idx."""
    try:
        if arr is None:
            return default
        item = arr[idx]
        if hasattr(item, "__len__"):
            item = item.flat[0]
        v = float(item)
        return default if (np.isnan(v) or np.isinf(v)) else v
    except Exception:
        return default


def _get_char_monthly_avg(
    tech_char_df: pd.DataFrame,
    zone: str,
    col: str,
    char_idx: int | None,
    default: float = 0.0,
) -> float:
    """Return the mean of the 12 monthly values stored at char_idx."""
    if char_idx is None or tech_char_df.empty:
        return default
    rows = tech_char_df[tech_char_df["Code"] == zone]
    if rows.empty or col not in rows.columns:
        return default
    arr = rows.iloc[0][col]
    try:
        item = arr[char_idx]
        if hasattr(item, "__len__"):
            vals = np.asarray(item, dtype=float).flatten()
            vals = vals[~np.isnan(vals)]
            return float(np.mean(vals)) if len(vals) > 0 else default
        v = float(item)
        return default if (np.isnan(v) or np.isinf(v)) else v
    except Exception:
        return default


def _get_char(
    tech_char_df: pd.DataFrame,
    zone: str,
    col: str,
    char_idx: int | None,
    default: float = 0.0,
) -> float:
    """Return a scalar characteristic value for a zone + technology row."""
    if char_idx is None or tech_char_df.empty:
        return default
    rows = tech_char_df[tech_char_df["Code"] == zone]
    if rows.empty or col not in rows.columns:
        return default
    arr = rows.iloc[0][col]
    return _safe_scalar(arr, char_idx, default)


def _get_profile(
    profiles_df: dict[str, list[dict]],
    zone: str,
    profile_key: str,
) -> np.ndarray | None:
    """Return the numpy data array for zone + profile_key, or None."""
    for entry in profiles_df.get(profile_key, []):
        if entry.get("Code") == zone:
            data = entry.get("Data")
            if data is not None and len(data) > 0:
                return np.asarray(data, dtype=float)
    return None


def _get_hourly_series(tech_cap_df: pd.DataFrame, zone: str, col: str) -> np.ndarray | None:
    """Return the hourly (MW/h) timeseries array for zone + column, or None."""
    if col not in tech_cap_df.columns:
        return None
    rows = tech_cap_df[tech_cap_df["Code"] == zone]
    if rows.empty:
        return None
    cell = rows.iloc[0][col]
    if isinstance(cell, (list, np.ndarray)):
        arr = np.asarray(cell, dtype=float).ravel()
        return arr if arr.size > 0 else None
    return None


def _col_val(tech_cap_df: pd.DataFrame, zone: str, col: str) -> float:
    """Return the numeric capacity value for zone + column (0 if missing)."""
    if col not in tech_cap_df.columns:
        return 0.0
    rows = tech_cap_df[tech_cap_df["Code"] == zone]
    if rows.empty:
        return 0.0
    cell = rows.iloc[0][col]
    try:
        v = float(cell)
        return 0.0 if v != v else v  # NaN != NaN
    except Exception:
        return 0.0


def _node_latlon(node_df: pd.DataFrame, zone: str) -> tuple[float, float]:
    if node_df is None or node_df.empty:
        return 0.0, 0.0
    lat_col = next((c for c in node_df.columns if "lat" in c.lower()), None)
    lon_col = next((c for c in node_df.columns if "lon" in c.lower()), None)
    code_col = next((c for c in node_df.columns if c.lower() == "code"), None)
    if not all([lat_col, lon_col, code_col]):
        return 0.0, 0.0
    rows = node_df[node_df[code_col] == zone]
    if rows.empty:
        return 0.0, 0.0
    try:
        return float(rows.iloc[0][lat_col]), float(rows.iloc[0][lon_col])
    except Exception:
        return 0.0, 0.0


# ---------------------------------------------------------------------------
# Individual CSV writers
# ---------------------------------------------------------------------------

def _write_dicts(
    folder: str,
    zones: list[str],
    gen_rows: list[dict],
    circuit_ids: list[str],
    loadlevels: list[str],
    scenario: int,
    all_technologies: list[str],
    sc_name: str = "sc01",
    zone_to_area: dict | None = None,
    unique_areas: list | None = None,
) -> None:
    """Write all oT_Dict_* CSV files."""
    if zone_to_area is None:
        zone_to_area = {z: "Area1" for z in zones}
    if unique_areas is None:
        unique_areas = ["Area1"]

    # Each electricity node gets an auxiliary H2 node and Exports node, both
    # belonging to the same zone as their parent electricity node.
    h2_nodes  = [f"{z}_H2" for z in zones]
    exp_nodes = [f"{z}_Exp" for z in zones]
    all_nodes = list(zones) + h2_nodes + exp_nodes
    node_zone = list(zones) + list(zones) + list(zones)  # aux nodes -> parent zone

    _csv(folder, "oT_Dict_Node.csv",
         pd.DataFrame({"Node": all_nodes}))

    _csv(folder, "oT_Dict_Zone.csv",
         pd.DataFrame({"Zone": zones}))

    _csv(folder, "oT_Dict_NodeToZone.csv",
         pd.DataFrame({"Node": all_nodes, "Zone": node_zone}))

    _csv(folder, "oT_Dict_Area.csv",
         pd.DataFrame({"Area": unique_areas}))

    _csv(folder, "oT_Dict_ZoneToArea.csv",
         pd.DataFrame({"Zone": zones, "Area": [zone_to_area[z] for z in zones]}))

    _csv(folder, "oT_Dict_AreaToRegion.csv",
         pd.DataFrame({"Area": unique_areas, "Region": ["Region1"] * len(unique_areas)}))

    _csv(folder, "oT_Dict_Region.csv",
         pd.DataFrame({"Region": ["Region1"]}))

    gen_names = [r["Generator"] for r in gen_rows]
    _csv(folder, "oT_Dict_Generation.csv",
         pd.DataFrame({"Generator": gen_names}))

    _csv(folder, "oT_Dict_Technology.csv",
         pd.DataFrame({"Technology": sorted(set(all_technologies))}))

    _csv(folder, "oT_Dict_Line.csv",
         pd.DataFrame({"LineType": ["DC"]}))

    _csv(folder, "oT_Dict_Circuit.csv",
         pd.DataFrame({"Circuit": circuit_ids} if circuit_ids else {"Circuit": []}))

    _csv(folder, "oT_Dict_LoadLevel.csv",
         pd.DataFrame({"LoadLevel": loadlevels}))

    _csv(folder, "oT_Dict_Period.csv",
         pd.DataFrame({"Period": [scenario]}))

    _csv(folder, "oT_Dict_Scenario.csv",
         pd.DataFrame({"Scenario": [sc_name]}))

    _csv(folder, "oT_Dict_Stage.csv",
         pd.DataFrame({"Stage": ["Stage1"]}))

    _storage_types = [
        s for s in dict.fromkeys(
            r.get("StorageType", 0) for r in gen_rows
        ) if s != 0 and s != ""
    ]
    _csv(folder, "oT_Dict_Storage.csv",
         pd.DataFrame({"StorageType": _storage_types}))


def _write_data_static(
    folder: str,
    zones: list[str],
    node_df: pd.DataFrame,
    scenario: int,
    loadlevels: list[str],
    sc_name: str = "sc01",
    unique_areas: list | None = None,
    co2_cost: float = 0.0,
) -> None:
    """Write scalar / structural data CSVs."""
    if unique_areas is None:
        unique_areas = ["Area1"]

    # Node locations (aux H2 / Exports nodes share their parent's coordinates)
    loc_rows = []
    for z in zones:
        lat, lon = _node_latlon(node_df, z)
        loc_rows.append({"Node": z,          "Latitude": lat, "Longitude": lon})
        loc_rows.append({"Node": f"{z}_H2",  "Latitude": lat, "Longitude": lon})
        loc_rows.append({"Node": f"{z}_Exp", "Latitude": lat, "Longitude": lon})
    _csv(folder, "oT_Data_NodeLocation.csv", pd.DataFrame(loc_rows))

    _csv(folder, "oT_Data_Period.csv",
         pd.DataFrame({"Period": [scenario], "Weight": [1]}))

    _csv(folder, "oT_Data_Scenario.csv",
         pd.DataFrame({"Period": [scenario], "Scenario": [sc_name], "Probability": [1.0]}))

    _csv(folder, "oT_Data_Stage.csv",
         pd.DataFrame({"Stage": ["Stage1"], "Weight": [1]}))

    dur_rows = [
        {"Period": scenario, "Scenario": sc_name, "LoadLevel": ll, "Duration": 1, "Stage": "Stage1"}
        for ll in loadlevels
    ]
    _csv(folder, "oT_Data_Duration.csv", pd.DataFrame(dur_rows))

    _csv(folder, "oT_Data_Parameter.csv", pd.DataFrame([{
        "ENSCost": 10000, "HNSCost": 10000, "HTNSCost": 10000,
        "CO2Cost": round(co2_cost, 4), "UpReserveActivation": 0, "DwReserveActivation": 0,
        "MinRatioDwUp": 0, "MaxRatioDwUp": 1, "SBase": 100,
        "ReferenceNode": zones[0], "TimeStep": 1,
        "EconomicBaseYear": scenario, "AnnualDiscountRate": 0,
    }]))

    _csv(folder, "oT_Data_Option.csv", pd.DataFrame([{
        "IndBinGenInvest": 0, "IndBinGenRetirement": 0, "IndBinRsrInvest": 0,
        "IndBinNetInvest": 0, "IndBinNetH2Invest": 0, "IndBinNetHeatInvest": 0,
        "IndBinGenOperat": 1, "IndBinNetLosses": 0, "IndBinLineCommit": 0,
        "IndBinSingleNode": 0, "IndBinGenRamps": 1, "IndBinGenMinTime": 0,
    }]))

    _csv(folder, "oT_Data_Emission.csv",
         pd.DataFrame([{"Period": scenario, "Area": a, "CO2Emission": ""} for a in unique_areas]))

    _csv(folder, "oT_Data_RESEnergy.csv",
         pd.DataFrame([{"Period": scenario, "Area": a, "RESEnergy": ""} for a in unique_areas]))

    _csv(folder, "oT_Data_ReserveMargin.csv",
         pd.DataFrame([{"Period": scenario, "Area": a, "ReserveMargin": ""} for a in unique_areas]))


def _write_generation(
    folder: str,
    gen_rows: list[dict],
    scenario: int,
) -> None:
    gen_cols = [
        "Generator", "Node", "Technology",
        "MutuallyExclusive", "StorageType", "OutflowsType", "EnergyType",
        "MustRun", "OutflowsIncompatibility", "NoOperatingReserve",
        "BinaryInvestment", "BinaryRetirement", "BinaryCommitment",
        "InitialPeriod", "FinalPeriod",
        "MaximumPower", "MinimumPower",
        "MaximumPowerHeat", "MinimumPowerHeat",
        "MaximumCharge", "MinimumCharge",
        "InitialStorage", "MaximumStorage", "MinimumStorage",
        "Efficiency", "ShiftTime", "EFOR",
        "RampUp", "RampDown", "UpTime", "DownTime", "StableTime",
        "FuelCost", "LinearTerm", "ConstantTerm", "OMVariableCost",
        "OperReserveCost", "StartUpCost", "ShutDownCost",
        "CO2EmissionRate", "Availability",
        "FixedInvestmentCost", "FixedRetirementCost", "FixedChargeRate",
        "StorageInvestment", "Inertia",
        "MaximumReactivePower", "MinimumReactivePower",
        "InvestmentLo", "InvestmentUp", "RetirementLo", "RetirementUp",
        "ProductionFunctionHydro", "ProductionFunctionH2",
        "ProductionFunctionHeat", "ProductionFunctionH2ToHeat",
    ]
    rows = []
    for r in gen_rows:
        row = {
            # string identifiers
            "Generator": r["Generator"], "Node": r["Node"], "Technology": r["Technology"],
            "MutuallyExclusive": "",  # group name or blank
            # binary flags (must be 0 or 1, never blank)
            "MustRun":               r.get("MustRun", 0),
            "BinaryInvestment":      0, "BinaryRetirement":   0, "BinaryCommitment":   0,
            "NoOperatingReserve":    0, "OutflowsIncompatibility": 0,
            # type strings — 0 maps to idxCycle[0]=1 (hourly); avoids NaN on .astype('int')
            "StorageType":  "",
            "OutflowsType": "", "EnergyType": 0,
            # time bounds
            "InitialPeriod": scenario, "FinalPeriod": scenario,
            # power (MW)
            "MaximumPower":      r.get("MaximumPower", 0),
            "MinimumPower":      r.get("MinimumPower", 0),
            "MaximumPowerHeat":  0, "MinimumPowerHeat": 0,
            # storage (MW / MWh)
            "MaximumCharge":  r.get("MaximumCharge", 0),
            "MinimumCharge":  0,
            # InitialStorage = 50% of MaximumStorage (blank when no storage)
            "InitialStorage": round(float(r["MaximumStorage"]) * 0.5, 6)
                              if str(r.get("MaximumStorage", "")) not in ("", "0", "0.0") else "",
            "MaximumStorage": r.get("MaximumStorage", 0),
            "MinimumStorage": r.get("MinimumStorage", 0),
            # technical parameters
            "Efficiency": r.get("Efficiency", ""),  # blank = use LinearTerm as heat rate
            "ShiftTime": 0,
            "EFOR":      r.get("EFOR", 0),
            "RampUp":    r.get("RampUp", 0),
            "RampDown":  r.get("RampDown", 0),
            "UpTime": 0, "DownTime": 0, "StableTime": 0,
            "FuelCost":       r.get("FuelCost", 0),
            "LinearTerm":     round(1.0 / r["LinearTermEff"], 6) if r.get("LinearTermEff") else 1,
            "ConstantTerm":   0, "OMVariableCost": r.get("OMVariableCost", 0),
            "OperReserveCost": 0, "StartUpCost": 0, "ShutDownCost": 0,
            # emissions
            "CO2EmissionRate": r.get("CO2EmissionRate", 0),
            "Availability":    r.get("Availability", 1.0),
            # investment (all existing capacity, no investment modelled)
            "FixedInvestmentCost": 0, "FixedRetirementCost": 0, "FixedChargeRate": 0,
            "StorageInvestment": 0, "Inertia": 0,
            "MaximumReactivePower": 0, "MinimumReactivePower": 0,
            "InvestmentLo": 0, "InvestmentUp": 0, "RetirementLo": 0, "RetirementUp": 0,
            # production functions (not used in our setup)
            "ProductionFunctionHydro": 0, "ProductionFunctionH2": 0,
            "ProductionFunctionHeat": 0,  "ProductionFunctionH2ToHeat": 0,
        }
        rows.append(row)
    df = pd.DataFrame(rows, columns=gen_cols)
    df = df.map(lambda v: "" if isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0 else v)
    _csv(folder, "oT_Data_Generation.csv", df)


def _network_to_df(data) -> pd.DataFrame:
    """Convert a network_df value (numpy array or DataFrame) to a DataFrame."""
    if data is None:
        return pd.DataFrame()
    if isinstance(data, pd.DataFrame):
        return data
    try:
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()


def _get_loss_fraction(loss_df: pd.DataFrame, frm: str, to: str) -> float:
    if loss_df.empty:
        return 0.0
    match = loss_df[
        (loss_df.iloc[:, 0].astype(str) == frm) &
        (loss_df.iloc[:, 1].astype(str) == to)
    ]
    if not match.empty:
        try:
            return float(match.iloc[0, 3])
        except Exception:
            pass
    return 0.0


def _get_length(loss_df: pd.DataFrame, frm: str, to: str) -> float:
    """Return Length (km) for the frm→to line from the loss-fraction table."""
    if loss_df.empty:
        return 0.0
    match = loss_df[
        (loss_df.iloc[:, 0].astype(str) == frm) &
        (loss_df.iloc[:, 1].astype(str) == to)
    ]
    if not match.empty:
        try:
            return float(match.iloc[0, 2])
        except Exception:
            pass
    return 0.0


def _write_network(
    folder: str,
    network_df: dict[str, np.ndarray],
    zones: list[str],
    scenario: int,
) -> tuple[list[str], list[dict]]:
    """Write oT_Data_Network.csv (electricity only). Return (circuit_ids, rows)."""
    net_cols = [
        "InitialNode", "FinalNode", "Circuit", "LineType", "Switching",
        "InitialPeriod", "FinalPeriod", "Voltage", "Length",
        "LossFactor", "Reactance", "TTC", "TTCBck", "SecurityFactor",
        "FixedInvestmentCost", "FixedChargeRate", "BinaryInvestment",
        "SwOnTime", "SwOffTime", "Resistance", "Susceptance",
        "Tap", "AngMin", "AngMax", "InvestmentLo", "InvestmentUp",
    ]
    zone_set = set(zones)
    rows: list[dict] = []
    circuit_ids: list[str] = []

    cap_df  = _network_to_df(network_df.get("Line Capacity (Electricity)"))
    loss_df = _network_to_df(network_df.get("Loss Fraction (Electricity)"))

    for _, row in cap_df.iterrows():
        frm, to = str(row.iloc[0]), str(row.iloc[1])
        if frm not in zone_set or to not in zone_set:
            continue
        ttc, ttc_bck = 0.0, 0.0
        try:
            ttc = float(row.iloc[2])
        except Exception:
            pass
        try:
            ttc_bck = float(row.iloc[3])
        except Exception:
            pass
        loss = _get_loss_fraction(loss_df, frm, to)
        length = _get_length(loss_df, frm, to)
        cid = "AC1"
        if cid not in circuit_ids:
            circuit_ids.append(cid)
        line_row = {c: "" for c in net_cols}
        line_row.update({
            "InitialNode":    frm,
            "FinalNode":      to,
            "Circuit":        cid,
            "LineType":       "DC",
            "Switching":      "No",
            "InitialPeriod":  scenario,
            "FinalPeriod":    scenario,
            "Length":         round(length, 4),
            "LossFactor":     round(loss, 4),
            "Reactance":      round(0.4 * length, 4),
            "TTC":            ttc,
            "TTCBck":         ttc_bck,
            "SecurityFactor": 1,
            "BinaryInvestment": "",
        })
        rows.append(line_row)

    # Connect each electricity node to its auxiliary H2 and Exports nodes with a
    # high-capacity line (reactance 0.1) so power can flow to serve their demand.
    cid = "AC1"
    if cid not in circuit_ids:
        circuit_ids.append(cid)
    for z in zones:
        for aux in (f"{z}_H2", f"{z}_Exp"):
            aux_row = {c: "" for c in net_cols}
            aux_row.update({
                "InitialNode":    z,
                "FinalNode":      aux,
                "Circuit":        cid,
                "LineType":       "DC",
                "Switching":      "No",
                "InitialPeriod":  scenario,
                "FinalPeriod":    scenario,
                "Length":         0,
                "LossFactor":     0,
                "Reactance":      0.1,
                "TTC":            999999,
                "TTCBck":         999999,
                "SecurityFactor": 1,
                "BinaryInvestment": "",
            })
            rows.append(aux_row)

    _csv(folder, "oT_Data_Network.csv",
         pd.DataFrame(rows, columns=net_cols) if rows else pd.DataFrame(columns=net_cols))
    return circuit_ids, rows


def _write_network_h2(
    folder: str,
    network_df: dict[str, np.ndarray],
    zones: list[str],
    scenario: int,
) -> bool:
    """Write oT_Data_NetworkHydrogen.csv. Return True if any H2 lines written."""
    h2_cols = [
        "InitialNode", "FinalNode", "Circuit",
        "InitialPeriod", "FinalPeriod", "Length",
        "TTC", "TTCBck", "SecurityFactor",
        "FixedInvestmentCost", "FixedChargeRate", "BinaryInvestment",
        "InvestmentLo", "InvestmentUp",
    ]
    zone_set = set(zones)
    rows: list[dict] = []

    cap_df  = _network_to_df(network_df.get("Line Capacity (Hydrogen)"))
    loss_df = _network_to_df(network_df.get("Loss Fraction (Hydrogen)"))

    for _, row in cap_df.iterrows():
        frm, to = str(row.iloc[0]), str(row.iloc[1])
        if frm not in zone_set or to not in zone_set:
            continue
        ttc, ttc_bck = 0.0, 0.0
        try:
            ttc = float(row.iloc[2])
        except Exception:
            pass
        try:
            ttc_bck = float(row.iloc[3])
        except Exception:
            pass
        length = 0.0
        if not loss_df.empty:
            match = loss_df[
                (loss_df.iloc[:, 0].astype(str) == frm) &
                (loss_df.iloc[:, 1].astype(str) == to)
            ]
            if not match.empty:
                try:
                    length = float(match.iloc[0, 2])  # Length_km column
                except Exception:
                    pass
        line_row = {c: "" for c in h2_cols}
        line_row.update({
            "InitialNode":    frm,
            "FinalNode":      to,
            "Circuit":        "h2pipe1",
            "InitialPeriod":  scenario,
            "FinalPeriod":    scenario,
            "Length":         round(length, 1),
            "TTC":            round(ttc, 4),
            "TTCBck":         round(ttc_bck, 4),
            "SecurityFactor": 1,
        })
        rows.append(line_row)

    _csv(folder, "oT_Data_NetworkHydrogen.csv",
         pd.DataFrame(rows, columns=h2_cols) if rows else pd.DataFrame(columns=h2_cols))
    return len(rows) > 0


def _write_demand(
    folder: str,
    profiles_df: dict[str, list[dict]],
    zones: list[str],
    selected_hours: int,
    scenario: int,
    loadlevels: list[str],
    sc_name: str = "sc01",
    tech_char_df: pd.DataFrame | None = None,
    export_df: pd.DataFrame | None = None,
) -> None:
    # char index of the Electrolyser row in the tech-characteristic arrays
    _ELECTROLYSER_IDX = 38
    demand_data: dict[str, list] = {}
    for zone in zones:
        # Electricity demand on the electricity node (unchanged)
        arr = _get_profile(profiles_df, zone, "Electricity Demand Profile")
        elec = np.array(arr[:selected_hours], dtype=float) if arr is not None \
            else np.zeros(selected_hours)
        demand_data[zone] = list(elec)

        # Hydrogen demand (electricity-equivalent) on the {zone}_H2 node
        h2_demand = np.zeros(selected_hours)
        h2 = _get_profile(profiles_df, zone, "Hydrogen Demand Profile")
        if h2 is not None and tech_char_df is not None:
            eff = _get_char(tech_char_df, zone, "Efficiency (%)", _ELECTROLYSER_IDX, 0.0)
            if eff > 0:
                h2 = np.asarray(h2[:selected_hours], dtype=float)
                n = min(len(h2_demand), len(h2))
                h2_demand[:n] = h2[:n] / eff
        demand_data[f"{zone}_H2"] = list(h2_demand)

        # Net exports to zones outside the selection on the {zone}_Exp node
        exp_demand = np.zeros(selected_hours)
        if isinstance(export_df, pd.DataFrame) and not export_df.empty:
            exp_cols = [c for c in export_df.columns if str(c).startswith(f"Exports_{zone}_")]
            if exp_cols:
                net = export_df[exp_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
                net = np.asarray(net.to_numpy()[:selected_hours], dtype=float)
                n = min(len(exp_demand), len(net))
                exp_demand[:n] = net[:n]
        demand_data[f"{zone}_Exp"] = list(exp_demand)

    all_nodes = list(zones) + [f"{z}_H2" for z in zones] + [f"{z}_Exp" for z in zones]
    rows = []
    for i, ll in enumerate(loadlevels):
        row: dict = {"Period": scenario, "Scenario": sc_name, "LoadLevel": ll}
        for node in all_nodes:
            col = demand_data[node]
            v = float(col[i]) if i < len(col) else 0.0
            row[node] = round(v, 4) if v != 0 else 1e-6  # 1 W floor when demand is 0
        rows.append(row)
    _csv(folder, "oT_Data_Demand.csv", pd.DataFrame(rows))


def _write_variable_profiles(
    folder: str,
    profiles_df: dict[str, list[dict]],
    tech_cap_df: pd.DataFrame,
    gen_rows: list[dict],
    selected_hours: int,
    scenario: int,
    loadlevels: list[str],
    sc_name: str = "sc01",
) -> None:
    """Write oT_Data_VariableMaxGeneration (and blank Variable* files)."""
    # Build set of RES generators that have a profile
    # gen_name â†’ (zone, suffix, max_power)
    gen_index = {r["Generator"]: r for r in gen_rows if r.get("is_RES")}

    # profile_key â†’ {gen_name: np.ndarray}
    col_data: dict[str, np.ndarray] = {}
    for profile_key, suffix in _PROFILE_TO_SUFFIX.items():
        for r in gen_rows:
            if not r.get("is_RES"):
                continue
            if r.get("suffix") != suffix:
                continue
            zone = r["Node"]
            arr = _get_profile(profiles_df, zone, profile_key)
            if arr is None:
                continue
            max_p = r.get("MaximumPower", 0.0)
            gen_name = r["Generator"]
            # Capacity factor Ã— installed capacity (profiles are 0-1 factors)
            cf = arr[:selected_hours]
            if cf.max() <= 1.01:
                values = cf * max_p
            else:
                values = cf  # already in MW
            col_data[gen_name] = values

    # Techs whose VariableMaxGeneration comes straight from an hourly (MW/h)
    # timeseries in tech_cap_df (used directly, no capacity multiplication).
    _DIRECT_HOURLY = {
        "Other Non-RES (MW)":         "Other Non-RES (MW/h)",
        "Other RES (biomass) (MW)":   "Other RES (biomass) (MW/h)",
        "Other RES (geothermal) (MW)": "Other RES (geothermal) (MW/h)",
        "Other RES (marine) (MW)":    "Other RES (marine) (MW/h)",
        "Other RES (waste) (MW)":     "Other RES (waste) (MW/h)",
        "Other RES (unknown) (MW)":   "Other RES (unknown) (MW/h)",
    }
    for r in gen_rows:
        cap_col = r.get("cap_col", "")
        if cap_col in _DIRECT_HOURLY:
            ts_col = _DIRECT_HOURLY[cap_col]
        elif cap_col.startswith("DSR") and cap_col.endswith("(MW)"):
            ts_col = cap_col.replace("(MW)", "(MW/h)")
        else:
            continue
        arr = _get_hourly_series(tech_cap_df, r["Node"], ts_col)
        if arr is None or len(arr) == 0:
            continue
        col_data[r["Generator"]] = np.asarray(arr[:selected_hours], dtype=float)

    # Full generator label list (all generators, in gen_rows order)
    all_gen_names = [r["Generator"] for r in gen_rows]

    # VariableMaxGeneration: keep computed values, add remaining generators empty.
    rows = []
    for i, ll in enumerate(loadlevels):
        row: dict = {"Period": scenario, "Scenario": sc_name, "LoadLevel": ll}
        for gn in all_gen_names:
            if gn in col_data:
                v = col_data[gn][i] if i < len(col_data[gn]) else ""
                if v == "":
                    row[gn] = ""
                else:
                    fv = round(float(v), 4)
                    row[gn] = fv if fv != 0 else 1e-6  # 1 W floor when CF×capacity is 0
            else:
                row[gn] = ""
        rows.append(row)

    df = pd.DataFrame(rows)
    _csv(folder, "oT_Data_VariableMaxGeneration.csv", df)

    # Blank variable files: full generator label columns with empty values.
    blank_rows = []
    for ll in loadlevels:
        row = {"Period": scenario, "Scenario": sc_name, "LoadLevel": ll}
        for gn in all_gen_names:
            row[gn] = ""
        blank_rows.append(row)
    blank_df = pd.DataFrame(blank_rows)

    for fname in [
        "oT_Data_VariableMinGeneration.csv",
        "oT_Data_VariableFuelCost.csv",
        "oT_Data_VariableEmissionCost.csv",
        "oT_Data_VariableMaxConsumption.csv",
        "oT_Data_VariableMinConsumption.csv",
        "oT_Data_VariableMaxStorage.csv",
        "oT_Data_VariableMinStorage.csv",
        "oT_Data_VariableMaxEnergy.csv",
        "oT_Data_VariableMinEnergy.csv",
    ]:
        _csv(folder, fname, blank_df)

    # Energy inflows/outflows apply to hydro units only.
    # suffix -> (Flow Energy profile key, hours per source period: daily=24, weekly=168)
    _HYDRO_FLOW = {
        "HydroRoR":  ("River Flow Energy",     24),
        "HydroPond": ("Pondage Flow Energy",   24),
        "HydroRes":  ("Reservoir Flow Energy", 168),
        "HydroPS_o": ("Open_PS Flow Energy",   168),
        "HydroPS_c": ("Closed_PS Flow Energy", 168),
    }
    hydro_rowdefs = [r for r in gen_rows if r.get("suffix", "") in _HYDRO_FLOW]
    hydro_gens = [r["Generator"] for r in hydro_rowdefs]

    # Fill EnergyInflows from Flow Energy: each period's value is repeated across
    # the hours of that period (daily = 24 h, weekly = 168 h).
    inflow_cols: dict[str, list] = {}
    for r in hydro_rowdefs:
        gn = r["Generator"]
        flow = _HYDRO_FLOW.get(r.get("suffix", ""))
        series = _get_profile(profiles_df, r["Node"], flow[0]) if flow else None
        if flow is None or series is None or len(series) == 0:
            inflow_cols[gn] = ["" for _ in loadlevels]
            continue
        period_hours = flow[1]
        inflow_cols[gn] = [
            round(float(series[min(h // period_hours, len(series) - 1)]), 6)
            for h in range(len(loadlevels))
        ]

    inflow_rows = []
    for i, ll in enumerate(loadlevels):
        row = {"Period": scenario, "Scenario": sc_name, "LoadLevel": ll}
        for gn in hydro_gens:
            row[gn] = inflow_cols[gn][i]
        inflow_rows.append(row)
    _csv(folder, "oT_Data_EnergyInflows.csv", pd.DataFrame(inflow_rows))

    # Outflows: hydro columns, left empty
    outflow_rows = []
    for ll in loadlevels:
        row = {"Period": scenario, "Scenario": sc_name, "LoadLevel": ll}
        for gn in hydro_gens:
            row[gn] = ""
        outflow_rows.append(row)
    _csv(folder, "oT_Data_EnergyOutflows.csv", pd.DataFrame(outflow_rows))


def _write_reserve_files(
    folder: str,
    scenario: int,
    loadlevels: list[str],
    sc_name: str = "sc01",
    unique_areas: list | None = None,
    area_fcr: dict[str, float] | None = None,
) -> None:
    if unique_areas is None:
        unique_areas = ["Area1"]
    area_fcr = area_fcr or {}

    up_rows = [
        dict({"Period": scenario, "Scenario": sc_name, "LoadLevel": ll},
             **{a: round(area_fcr.get(a, 0.0), 4) for a in unique_areas})
        for ll in loadlevels
    ]
    _csv(folder, "oT_Data_OperatingReserveUp.csv", pd.DataFrame(up_rows))

    down_rows = [
        dict({"Period": scenario, "Scenario": sc_name, "LoadLevel": ll},
             **{a: "" for a in unique_areas})
        for ll in loadlevels
    ]
    _csv(folder, "oT_Data_OperatingReserveDown.csv", pd.DataFrame(down_rows))

    inertia_rows = [
        dict({"Period": scenario, "Scenario": sc_name, "LoadLevel": ll},
             **{a: "" for a in unique_areas})
        for ll in loadlevels
    ]
    _csv(folder, "oT_Data_Inertia.csv", pd.DataFrame(inertia_rows))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def export_opentepes(
    tech_cap_df: pd.DataFrame,
    tech_char_df: pd.DataFrame,
    profiles_df: dict[str, list[dict]],
    export_df: pd.DataFrame,
    storage_df: dict[str, np.ndarray],
    network_df: dict[str, np.ndarray],
    node_df: pd.DataFrame,
    selected_zones: list[str],
    selected_hours: int,
    scenario: int,
    output_folder: str,
    climate_year: int = 2009,
    commodity_prices: dict[str, float] | None = None,
    lignite_groups: dict[str, str] | None = None,
    reserve_df: pd.DataFrame | None = None,
) -> None:
    """Write the complete openTEPES CSV input set to *output_folder*.

    Args:
        tech_cap_df:    Technology capacity DataFrame (one row per zone).
        tech_char_df:   Technology characteristics DataFrame.
        profiles_df:    Time-series profiles dict.
        export_df:      Cross-border exchange flows DataFrame.
        storage_df:     Storage capacity arrays.
        network_df:     Network lines dict.
        node_df:        Nodes table (for lat/lon).
        selected_zones: Zone codes to include.
        selected_hours: Number of hourly time steps.
        scenario:       Scenario year (e.g. 2030).
        output_folder:  Destination directory for CSV files.
    """
    os.makedirs(output_folder, exist_ok=True)
    loadlevels = _make_loadlevels(selected_hours)
    sc_name = f"CY_{climate_year}"

    if commodity_prices is None:
        commodity_prices = {}
    if lignite_groups is None:
        lignite_groups = {}

    # Build zone -> area mapping (country name, spaces replaced with "_")
    zone_to_area: dict[str, str] = {}
    for z in selected_zones:
        area = z  # fallback: use zone code itself
        if isinstance(node_df, pd.DataFrame) and {"Code", "Location"}.issubset(node_df.columns):
            match = node_df[node_df["Code"] == z]
            if not match.empty:
                area = _clean_area(match["Location"].iloc[0])
        zone_to_area[z] = area
    unique_areas: list[str] = list(dict.fromkeys(zone_to_area.values()))

    # FCR (total) reserve per area = sum of member zones' Total (FCR) (MW/h)
    area_fcr: dict[str, float] = {a: 0.0 for a in unique_areas}
    if isinstance(reserve_df, pd.DataFrame) and "Code" in reserve_df.columns \
            and "Total (FCR) (MW/h)" in reserve_df.columns:
        for z in selected_zones:
            row = reserve_df[reserve_df["Code"] == z]
            if row.empty:
                continue
            try:
                val = float(row["Total (FCR) (MW/h)"].iloc[0])
            except (TypeError, ValueError):
                continue
            if val == val:  # not NaN
                area_fcr[zone_to_area[z]] += val

    # â"€â"€ Build generator list â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    gen_rows: list[dict] = []
    all_technologies: list[str] = []

    for zone in selected_zones:
        # DSR columns with capacity present in this zone
        _single_dsr = len([
            c for c, *_ in _TECH_ENTRIES
            if c.startswith("DSR") and _col_val(tech_cap_df, zone, c) != 0
        ]) == 1
        for cap_col, suffix, ot_tech, is_res, char_idx in _TECH_ENTRIES:
            # Skip DSR types that have no capacity in this zone
            if cap_col.startswith("DSR") and _col_val(tech_cap_df, zone, cap_col) == 0:
                continue

            if cap_col.startswith("DSR"):
                # Single DSR type → label "DSR"; Technology is always "DSR"
                gen_label = "DSR" if _single_dsr else _tech_label(cap_col)
                tech_lbl  = "DSR"
            else:
                gen_label = tech_lbl = _tech_label(cap_col)
            gen_name = f"{zone}_{gen_label}"
            all_technologies.append(tech_lbl)

            # Capacity: Battery stores MWh in tech_cap_df; get MW from tech_char_df
            if cap_col in _CHAR_POWER_ENTRIES:
                p_col, c_col, cidx = _CHAR_POWER_ENTRIES[cap_col]
                max_p      = _get_char(tech_char_df, zone, p_col, cidx, 0.0)
                max_charge = _get_char(tech_char_df, zone, c_col, cidx, 0.0)
                max_storage = _col_val(tech_cap_df, zone, cap_col)
            elif cap_col == "Electrolyser (MW)":
                # Electrolyser is a consumer: its capacity goes to MaximumCharge
                max_p       = 0.0
                max_charge  = _col_val(tech_cap_df, zone, cap_col)
                max_storage = 0.0
            else:
                max_p = _col_val(tech_cap_df, zone, cap_col)
                storage_mwh_col = _STORAGE_MW_PAIRS.get(cap_col)
                max_storage = _col_val(tech_cap_df, zone, storage_mwh_col) if storage_mwh_col else 0.0
                pump_col    = _PUMP_PAIRS.get(cap_col)
                max_charge  = _col_val(tech_cap_df, zone, pump_col) if pump_col else 0.0

            # â"€â"€ Characteristics â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
            min_pct     = _get_char(tech_char_df, zone, "Minimum Stable Power (%)", char_idx, 0.0) / 100.0
            ramp_up     = _get_char(tech_char_df, zone, "Ramp-Up Rate (MW/h)", char_idx, 0.0)
            ramp_dn     = _get_char(tech_char_df, zone, "Ramp-Down Rate (MW/h)", char_idx, 0.0)
            fuel_cost   = _get_char(tech_char_df, zone, "Price (EUR/MWh)", char_idx, 0.0)
            efficiency  = _get_char(tech_char_df, zone, "Efficiency (%)", char_idx, 0.0)
            co2_rate    = _get_char(tech_char_df, zone, "CO2 Factor (ton/MWh)", char_idx, 0.0)

            # Predefined efficiency written to output: 0.9 battery, 0.7 pump, else 1
            out_eff = (0.9 if cap_col in _CHAR_POWER_ENTRIES
                       else 0.7 if cap_col in _PUMP_PAIRS
                       else 1.0)

            # LinearTerm (heat rate) is only defined for thermal units and DSR;
            # everything else uses an efficiency of 1 (→ LinearTerm = 1).
            is_thermal = ot_tech in {"Nuclear", "Coal", "Lignite", "Gas", "Oil", "Hydrogen"}
            lin_eff = efficiency if (is_thermal or cap_col.startswith("DSR")) else 1.0

            min_p    = round(min_pct * max_p, 2) if (not is_res and min_pct > 0) else 0.0

            # Must Run: average 12 monthly values; if any > 0, flag unit as must-run
            must_run_pct = _get_char_monthly_avg(tech_char_df, zone, "Must Run (%)", char_idx, 0.0)
            if must_run_pct > 0 and not is_res:
                must_run_flag = "Yes"
                min_p = round(max(must_run_pct / 100.0, min_pct) * max_p, 2)
            else:
                must_run_flag = ""

            efor = _get_char(tech_char_df, zone, "Annual Forced Outage (%)", char_idx, 0.0) / 100.0

            # Commodity fuel cost from TYNDP 2024 prices (EUR/MWh)
            if suffix in _SUFFIX_FUEL:
                fuel_key = _SUFFIX_FUEL[suffix]
            elif ot_tech == "Lignite":
                country = zone.rstrip("0123456789")
                fuel_key = lignite_groups.get(country, "Lignite_G2")
            else:
                fuel_key = _OT_TECH_FUEL.get(ot_tech, "")
            commodity_fuel = round(commodity_prices.get(fuel_key, 0.0), 4) if fuel_key else 0.0

            row: dict = {
                "Generator":    gen_name,
                "Node":         zone,
                "Technology":   tech_lbl,
                "MaximumPower": round(max_p, 2),
                "MinimumPower": min_p,
                "MaximumCharge": round(abs(max_charge), 2) if max_charge != 0 else "",
                "MaximumStorage": round(max_storage / 1000.0, 6) if max_storage > 0 else "",
                "MinimumStorage": "",
                "StorageType":  "",
                "EFOR":         round(efor, 4),
                "RampUp":       round(ramp_up, 2) if ramp_up > 0 else "",
                "RampDown":     round(ramp_dn, 2) if ramp_dn > 0 else "",
                "FuelCost":     commodity_fuel,
                "OMVariableCost": round(fuel_cost, 2),
                "Efficiency":   out_eff,
                "LinearTermEff": lin_eff,
                "CO2EmissionRate": round(co2_rate, 6),
                "Availability": 1,
                "MustRun":      must_run_flag,
                "is_RES":       is_res,
                "suffix":       suffix,
                "cap_col":      cap_col,
            }
            gen_rows.append(row)

    # â"€â"€ Write Dict files â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    circuit_ids, _ = _write_network(output_folder, network_df, selected_zones, scenario)
    _write_dicts(output_folder, selected_zones, gen_rows, circuit_ids, loadlevels, scenario, all_technologies, sc_name, zone_to_area, unique_areas)

    # -- Write Data files ----------------------------------------------------
    _write_data_static(output_folder, selected_zones, node_df, scenario, loadlevels, sc_name, unique_areas,
                       co2_cost=commodity_prices.get("CO2_price", 0.0) if commodity_prices else 0.0)
    _write_generation(output_folder, gen_rows, scenario)
    _write_demand(output_folder, profiles_df, selected_zones, selected_hours, scenario, loadlevels, sc_name,
                  tech_char_df=tech_char_df, export_df=export_df)
    # Hydrogen demand is folded into electricity demand via the electrolyser, so the
    # hydrogen carrier is not modelled separately. Emitting oT_Data_NetworkHydrogen.csv
    # would switch on openTEPES' pIndHydrogen and then fail on the (now absent)
    # oT_Data_DemandHydrogen table, so the H2 network file is intentionally not written.
    _write_variable_profiles(output_folder, profiles_df, tech_cap_df, gen_rows, selected_hours, scenario, loadlevels, sc_name)
    _write_reserve_files(output_folder, scenario, loadlevels, sc_name, unique_areas, area_fcr)

    # Tag every output file with an _NT{Period} suffix (e.g. oT_Data_Generation_NT2030.csv)
    # so a run's CSVs are self-identifying. The notebook strips this suffix before
    # applying openTEPES' own CaseName suffix when copying.
    suffix = f"_NT{scenario}"
    for fn in os.listdir(output_folder):
        if not (fn.startswith("oT_") and fn.endswith(".csv")):
            continue
        base = fn[:-4]
        if base.endswith(suffix):
            continue
        os.replace(os.path.join(output_folder, fn),
                   os.path.join(output_folder, f"{base}{suffix}.csv"))

    print(f"openTEPES CSV files written to: {output_folder}")
