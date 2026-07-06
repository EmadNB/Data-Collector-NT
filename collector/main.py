"""Orchestrates the full ENTSO-E data collection and export pipeline.

Run directly::

    python -m collector.main

or import and call :func:`run` from another script::

    from collector.main import run
    run(
        selected_scenario=2030,
        selected_climate_year=2009,
        selected_zones=["ES00", "PT00", "FR00"],
        selected_hours=8736,
        selected_gas_pipe="Existing",
        selected_hydrogen_pipe="PCI/PMI",
        selected_gas_storage="Low",
        selected_hydrogen_storage="PCI/PMI",
        selected_gas_terminal="Low",
        selected_hydrogen_terminal="PCI/PMI",
        selected_output="Normal",
    )
"""

from __future__ import annotations

import os

from collector.data.loader import (
    load_all_profiles,
    load_commodity_prices,
    load_lignite_groups,
    load_crossborder_exchanges,
    load_network_edges,
    load_network_storages,
    load_network_terminals,
    load_nodes,
    load_reserve_requirements,
    load_tech_capacities,
    load_tech_characteristics,
)
from collector.models.core import export_all_zones
from collector.models.opentepes import export_opentepes
from collector.processing.transforms import (
    build_network_data,
    build_storage_data,
    build_terminal_data,
    filter_electricity_edges,
    normalise_profiles_to_hourly,
)
from collector.utils.config import (
    GAS_PIPE_OPTIONS,
    GAS_STORAGE_OPTIONS,
    GAS_TERMINAL_OPTIONS,
    HYDROGEN_PIPE_OPTIONS,
    HYDROGEN_STORAGE_OPTIONS,
    HYDROGEN_TERMINAL_OPTIONS,
    OUTPUT_MODES,
    VALID_SCENARIOS,
)
from collector.utils.helpers import (
    build_zone_display_map,
    clear_output_files,
    create_output_directories,
    validate_option,
    validate_scenario,
)
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


