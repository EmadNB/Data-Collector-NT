from __future__ import annotations

import os
import random

import folium
import numpy as np
import pandas as pd
import requests
from bokeh.io import output_file, save as bokeh_save
from bokeh.layouts import column as bokeh_column
from bokeh.models import ColumnDataSource, HoverTool, Legend, LegendItem
from bokeh.palettes import Category10, Category20
from bokeh.plotting import figure
from branca.element import MacroElement, Template

from collector.utils.helpers import build_zone_display_map, expand_profile_to_hourly


# Internal helpers


def _zone_palette(n: int) -> list[str]:
    palette = Category10[10] if n <= 10 else Category20[20]
    return [palette[i % len(palette)] for i in range(n)]


def _apply_font(p, font_factor: float = 1.0) -> None:
    p.title.text_font_size        = f"{font_factor * 13}pt"
    p.xaxis.axis_label_text_font_size = f"{font_factor * 11}pt"
    p.yaxis.axis_label_text_font_size = f"{font_factor * 11}pt"
    p.xaxis.major_label_text_font_size = f"{font_factor * 10}pt"
    p.yaxis.major_label_text_font_size = f"{font_factor * 10}pt"
    if p.legend:
        p.legend.label_text_font_size = f"{font_factor * 10}pt"


# Capacity bar charts


def _zone_titles(
    selected_zones: list[str],
    zone_to_display: dict[str, str],
) -> dict[str, str]:
    """Zone's display label with the zone code always appended in parentheses."""
    def _label(z: str) -> str:
        text = zone_to_display.get(z, z)
        suffix = f" ({z})"
        return text[: -len(suffix)] if text.endswith(suffix) else text

    return {z: f"{_label(z)} ({z})" for z in selected_zones}


