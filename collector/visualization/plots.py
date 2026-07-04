"""Plotting and visualisation functions (Bokeh charts + Folium maps)."""

from __future__ import annotations

import os
import random

import folium
import numpy as np
import pandas as pd
import requests
from bokeh.io import output_file, save as bokeh_save
from bokeh.layouts import column as bokeh_column
from bokeh.models import ColumnDataSource, HoverTool
from bokeh.palettes import Category10, Category20
from bokeh.plotting import figure
from bokeh.transform import dodge
from branca.element import MacroElement, Template

from collector.utils.helpers import build_zone_display_map, expand_profile_to_hourly


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _zone_palette(n: int) -> list[str]:
    """Return a colour palette of length *n* from the Bokeh Category sets."""
    palette = Category10[10] if n <= 10 else Category20[20]
    return [palette[i % len(palette)] for i in range(n)]


def _apply_font(p, font_factor: float = 1.0) -> None:
    """Apply consistent font sizes to a Bokeh figure."""
    p.title.text_font_size        = f"{font_factor * 13}pt"
    p.xaxis.axis_label_text_font_size = f"{font_factor * 11}pt"
    p.yaxis.axis_label_text_font_size = f"{font_factor * 11}pt"
    p.xaxis.major_label_text_font_size = f"{font_factor * 10}pt"
    p.yaxis.major_label_text_font_size = f"{font_factor * 10}pt"
    p.legend.label_text_font_size  = f"{font_factor * 10}pt"


def _bar_offsets(n: int, total_width: float = 0.85) -> tuple[float, list[float]]:
    """Compute bar width and dodge offsets for a grouped bar chart."""
    bar_w = max(0.05, total_width / max(1, n))
    if n == 1:
        return bar_w, [0.0]
    offsets = list(np.linspace(-total_width / 2 + bar_w / 2,
                                total_width / 2 - bar_w / 2, n))
    return bar_w, offsets


# ---------------------------------------------------------------------------
# Capacity bar charts
# ---------------------------------------------------------------------------


def plot_capacity_by_technology(
    tech_cap_df: pd.DataFrame,
    selected_zones: list[str],
    zone_to_display: dict[str, str],
    output_path: str,
) -> None:
    """Save a grouped bar chart of installed capacity by technology for each zone.

    One bar group per technology; one bar per zone.  Only MW columns (not MWh
    or MW/h time-series) are included.

    Args:
        tech_cap_df (pd.DataFrame): Technology capacity DataFrame as returned
            by :func:`~collector.data.loader.load_tech_capacities`.
        selected_zones (list[str]): Zone codes to plot.
        zone_to_display (dict[str, str]): Mapping from zone code to display
            label (built by :func:`~collector.utils.helpers.build_zone_display_map`).
        output_path (str): Destination path for the HTML output file.

    Returns:
        None

    Example:
        >>> plot_capacity_by_technology(cap_df, ["ES00"], {"ES00": "Spain (ES00)"},
        ...                             "Outputs/HTMLs/cap_by_tech.html")
    """
    exclude = [c for c in tech_cap_df.columns if c.endswith("(MWh)") or c.endswith("(MW/h)")]
    techs = [c for c in tech_cap_df.columns if c != "Code" and c not in exclude]
    dfz = tech_cap_df[tech_cap_df["Code"].isin(selected_zones)].copy()
    for c in techs:
        dfz[c] = pd.to_numeric(dfz[c], errors="coerce").fillna(0.0)

    n = len(selected_zones)
    bar_w, offsets = _bar_offsets(n)
    colors = _zone_palette(n)

    source_dict: dict = {"tech": techs}
    for z in selected_zones:
        row = dfz[dfz["Code"] == z]
        source_dict[z] = [float(row.iloc[0][t]) if not row.empty else 0.0 for t in techs]
    source = ColumnDataSource(source_dict)

    p = figure(
        x_range=techs,
        title="Installed Capacities by Technology",
        x_axis_label="Technology",
        y_axis_label="Capacity (MW)",
        width=1300, height=500,
        tools="pan,wheel_zoom,box_zoom,reset,save",
    )
    for i, z in enumerate(selected_zones):
        r = p.vbar(
            x=dodge("tech", float(offsets[i]), range=p.x_range),
            top=z, width=bar_w, source=source,
            color=colors[i], legend_label=zone_to_display.get(z, z), alpha=0.7,
        )
        p.add_tools(HoverTool(renderers=[r], tooltips=[
            ("Zone", zone_to_display.get(z, z)),
            ("Technology", "@tech"),
            ("Capacity", f"@{z}{{0,0.00}}"),
        ]))
    p.xaxis.major_label_orientation = 1.5708
    _apply_font(p)
    output_file(output_path)
    bokeh_save(p)