def run(
    selected_scenario: int = 2030,
    selected_climate_year: int = 2009,
    selected_zones: list[str] | None = None,
    selected_hours: int = 8736,
    selected_gas_pipe: str = "Existing",
    selected_hydrogen_pipe: str = "PCI/PMI",
    selected_gas_storage: str = "Low",
    selected_hydrogen_storage: str = "PCI/PMI",
    selected_gas_terminal: str = "Low",
    selected_hydrogen_terminal: str = "PCI/PMI",
    selected_output: str = "Normal",
    selected_generate_html: bool = False,
    base_path: str = ".",
) -> None:
    """Execute the full data collection, processing, visualisation, and export pipeline.

    Mirrors the execution order of the original ``Data Analyzer.ipynb`` notebook,
    re-implemented as clean, testable function calls.

    Args:
        selected_scenario (int): Scenario year.  One of ``2030``, ``2040``,
            ``2050``.  Defaults to ``2030``.
        selected_climate_year (int): Climate year for which profile data is
            extracted (e.g. ``2009``).  Defaults to ``2009``.
        selected_zones (list[str] | None): Zone codes to collect data for
            (e.g. ``["ES00", "PT00", "FR00"]``).  Required — a ``ValueError`` is
            raised (nothing is generated) when empty or ``None``.
        selected_hours (int): Number of hourly time steps per year to read.
            Defaults to ``8736``.
        selected_gas_pipe (str): Gas pipeline capacity scenario.  One of
            :data:`~collector.utils.config.GAS_PIPE_OPTIONS`.
        selected_hydrogen_pipe (str): Hydrogen pipeline capacity scenario.
            One of :data:`~collector.utils.config.HYDROGEN_PIPE_OPTIONS`.
        selected_gas_storage (str): Gas storage capacity scenario.  One of
            :data:`~collector.utils.config.GAS_STORAGE_OPTIONS`.
        selected_hydrogen_storage (str): Hydrogen storage capacity scenario.
            One of :data:`~collector.utils.config.HYDROGEN_STORAGE_OPTIONS`.
        selected_gas_terminal (str): Gas terminal capacity scenario.  One of
            :data:`~collector.utils.config.GAS_TERMINAL_OPTIONS`.
        selected_hydrogen_terminal (str): Hydrogen terminal capacity scenario.
            One of :data:`~collector.utils.config.HYDROGEN_TERMINAL_OPTIONS`.
        selected_output (str): Output format – ``'Normal'`` or
            ``'openTEPES'``.  Defaults to ``'Normal'``.
        selected_generate_html (bool): Whether to render the HTML chart / map
            visualisations.  Defaults to ``False`` (no HTML output).
        base_path (str): Working directory containing the ``Data/`` folder
            and where ``Outputs/`` will be created.  Defaults to ``'.'``.

    Returns:
        None

    Raises:
        ValueError: When any selector argument is invalid.

    Example:
        >>> from collector.main import run
        >>> run(selected_scenario=2030, selected_zones=["ES00", "PT00"])
    """
    if not selected_zones:
        raise ValueError("No zones selected — nothing to generate.")

    # Validate inputs
    validate_scenario(selected_scenario)
    validate_option(selected_gas_pipe,          GAS_PIPE_OPTIONS,         "selected_gas_pipe")
    validate_option(selected_hydrogen_pipe,     HYDROGEN_PIPE_OPTIONS,    "selected_hydrogen_pipe")
    validate_option(selected_gas_storage,       GAS_STORAGE_OPTIONS,      "selected_gas_storage")
    validate_option(selected_hydrogen_storage,  HYDROGEN_STORAGE_OPTIONS, "selected_hydrogen_storage")
    validate_option(selected_gas_terminal,      GAS_TERMINAL_OPTIONS,     "selected_gas_terminal")
    validate_option(selected_hydrogen_terminal, HYDROGEN_TERMINAL_OPTIONS,"selected_hydrogen_terminal")
    validate_option(selected_output,            OUTPUT_MODES,             "selected_output")

    _orig_cwd = os.getcwd()
    if base_path != ".":
        os.chdir(base_path)

    try:
        _pipeline(
            scenario=selected_scenario,
            climate_year=selected_climate_year,
            zones=selected_zones,
            hours=selected_hours,
            gas_pipe=selected_gas_pipe,
            hydrogen_pipe=selected_hydrogen_pipe,
            gas_storage=selected_gas_storage,
            hydrogen_storage=selected_hydrogen_storage,
            gas_terminal=selected_gas_terminal,
            hydrogen_terminal=selected_hydrogen_terminal,
            output_mode=selected_output,
            generate_html=selected_generate_html,
        )
    finally:
        if base_path != ".":
            os.chdir(_orig_cwd)


