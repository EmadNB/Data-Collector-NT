"""Constants for the ENTSO-E data collector."""

# ---------------------------------------------------------------------------
# Scenario / infrastructure options
# ---------------------------------------------------------------------------

VALID_SCENARIOS = [2030, 2040, 2050]

GAS_PIPE_OPTIONS = ["Existing", "Low", "Advanced", "High"]
HYDROGEN_PIPE_OPTIONS = ["PCI/PMI", "Advanced", "Less-Advanced"]
GAS_STORAGE_OPTIONS = ["Low", "Advanced", "High"]
HYDROGEN_STORAGE_OPTIONS = ["PCI/PMI", "Advanced", "Less-Advanced"]
GAS_TERMINAL_OPTIONS = ["Low", "Advanced", "High"]
HYDROGEN_TERMINAL_OPTIONS = ["PCI/PMI", "Advanced", "Less-Advanced"]
OUTPUT_MODES = ["Normal", "openTEPES"]

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

EARTH_RADIUS_KM: float = 6371.0088
DEFAULT_LOSS_PER_100KM: float = 0.3

# Gas / hydrogen unit conversion: GWh/day → MW  (× 1000 / 24)
GAS_UNIT_FACTOR: float = 1000.0 / 24.0

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

# DSR and Other Non-RES have a variable number of type columns on their PEMMDB
# sheets (DSR: 11 for most zones, 19 for DE00; Other Non-RES: uniformly 27). The
# DSR count is detected per run (max across the selected zones); Other Non-RES is
# fixed. build_tech_columns() produces the capacity DataFrame column order for a
# given DSR count so the loader, Normal export, and openTEPES stay consistent.
OTHER_NONRES_COUNT = 27
DSR_DEFAULT_COUNT = 10


def build_tech_columns(n_dsr: int, n_nores: int = OTHER_NONRES_COUNT) -> list[str]:
    """Return the ``tech_cap_df`` column order for *n_dsr* DSR type columns."""
    return [
        "Code",
        "Nuclear (MW)",
        "Hard Coal (old1) (MW)", "Hard Coal (old2) (MW)",
        "Hard Coal (new) (MW)", "Hard Coal (ccs) (MW)",
        "Lignite (old1) (MW)", "Lignite (old2) (MW)",
        "Lignite (new) (MW)", "Lignite (ccs) (MW)",
        "Gas (conv_old1) (MW)", "Gas (conv_old2) (MW)",
        "Gas (ccgt_old1) (MW)", "Gas (ccgt_old2) (MW)",
        "Gas (ccgt_new) (MW)", "Gas (ccgt_ccs) (MW)",
        "Gas (ocgt_old) (MW)", "Gas (ocgt_new) (MW)",
        "Light Oil (MW)", "Heavy oil (old1) (MW)", "Heavy oil (old2) (MW)",
        "Oil shale (old) (MW)", "Oil shale (new) (MW)",
        "Gas (ccgt_pre1) (MW)", "Gas (ccgt_pre2) (MW)",
        "Hydrogen (fc) (MW)", "Hydrogen (ccgt) (MW)",
        *[f"Other Non-RES{i+1} (MW)" for i in range(n_nores)],
        *[f"DSR{i+1} (MW)" for i in range(n_dsr)],
        "Battery (MWh)", "Electrolyser (MW)",
        "Wind (onshore) (MW)", "Wind (offshore) (MW)",
        "Solar (thermal) (MW)", "Solar (MW)", "Solar (rooftop) (MW)",
        "Solar (thermal_with_storage) (MW)",
        "Hydro (river) (MW)",
        "Hydro (pondage) (MWh)", "Hydro (pondage) (MW)",
        "Hydro (reservoir) (MWh)", "Hydro (reservoir) (MW)",
        "Hydro (open_ps) (MWh)", "Hydro (open_ps_turbine) (MW)", "Hydro (open_ps_pump) (MW)",
        "Hydro (closed_ps) (MWh)", "Hydro (closed_ps_turbine) (MW)", "Hydro (closed_ps_pump) (MW)",
        "Other RES (biomass) (MW)", "Other RES (geothermal) (MW)",
        "Other RES (marine) (MW)", "Other RES (waste) (MW)", "Other RES (unknown) (MW)",
        "Solar (thermal_with_storage) (MWh)", "Electrolyser (MWh)",
        "Exports_non_ENTSOe (MW/h)",
        *[f"DSR{i+1} (MW/h)" for i in range(n_dsr)],
        "Other RES (biomass) (MW/h)", "Other RES (geothermal) (MW/h)",
        "Other RES (marine) (MW/h)", "Other RES (waste) (MW/h)",
        "Other RES (unknown) (MW/h)",
        *[f"Other Non-RES{i+1} (MW/h)" for i in range(n_nores)],
    ]