def plot_storage_capacity_by_technology(
    tech_cap_df: pd.DataFrame,
    selected_zones: list[str],
    zone_to_display: dict[str, str],
    output_path: str,
) -> None:
    """Save a grouped bar chart of MWh storage capacity by technology for each zone.

    Only MWh columns (not MW or MW/h time-series) are included.

    Args:
        tech_cap_df (pd.DataFrame): Technology capacity DataFrame.
        selected_zones (list[str]): Zone codes to plot.
        zone_to_display (dict[str, str]): Zone display label mapping.
        output_path (str): Destination HTML path.

    Returns:
        None

    Example:
        >>> plot_storage_capacity_by_technology(cap_df, ["ES00"], labels,
        ...                                     "Outputs/HTMLs/storage_by_tech.html")
    """
    ex_techs = [c for c in tech_cap_df.columns if c.endswith("(MWh)")]
    if not ex_techs:
        return

    dfz = tech_cap_df[tech_cap_df["Code"].isin(selected_zones)].copy()
    for c in ex_techs:
        dfz[c] = pd.to_numeric(dfz[c], errors="coerce").fillna(0.0)

    n = len(selected_zones)
    bar_w, offsets = _bar_offsets(n)
    colors = _zone_palette(n)

    source_dict: dict = {"tech": ex_techs}
    for z in selected_zones:
        row = dfz[dfz["Code"] == z]
        source_dict[z] = [float(row.iloc[0][t]) if not row.empty else 0.0 for t in ex_techs]
    source = ColumnDataSource(source_dict)

    p = figure(
        x_range=ex_techs,
        title="Storage Capacities by Technology",
        x_axis_label="Technology (MWh)",
        y_axis_label="Capacity (MWh)",
        width=1300, height=500,
        tools="pan,wheel_zoom,box_zoom,reset,save",
    )
    for i, z in enumerate(selected_zones):
        r = p.vbar(
            x=dodge("tech", float(offsets[i]), range=p.x_range),
            top=z, width=bar_w, source=source,
            color=colors[i], legend_label=zone_to_display.get(z, z), alpha=0.7,
        )
        p.add_tools(HoverTool(renderers=[r], tooltips=[
            ("Zone", zone_to_display.get(z, z)),
            ("Technology", "@tech"),
            ("Capacity", f"@{z}{{0,0.00}}"),
        ]))
    p.xaxis.major_label_orientation = 1.5708
    _apply_font(p)
    output_file(output_path)
    bokeh_save(p)