def _pipeline(
    scenario: int,
    climate_year: int,
    zones: list[str],
    hours: int,
    gas_pipe: str,
    hydrogen_pipe: str,
    gas_storage: str,
    hydrogen_storage: str,
    gas_terminal: str,
    hydrogen_terminal: str,
    output_mode: str,
    generate_html: bool = False,
) -> None:
    """Internal pipeline implementation (all paths relative to cwd)."""

    # ── Step 1: directories ──────────────────────────────────────────────────
    create_output_directories(".")
    clear_output_files(".", output_mode)
    html_dir   = os.path.join("outputs", "HTMLs")
    excel_dir  = os.path.join("outputs", "Excel Files", output_mode)

    # ── Step 2: node / network loading ──────────────────────────────────────
    print("\n=== Loading nodes and network edges ===")
    node_df = load_nodes()
    edges_e, edges_g, edges_h = load_network_edges(scenario)
    storages_g, storages_h  = load_network_storages(scenario)
    terminals_g, terminals_h = load_network_terminals(scenario)

    # ── Step 3: technology data ──────────────────────────────────────────────
    print("\n=== Loading technology capacities ===")
    tech_cap_df  = load_tech_capacities(node_df, zones, scenario, hours)
    print("\n=== Loading technology characteristics ===")
    tech_char_df = load_tech_characteristics(node_df, zones, scenario)
    print("\n=== Loading reserve requirements ===")
    reserve_df   = load_reserve_requirements(node_df, zones, scenario)

    # ── Step 4: network transforms ───────────────────────────────────────────
    print("\n=== Processing network data ===")
    network_df = build_network_data(
        node_df, edges_e, edges_g, edges_h, zones,
        gas_pipe, hydrogen_pipe,
    )
    storage_df  = build_storage_data(storages_g, storages_h, zones, gas_storage, hydrogen_storage)
    terminal_df = build_terminal_data(terminals_g, terminals_h, zones, gas_terminal, hydrogen_terminal)

    # ── Step 5: cross-border exchanges ───────────────────────────────────────
    print("\n=== Loading cross-border exchanges ===")
    filtered_e = filter_electricity_edges(edges_e, zones)
    try:
        export_df = load_crossborder_exchanges(scenario, hours, filtered_e, zones)
    except FileNotFoundError as exc:
        print(f"Warning: cross-border exchange file not found – {exc}")
        import pandas as pd
        export_df = pd.DataFrame()

    # ── Step 6: profiles ─────────────────────────────────────────────────────
    print("\n=== Loading generation and demand profiles ===")
    profiles_df = load_all_profiles(node_df, zones, scenario, climate_year, hours)
    profiles_df = normalise_profiles_to_hourly(profiles_df, hours)

    # Load TYNDP 2024 commodity prices and Lignite country groups
    commodity_prices = load_commodity_prices(scenario)
    lignite_groups   = load_lignite_groups()

    # ── Steps 7–10: HTML visualisations (optional) ──────────────────────────
    if generate_html:
        # Step 7: capacity visualisations
        print("\n=== Plotting capacity charts ===")
        zone_to_display = build_zone_display_map(node_df, zones)
        plot_capacity_by_technology(
            tech_cap_df, zones, zone_to_display,
            os.path.join(html_dir, "Technology Capacities (ver.1).html"),
        )
        plot_storage_capacity_by_technology(
            tech_cap_df, zones, zone_to_display,
            os.path.join(html_dir, "Storage Capacities (ver.1).html"),
        )
        plot_capacity_by_zone(
            tech_cap_df, zones, zone_to_display,
            os.path.join(html_dir, "Technology Capacities (ver.2).html"),
        )
        plot_storage_capacity_by_zone(
            tech_cap_df, zones, zone_to_display,
            os.path.join(html_dir, "Storage Capacities (ver.2).html"),
        )

        # Step 8: profile visualisations
        print("\n=== Plotting profile time series ===")
        plot_profiles(profiles_df, zones, node_df, hours, html_dir)

        # Step 9: availability report
        print("\n=== Writing availability report ===")
        plot_availability_report(
            profiles_df, node_df, scenario, climate_year,
            os.path.join(html_dir, "Report Table.html"),
        )

        # Step 10: network maps
        print("\n=== Rendering network maps ===")
        m_el  = plot_electricity_network_map(node_df, edges_e, zones, scenario)
        m_gas = plot_gas_network_map(node_df, edges_g, zones, scenario)
        m_h2  = plot_hydrogen_network_map(node_df, edges_h, zones, scenario)
        m_el.save(os.path.join(html_dir, "Electricity Network Map.html"))
        m_gas.save(os.path.join(html_dir, "Gas Network Map.html"))
        m_h2.save(os.path.join(html_dir, "Hydrogen Network Map.html"))
    else:
        print("\n=== Skipping HTML visualisations (disabled) ===")

    # ── Step 11: Export ──────────────────────────────────────────────────────
    if output_mode == "openTEPES":
        print("\n=== Exporting openTEPES CSV files ===")
        export_opentepes(
            tech_cap_df=tech_cap_df,
            tech_char_df=tech_char_df,
            profiles_df=profiles_df,
            export_df=export_df,
            storage_df=storage_df,
            network_df=network_df,
            node_df=node_df,
            selected_zones=zones,
            selected_hours=hours,
            scenario=scenario,
            output_folder=excel_dir,
            climate_year=climate_year,
            commodity_prices=commodity_prices,
            lignite_groups=lignite_groups,
            reserve_df=reserve_df,
        )
    else:
        print("\n=== Exporting Excel workbooks ===")
        export_all_zones(
            tech_cap_df=tech_cap_df,
            tech_char_df=tech_char_df,
            reserve_req_df=reserve_df,
            profiles_df=profiles_df,
            export_df=export_df,
            storage_df=storage_df,
            terminal_df=terminal_df,
            network_df=network_df,
            selected_hours=hours,
            selected_zones=zones,
            output_folder=excel_dir,
            commodity_prices=commodity_prices,
            lignite_groups=lignite_groups,
        )

    print("\n=== Pipeline complete ===")


if __name__ == "__main__":
    run()
