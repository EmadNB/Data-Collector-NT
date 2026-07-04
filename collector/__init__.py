"""ENTSO-E data collector package.

Top-level exports give single-import access to the most commonly used
functions across all sub-packages.

Usage::

    from collector import load_nodes, load_tech_capacities, plot_capacity_by_technology
    from collector.data import load_all_profiles
    from collector.processing import build_network_data
    from collector.models import export_all_zones
"""

# Data loaders
from collector.data.loader import (
    load_all_profiles,
    load_closed_ps_flow_profiles,
    load_crossborder_exchanges,
    load_csp_dispatch_profiles,
    load_csp_no_storage_profiles,
    load_csp_predispatch_profiles,
    load_electricity_demand_profiles,
    load_gas_demand_profiles,
    load_hydrogen_demand_profiles,
    load_network_edges,
    load_network_storages,
    load_network_terminals,
    load_nodes,
    load_open_ps_flow_profiles,
    load_pondage_flow_profiles,
    load_reservoir_flow_profiles,
    load_reserve_requirements,
    load_river_flow_profiles,
    load_solar_profiles,
    load_solar_rooftop_profiles,
    load_solar_utility_profiles,
    load_tech_capacities,
    load_tech_characteristics,
    load_wind_offshore_profiles,
    load_wind_onshore_profiles,
)

# Processing / transforms
from collector.processing.transforms import (
    build_network_data,
    build_storage_data,
    build_terminal_data,
    compute_lengths_and_losses,
    haversine_km,
    normalise_profiles_to_hourly,
)

# Visualisation
from collector.visualization.plots import (
    plot_availability_report,
    plot_capacity_by_technology,
    plot_capacity_by_zone,
    plot_electricity_network_map,
    plot_gas_network_map,
    plot_hydrogen_network_map,
    plot_profiles,
    plot_storage_capacity_by_technology,
    plot_storage_capacity_by_zone,
)

# Export / aggregation
from collector.models.core import (
    build_availability_summary,
    export_all_zones,
    export_network_data,
    export_zone_data,
)

# Utilities
from collector.utils.helpers import (
    build_zone_display_map,
    create_output_directories,
    expand_profile_to_hourly,
    get_pemmdb_filepath,
    validate_option,
    validate_scenario,
)

__all__ = [
    # loaders
    "load_nodes",
    "load_network_edges",
    "load_network_storages",
    "load_network_terminals",
    "load_tech_capacities",
    "load_tech_characteristics",
    "load_reserve_requirements",
    "load_crossborder_exchanges",
    "load_electricity_demand_profiles",
    "load_hydrogen_demand_profiles",
    "load_gas_demand_profiles",
    "load_csp_no_storage_profiles",
    "load_csp_dispatch_profiles",
    "load_csp_predispatch_profiles",
    "load_solar_profiles",
    "load_solar_rooftop_profiles",
    "load_solar_utility_profiles",
    "load_wind_offshore_profiles",
    "load_wind_onshore_profiles",
    "load_river_flow_profiles",
    "load_pondage_flow_profiles",
    "load_reservoir_flow_profiles",
    "load_open_ps_flow_profiles",
    "load_closed_ps_flow_profiles",
    "load_all_profiles",
    # transforms
    "haversine_km",
    "compute_lengths_and_losses",
    "build_network_data",
    "build_storage_data",
    "build_terminal_data",
    "normalise_profiles_to_hourly",
    # visualisation
    "plot_capacity_by_technology",
    "plot_storage_capacity_by_technology",
    "plot_capacity_by_zone",
    "plot_storage_capacity_by_zone",
    "plot_profiles",
    "plot_availability_report",
    "plot_electricity_network_map",
    "plot_gas_network_map",
    "plot_hydrogen_network_map",
    # export
    "build_availability_summary",
    "export_zone_data",
    "export_network_data",
    "export_all_zones",
    # utils
    "create_output_directories",
    "get_pemmdb_filepath",
    "build_zone_display_map",
    "expand_profile_to_hourly",
    "validate_scenario",
    "validate_option",
]