def plot_capacity_by_zone(
    tech_cap_df: pd.DataFrame,
    selected_zones: list[str],
    zone_to_display: dict[str, str],
    output_path: str,
) -> None:
    """Save a grouped bar chart of installed capacity by zone for each technology.

    One bar group per zone; one bar per technology.

    Args:
        tech_cap_df (pd.DataFrame): Technology capacity DataFrame.
        selected_zones (list[str]): Zone codes to plot.
        zone_to_display (dict[str, str]): Zone display label mapping.
        output_path (str): Destination HTML path.

    Returns:
        None

    Example:
        >>> plot_capacity_by_zone(cap_df, ["ES00", "PT00"], labels,
        ...                       "Outputs/HTMLs/cap_by_zone.html")
    """
    exclude = [c for c in tech_cap_df.columns if c.endswith("(MWh)") or c.endswith("(MW/h)")]
    techs = [c for c in tech_cap_df.columns if c != "Code" and c not in exclude]
    dfz = tech_cap_df[tech_cap_df["Code"].isin(selected_zones)].copy()
    for c in techs:
        dfz[c] = pd.to_numeric(dfz[c], errors="coerce").fillna(0.0)

    zone_labels = [zone_to_display.get(z, z) for z in selected_zones]
    m = len(techs)
    bar_w, offsets = _bar_offsets(m)
    colors = _zone_palette(m)

    tech_to_values: dict = {}
    for tech in techs:
        vals = []
        for z in selected_zones:
            row = dfz[dfz["Code"] == z]
            vals.append(float(row.iloc[0][tech]) if not row.empty else 0.0)
        tech_to_values[tech] = vals
    source = ColumnDataSource({"zone": zone_labels, **tech_to_values})

    p = figure(
        x_range=zone_labels,
        title="Installed Capacities by Zone",
        x_axis_label="Zone",
        y_axis_label="Capacity (MW)",
        width=1300, height=500,
        tools="pan,wheel_zoom,box_zoom,reset,save",
    )
    for i, tech in enumerate(techs):
        r = p.vbar(
            x=dodge("zone", float(offsets[i]), range=p.x_range),
            top=tech, width=bar_w, source=source,
            color=colors[i], legend_label=tech, alpha=0.9,
        )
        p.add_tools(HoverTool(renderers=[r], tooltips=[
            ("Zone", "@zone"),
            ("Technology", tech),
            ("Capacity", f"@{{{tech}}}{{0,0.00}}"),
        ]))
    p.xaxis.major_label_orientation = 0
    p.legend.location = "top_right"
    p.legend.click_policy = "hide"
    p.legend.orientation = "vertical"
    p.legend.title = "Technologies"
    p.legend.ncols = 3
    _apply_font(p)
    output_file(output_path)
    bokeh_save(p)


def plot_storage_capacity_by_zone(
    tech_cap_df: pd.DataFrame,
    selected_zones: list[str],
    zone_to_display: dict[str, str],
    output_path: str,
) -> None:
    """Save a grouped bar chart of MWh storage capacity by zone for each technology.

    Args:
        tech_cap_df (pd.DataFrame): Technology capacity DataFrame.
        selected_zones (list[str]): Zone codes to plot.
        zone_to_display (dict[str, str]): Zone display label mapping.
        output_path (str): Destination HTML path.

    Returns:
        None

    Example:
        >>> plot_storage_capacity_by_zone(cap_df, ["ES00"], labels,
        ...                               "Outputs/HTMLs/storage_by_zone.html")
    """
    ex_techs = [c for c in tech_cap_df.columns if c.endswith("(MWh)")]
    if not ex_techs:
        return

    dfz = tech_cap_df[tech_cap_df["Code"].isin(selected_zones)].copy()
    for c in ex_techs:
        dfz[c] = pd.to_numeric(dfz[c], errors="coerce").fillna(0.0)

    zone_labels = [zone_to_display.get(z, z) for z in selected_zones]
    m = len(ex_techs)
    bar_w, offsets = _bar_offsets(m)
    colors = _zone_palette(m)

    tech_to_values: dict = {}
    for tech in ex_techs:
        vals = []
        for z in selected_zones:
            row = dfz[dfz["Code"] == z]
            vals.append(float(row.iloc[0][tech]) if not row.empty and tech in row.columns else 0.0)
        tech_to_values[tech] = vals
    source = ColumnDataSource({"zone": zone_labels, **tech_to_values})

    p = figure(
        x_range=zone_labels,
        title="Storage Capacities by Zone",
        x_axis_label="Zone",
        y_axis_label="Capacity (MWh)",
        width=1300, height=500,
        tools="pan,wheel_zoom,box_zoom,reset,save",
    )
    for i, tech in enumerate(ex_techs):
        r = p.vbar(
            x=dodge("zone", float(offsets[i]), range=p.x_range),
            top=tech, width=bar_w, source=source,
            color=colors[i], legend_label=tech, alpha=0.9,
        )
        p.add_tools(HoverTool(renderers=[r], tooltips=[
            ("Zone", "@zone"),
            ("Technology", tech),
            ("Capacity", f"@{{{tech}}}{{0,0.00}}"),
        ]))
    p.xaxis.major_label_orientation = 0
    p.legend.location = "top_right"
    p.legend.click_policy = "hide"
    p.legend.ncols = 1
    _apply_font(p)
    output_file(output_path)
    bokeh_save(p)