# Default (used only as a fallback / for imports); the loader rebuilds per run.
TECH_COLUMNS = build_tech_columns(DSR_DEFAULT_COUNT)

TECH_CHAR_COLUMNS = [
    "Code",
    "Number of Units",
    "Number of Biofuel Units",
    "Biofuel Usage (%)",
    "Must Run (Number of units)",
    "Must Run (%)",
    "Annual Forced Outage (%)",
    "Annual Forced Outage (Days)",
    "Annual Forced Outage in Winter (%)",
    "Minimum Stable Power (%)",
    "Ramp-Up Rate (MW/h)",
    "Ramp-Down Rate (MW/h)",
    "Fixed Generation Reduction (%)",
    "Maximum Number of Units in Maintenace",
    "Price (EUR/MWh)",
    "Efficiency (%)",
    "CO2 Factor (ton/MWh)",
    "Net maximum capacity - generation perspective (MW)",
    "Net maximum capacity - demand perspective (MW)",
]

RESERVE_COLUMNS = [
    "Code",
    "Thermal (FCR) (MW/h)",
    "Hydro (FCR) (MW/h)",
    "Total (FCR) (MW/h)",
    "Thermal (FRR) (MW/h)",
    "Hydro (FRR) (MW/h)",
    "Total (FRR) (MW/h)",
]

# ---------------------------------------------------------------------------
# Profile catalogue
# ---------------------------------------------------------------------------