def _capacity_by_zone_chart(
    techs: list[str],
    dfz: pd.DataFrame,
    selected_zones: list[str],
    zone_to_display: dict[str, str],
    y_axis_label: str,
    output_path: str,
    legend_ncols: int = 8,
) -> None:
    """One sub-plot per zone, stacked vertically. Bars sit side by side within a
    sub-plot, colored consistently by technology across every sub-plot so colors
    stay comparable across countries. A technology is dropped everywhere only if
    it is zero in all selected zones. One shared, clickable legend sits above the
    first sub-plot and toggles that technology's bars across every sub-plot at
    once (click_policy="hide")."""
    titles = _zone_titles(selected_zones, zone_to_display)

    values_by_zone: dict[str, dict[str, float]] = {}
    for z in selected_zones:
        row = dfz[dfz["Code"] == z]
        values_by_zone[z] = {
            t: (float(row.iloc[0][t]) if not row.empty and t in row.columns else 0.0)
            for t in techs
        }

    used_techs = [t for t in techs if any(values_by_zone[z][t] > 0 for z in selected_zones)]
    if not used_techs:
        return
    tech_colors = dict(zip(used_techs, _zone_palette(len(used_techs))))
    tech_renderers: dict[str, list] = {t: [] for t in used_techs}

    rows = []
    for z in selected_zones:
        values = values_by_zone[z]
        p = figure(
            x_range=used_techs,
            title=titles[z],
            y_axis_label=y_axis_label,
            width=1300, height=300,
            tools="pan,wheel_zoom,box_zoom,reset,save",
        )
        subplot_renderers = []
        for t in used_techs:
            source = ColumnDataSource({"tech": [t], "value": [values[t]]})
            r = p.vbar(
                x="tech", top="value", width=0.7, source=source,
                color=tech_colors[t], alpha=0.9,
            )
            tech_renderers[t].append(r)
            subplot_renderers.append(r)
        p.add_tools(HoverTool(renderers=subplot_renderers, tooltips=[
            ("Zone", titles[z]),
            ("Technology", "@tech"),
            ("Capacity", "@value{0,0.00}"),
        ]))
        p.xaxis.visible = False
        _apply_font(p, font_factor=0.85)
        rows.append(p)

    ncols = min(legend_ncols, len(used_techs))
    nrows = -(-len(used_techs) // ncols)  # ceil division
    legend_holder = figure(
        width=1300, height=40 + nrows * 30,
        toolbar_location=None, outline_line_color=None,
    )
    legend_holder.axis.visible = False
    legend_holder.grid.visible = False

    # A same-figure swatch renderer per technology: Bokeh resolves a legend
    # item's swatch color from its *first* renderer, and that only renders
    # reliably when the renderer belongs to the legend's own figure. The real
    # cross-subplot renderers are still included so click_policy="hide" keeps
    # toggling that technology's bars everywhere.
    legend_items = []
    for t in used_techs:
        swatch = legend_holder.scatter(x=[0], y=[0], marker="square", size=0, color=tech_colors[t])
        legend_items.append(LegendItem(label=t, renderers=[swatch, *tech_renderers[t]]))

    legend = Legend(
        items=legend_items,
        click_policy="hide", orientation="horizontal", location="center",
        label_text_font_size="8.5pt", ncols=ncols,
    )
    legend_holder.add_layout(legend, "center")
    rows.insert(0, legend_holder)

    output_file(output_path, title="Data-Collector-NT")
    bokeh_save(bokeh_column(*rows, sizing_mode="stretch_width"))


def plot_capacity_by_zone(
    tech_cap_df: pd.DataFrame,
    selected_zones: list[str],
    zone_to_display: dict[str, str],
    output_path: str,
) -> None:
    exclude = [c for c in tech_cap_df.columns if c.endswith("(MWh)") or c.endswith("(MW/h)")]
    techs = [c for c in tech_cap_df.columns if c != "Code" and c not in exclude]
    dfz = tech_cap_df[tech_cap_df["Code"].isin(selected_zones)].copy()
    for c in techs:
        dfz[c] = pd.to_numeric(dfz[c], errors="coerce").fillna(0.0)
    _capacity_by_zone_chart(techs, dfz, selected_zones, zone_to_display, "Capacity (MW)", output_path, legend_ncols=5)


def plot_storage_capacity_by_zone(
    tech_cap_df: pd.DataFrame,
    selected_zones: list[str],
    zone_to_display: dict[str, str],
    output_path: str,
) -> None:
    ex_techs = [c for c in tech_cap_df.columns if c.endswith("(MWh)")]
    if not ex_techs:
        return
    dfz = tech_cap_df[tech_cap_df["Code"].isin(selected_zones)].copy()
    for c in ex_techs:
        dfz[c] = pd.to_numeric(dfz[c], errors="coerce").fillna(0.0)
    _capacity_by_zone_chart(ex_techs, dfz, selected_zones, zone_to_display, "Capacity (MWh)", output_path)


# Profile time-series plots


def plot_profiles(
    profiles_df: dict[str, list[dict]],
    selected_zones: list[str],
    node_df: pd.DataFrame,
    selected_hours: int,
    output_dir: str,
) -> None:
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
        output_file(html_path, title="Data-Collector-NT")
        if plots:
            bokeh_save(plots)
        else:
            print(f"No data to plot for profile type '{profile_type}'")


# Availability report


def plot_availability_report(
    profiles_df: dict[str, list[dict]],
    node_df: pd.DataFrame,
    scenario: int,
    climate_year: int,
    output_path: str,
) -> None:
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


# Folium network maps


def _get_random_hex_color() -> str:
    return "#{:06x}".format(random.randint(0, 0xFFFFFF))


def _build_folium_locations(node_df: pd.DataFrame) -> dict[str, list[float]]:
    node_df = node_df.copy()
    if "Location" in node_df.columns:
        node_df["Location"] = node_df["Location"].str.replace("\xa0", " ", regex=False)
    return {
        f"{row['Country']} ({row['Code']})": [row["Latitude"], row["Longitude"]]
        for _, row in node_df.iterrows()
        if {"Country", "Code", "Latitude", "Longitude"}.issubset(node_df.columns)
    }


def _add_map_title(m: folium.Map, title_text: str) -> None:
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