# ---------------------------------------------------------------------------
# Profile time-series plots
# ---------------------------------------------------------------------------


def plot_profiles(
    profiles_df: dict[str, list[dict]],
    selected_zones: list[str],
    node_df: pd.DataFrame,
    selected_hours: int,
    output_dir: str,
) -> None:
    """Save one HTML time-series plot per profile type.

    For each profile type in *profiles_df* a stacked column of line plots is
    generated – one line per zone – and saved as
    ``<output_dir>/<profile_type>.html``.

    Args:
        profiles_df (dict[str, list[dict]]): Profiles as returned by
            :func:`~collector.data.loader.load_all_profiles`.
        selected_zones (list[str]): Zone codes to include.
        node_df (pd.DataFrame): Nodes table used to resolve display names.
        selected_hours (int): Canonical hourly series length; daily/weekly
            arrays are expanded automatically.
        output_dir (str): Folder where HTML files are written.

    Returns:
        None

    Example:
        >>> plot_profiles(profiles, ["ES00"], nodes, 8736, "Outputs/HTMLs")
    """
    profile_types = list(profiles_df.keys())
    palette = Category10[10] if len(profile_types) <= 10 else Category20[20]
    color_map = {pt: palette[i % len(palette)] for i, pt in enumerate(profile_types)}

    code_to_location: dict[str, str] = {}
    if isinstance(node_df, pd.DataFrame) and {"Code", "Location"}.issubset(node_df.columns):
        code_to_location = dict(zip(node_df["Code"], node_df["Location"]))

    for profile_type, profile_list in profiles_df.items():
        plots = []
        for entry in profile_list:
            code = entry.get("Code")
            if code not in selected_zones:
                continue
            year = entry.get("Year", 0)
            data = np.asarray(entry.get("Data", []), dtype=float)
            if len(data) != selected_hours:
                data = expand_profile_to_hourly(data, selected_hours)
            if not isinstance(data, np.ndarray) or data.size == 0:
                continue

            display_name = code_to_location.get(code, code)
            x = list(range(1, len(data) + 1))
            title = profile_type.replace("Energy", "Profile")

            p = figure(
                title=f"{title} – {display_name} ({code}) – Year {year}",
                x_axis_label="Time (h)",
                y_axis_label="Value",
                width=1300, height=300,
                tools="pan,wheel_zoom,box_zoom,reset,save",
            )
            p.add_tools(HoverTool(
                tooltips=[("Time", "@x"), ("Value", "@y{0.00}")],
                mode="vline",
            ))
            p.line(x, data, line_width=1, legend_label=display_name,
                   color=color_map.get(profile_type, "black"))
            p.legend.location = "top_left"
            _apply_font(p)
            plots.append(p)

        html_path = os.path.join(output_dir, f"{profile_type}.html")
        output_file(html_path)
        if plots:
            bokeh_save(plots)
        else:
            print(f"No data to plot for profile type '{profile_type}'")


# ---------------------------------------------------------------------------
# Availability report
# ---------------------------------------------------------------------------