PECD_FILE_TEMPLATES: dict[str, dict[int, str]] = {
    "CSP_noStorage Profile": {
        2030: r"inputs\PECD\2030\PECD_CSP_noStorage_2030_{}_edition 2023.2.csv",
        2040: r"inputs\PECD\2040\PECD_CSP_noStorage_2040_{}_edition 2023.2.csv",
        2050: r"inputs\PECD\2050\PECD_CSP_noStorage_2050_{}_edition 2023.2.csv",
    },
    "CSP_withStorage_D Profile": {
        2030: r"inputs\PECD\2030\PECD_CSP_withStorage_7h_dispatched_2030_{}_edition 2023.2.csv",
        2040: r"inputs\PECD\2040\PECD_CSP_withStorage_7h_dispatched_2040_{}_edition 2023.2.csv",
        2050: r"inputs\PECD\2050\PECD_CSP_withStorage_7h_dispatched_2050_{}_edition 2023.2.csv",
    },
    "CSP_withStorage_PreD Profile": {
        2030: r"inputs\PECD\2030\PECD_CSP_withStorage_7h_preDispatch_2030_{}_edition 2023.2.csv",
        2040: r"inputs\PECD\2040\PECD_CSP_withStorage_7h_preDispatch_2040_{}_edition 2023.2.csv",
        2050: r"inputs\PECD\2050\PECD_CSP_withStorage_7h_preDispatch_2050_{}_edition 2023.2.csv",
    },
    "Solar Profile": {
        2030: r"inputs\PECD\2030\PECD_LFSolarPV_2030_{}_edition 2023.2.csv",
        2040: r"inputs\PECD\2040\PECD_LFSolarPV_2040_{}_edition 2023.2.csv",
        2050: r"inputs\PECD\2050\PECD_LFSolarPV_2050_{}_edition 2023.2.csv",
    },
    "Solar_Rooftop Profile": {
        2030: r"inputs\PECD\2030\PECD_LFSolarPVRooftop_2030_{}_edition 2023.2.csv",
        2040: r"inputs\PECD\2040\PECD_LFSolarPVRooftop_2040_{}_edition 2023.2.csv",
        2050: r"inputs\PECD\2050\PECD_LFSolarPVRooftop_2050_{}_edition 2023.2.csv",
    },
    "Solar_Utility Profile": {
        2030: r"inputs\PECD\2030\PECD_LFSolarPVUtility_2030_{}_edition 2023.2.csv",
        2040: r"inputs\PECD\2040\PECD_LFSolarPVUtility_2040_{}_edition 2023.2.csv",
        2050: r"inputs\PECD\2050\PECD_LFSolarPVUtility_2050_{}_edition 2023.2.csv",
    },
    "Wind_Offshore Profile": {
        2030: r"inputs\PECD\2030\PECD_Wind_Offshore_2030_{}_edition 2023.2.csv",
        2040: r"inputs\PECD\2040\PECD_Wind_Offshore_2040_{}_edition 2023.2.csv",
        2050: r"inputs\PECD\2050\PECD_Wind_Offshore_2050_{}_edition 2023.2.csv",
    },
    "Wind_Onshore Profile": {
        2030: r"inputs\PECD\2030\PECD_Wind_Onshore_2030_{}_edition 2023.2.csv",
        2040: r"inputs\PECD\2040\PECD_Wind_Onshore_2040_{}_edition 2023.2.csv",
        2050: r"inputs\PECD\2050\PECD_Wind_Onshore_2050_{}_edition 2023.2.csv",
    },
}

HYDRO_FILE_TEMPLATES: dict[int, str] = {
    2030: r"inputs\Hydro Inflows\2030\PEMMDB_{}_Hydro_Inflows_2030.xlsx",
    2040: r"inputs\Hydro Inflows\2040\PEMMDB_{}_Hydro_Inflows_2040.xlsx",
    2050: r"inputs\Hydro Inflows\2050\PEMMDB_{}_Hydro_Inflows_2050.xlsx",
}

HYDRO_SHEET_NAMES: dict[str, str] = {
    "River Flow Energy": "Run of River - Year Dependent",
    "Pondage Flow Energy": "Pondage - Year Dependent",
    "Reservoir Flow Energy": "Reservoir - Year Dependent",
    "Open_PS Flow Energy": "PS Open - Year Dependent",
    "Closed_PS Flow Energy": "PS Closed - Year Dependent",
}

# Expected series length per hydro inflow type
HYDRO_TARGET_LENGTHS: dict[str, int] = {
    "River Flow Energy": 366,
    "Pondage Flow Energy": 366,
    "Reservoir Flow Energy": 53,
    "Open_PS Flow Energy": 53,
    "Closed_PS Flow Energy": 53,
}

# Hydro raw unit is GWh → convert to MWh
HYDRO_SCALE_FACTOR: float = 1000.0

# Rooftop PV always uses 8760 h regardless of selected_hours
SOLAR_ROOFTOP_TARGET_LEN: int = 8760

# Common data file paths
FILEPATH_CO2_FACTORS = "inputs/CO2 emission factors in TYNDP2024 v2.xlsx"
FILEPATH_COMMON_DATA = "inputs/Common data/Common Data.xlsx"
FILEPATH_NETWORKS = "inputs/Networks.xlsx"
FILEPATH_STORAGES = "inputs/Storages.xlsx"
FILEPATH_TERMINALS = "inputs/Terminals.xlsx"
FILEPATH_COMMODITY_PRICES = (
    "inputs/Prices/2023 06 22 TYNDP 2024 Commodity prices Final.xlsx"
)