def plot_availability_report(
    profiles_df: dict[str, list[dict]],
    node_df: pd.DataFrame,
    scenario: int,
    climate_year: int,
    output_path: str,
) -> None:
    """Write a colour-coded HTML availability matrix for all profile types.

    Cells are styled green (``'Available'``) when the data array contains at
    least one non-zero, non-NaN value, and red (``'No Data'``) otherwise.

    Args:
        profiles_df (dict[str, list[dict]]): Combined profiles dict.
        node_df (pd.DataFrame): Nodes table for display name resolution.
        scenario (int): Scenario year (used in the report title).
        climate_year (int): Climate year (used in the report title).
        output_path (str): Full path for the output HTML file.

    Returns:
        None

    Example:
        >>> plot_availability_report(profiles, nodes, 2030, 2009,
        ...                          "Outputs/HTMLs/Report Table.html")
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

    avail_df = pd.DataFrame(records).set_index("Code").transpose()

    def _colour(val: str) -> str:
        if val == "Available":
            return "background-color: #b6e8be; color: #145a22; font-weight: bold; text-align: center;"
        if val == "No Data":
            return "background-color: #f6baba; color: #7d1111; font-weight: bold; text-align: center;"
        return "text-align: center;"

    styled = (
        avail_df.style
        .map(_colour)
        .set_properties(**{"font-size": "12pt", "white-space": "pre-line", "text-align": "center"})
        .set_table_styles([{
            "selector": "th",
            "props": [
                ("background-color", "#dde4f0"),
                ("font-weight", "bold"),
                ("color", "#2b394c"),
                ("font-size", "13pt"),
                ("white-space", "pre-line"),
                ("text-align", "center"),
            ],
        }])
    )

    header = (
        f'<h3 style="text-align:center;">Profile Availability<br>'
        f'<span style="font-size:12pt; font-weight:normal">'
        f"Scenario: {scenario}, Climate Year: {climate_year}</span></h3>"
    )
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(styled.to_html())


# ---------------------------------------------------------------------------
# Folium network maps (from Map.ipynb)
# ---------------------------------------------------------------------------


def _get_random_hex_color() -> str:
    """Return a random CSS hex colour string."""
    return "#{:06x}".format(random.randint(0, 0xFFFFFF))


def _build_folium_locations(node_df: pd.DataFrame) -> dict[str, list[float]]:
    """Build a ``{"Country (Code)": [lat, lon]}`` mapping from the nodes table."""
    node_df = node_df.copy()
    if "Location" in node_df.columns:
        node_df["Location"] = node_df["Location"].str.replace("\xa0", " ", regex=False)
    return {
        f"{row['Country']} ({row['Code']})": [row["Latitude"], row["Longitude"]]
        for _, row in node_df.iterrows()
        if {"Country", "Code", "Latitude", "Longitude"}.issubset(node_df.columns)
    }


def _add_map_title(m: folium.Map, title_text: str) -> None:
    """Embed a fixed-position title div into a Folium map."""
    title_html = (
        "{% macro html(this, kwargs) %}"
        f'<div style="position: fixed; top: 10px; left: 50px; font-size: 22px; '
        f'font-weight: bold; color: black; z-index:9999;">{title_text}</div>'
        "{% endmacro %}"
    )
    element = MacroElement()
    element._template = Template(title_html)
    m.get_root().add_child(element)


def plot_electricity_network_map(
    node_df: pd.DataFrame,
    edges_e_df: pd.DataFrame,
    selected_zones: list[str],
    scenario: int,
    geojson_url: str = "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json",
) -> folium.Map:
    """Build a Folium map of the electricity network for the selected zones.

    Nodes in the study zone are coloured red; neighbouring nodes black.
    Lines are drawn in red.  A GeoJSON country layer provides geographic
    context.

    Args:
        node_df (pd.DataFrame): Nodes table with ``Country``, ``Code``,
            ``Latitude``, and ``Longitude`` columns.
        edges_e_df (pd.DataFrame): Electricity edge table for the given
            scenario (already loaded via
            :func:`~collector.data.loader.load_network_edges`).
        selected_zones (list[str]): Zone codes that define the study area.
        scenario (int): Scenario year (used in the map title).
        geojson_url (str): URL to a world GeoJSON file for country outlines.

    Returns:
        folium.Map: Interactive Folium map object.

    Example:
        >>> m = plot_electricity_network_map(nodes, edges_e, ["ES00", "PT00"], 2030)
        >>> m.save("electricity_network.html")
    """
    return _build_network_map(
        node_df=node_df,
        edges_df=edges_e_df,
        selected_zones=selected_zones,
        network_label="Electricity Network",
        line_color="red",
        geojson_url=geojson_url,
    )


def plot_gas_network_map(
    node_df: pd.DataFrame,
    edges_g_df: pd.DataFrame,
    selected_zones: list[str],
    scenario: int,
    geojson_url: str = "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json",
) -> folium.Map:
    """Build a Folium map of the gas pipeline network for the selected zones.

    Lines are drawn in blue.

    Args:
        node_df (pd.DataFrame): Nodes table.
        edges_g_df (pd.DataFrame): Gas pipeline edge table.
        selected_zones (list[str]): Study-area zone codes.
        scenario (int): Scenario year (used in title).
        geojson_url (str): URL to a world GeoJSON file.

    Returns:
        folium.Map: Interactive Folium map object.

    Example:
        >>> m = plot_gas_network_map(nodes, edges_g, ["ES00"], 2030)
    """
    return _build_network_map(
        node_df=node_df,
        edges_df=edges_g_df,
        selected_zones=selected_zones,
        network_label="Gas Network",
        line_color="blue",
        geojson_url=geojson_url,
    )


def plot_hydrogen_network_map(
    node_df: pd.DataFrame,
    edges_h_df: pd.DataFrame,
    selected_zones: list[str],
    scenario: int,
    geojson_url: str = "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json",
) -> folium.Map:
    """Build a Folium map of the hydrogen pipeline network for the selected zones.

    Lines are drawn in green.

    Args:
        node_df (pd.DataFrame): Nodes table.
        edges_h_df (pd.DataFrame): Hydrogen pipeline edge table.
        selected_zones (list[str]): Study-area zone codes.
        scenario (int): Scenario year (used in title).
        geojson_url (str): URL to a world GeoJSON file.

    Returns:
        folium.Map: Interactive Folium map object.

    Example:
        >>> m = plot_hydrogen_network_map(nodes, edges_h, ["ES00"], 2030)
    """
    return _build_network_map(
        node_df=node_df,
        edges_df=edges_h_df,
        selected_zones=selected_zones,
        network_label="Hydrogen Network",
        line_color="green",
        geojson_url=geojson_url,
    )


def _build_network_map(
    node_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    selected_zones: list[str],
    network_label: str,
    line_color: str,
    geojson_url: str,
) -> folium.Map:
    """Internal builder shared by all three network map functions."""
    geojson_data = requests.get(geojson_url, timeout=30).json()
    locations = _build_folium_locations(node_df)

    if "Location" in node_df.columns:
        node_df = node_df.copy()
        node_df["Location"] = node_df["Location"].str.replace("\xa0", " ", regex=False)
        countries_with_nodes = node_df["Location"].apply(
            lambda x: x.split(" - ")[0]
        ).unique().tolist()
    else:
        countries_with_nodes = []

    country_colors = {c: _get_random_hex_color() for c in countries_with_nodes}

    def style_function(feature: dict) -> dict:
        country = feature["properties"]["name"]
        if country in country_colors:
            return {"fillColor": country_colors[country], "fillOpacity": 0.3,
                    "color": None, "weight": 0}
        return {"fillOpacity": 0}

    m = folium.Map(location=[45, -5], zoom_start=5, tiles="CartoDB positron")
    folium.GeoJson(geojson_data, style_function=style_function).add_to(m)

    filtered = edges_df.iloc[1:][
        edges_df.iloc[1:]["Start_Node"].apply(lambda x: any(z in str(x) for z in selected_zones)) |
        edges_df.iloc[1:]["End_Node"].apply(lambda x: any(z in str(x) for z in selected_zones))
    ]

    for _, row in filtered.iterrows():
        start_key = next((k for k in locations if k.endswith(f"({row['Start_Node']})")), None)
        end_key   = next((k for k in locations if k.endswith(f"({row['End_Node']})")), None)
        if start_key and end_key:
            folium.PolyLine(
                locations=[locations[start_key], locations[end_key]],
                color=line_color, weight=2, opacity=0.6,
            ).add_to(m)

    nodes_in_edges = set(filtered["Start_Node"]).union(set(filtered["End_Node"]))
    for node_key, coord in locations.items():
        code = node_key.split("(")[-1].replace(")", "")
        if code not in nodes_in_edges:
            continue
        color = line_color if code in selected_zones else "black"
        folium.CircleMarker(
            location=coord, radius=10,
            color=color, fill=True, fill_color=color, fill_opacity=0.8,
        ).add_to(m)
        folium.Marker(
            location=coord,
            icon=folium.DivIcon(html=(
                f'<div style="font-size: 9pt; font-weight: bold; color: white; '
                f'text-shadow: 1px 1px 2px black;">{code}</div>'
            )),
        ).add_to(m)

    _add_map_title(m, f"{network_label}<br>Zones: {len(nodes_in_edges)}<br>Lines: {len(filtered)}")
    return m
