# Data Collector-NT (v1.0)

**Data Collector-NT** builds datasets for the ENTSO-E / ENTSO-G **National Trends (NT)**
scenario. The **-NT** suffix denotes that the underlying source data (demand, capacities,
prices, cross-border exchanges, etc.) is drawn from the *National Trends* pathway of the
TYNDP.

A tool for assembling **pan-European power, gas and hydrogen system datasets** for
energy-system modelling. It reads the raw [ENTSO-E](https://www.entsoe.eu/) and
[ENTSO-G](https://www.entsog.eu/) TYNDP / PEMMDB / PECD source files, lets you pick
countries, zones and a scenario through an interactive web map, and exports a clean,
ready-to-use dataset — either in a human-readable **Normal** Excel format or as a
complete **[openTEPES](https://opentepes.readthedocs.io/)** CSV input set.

All underlying data originates from the [ENTSO-E](https://www.entsoe.eu/) (electricity)
and [ENTSO-G](https://www.entsog.eu/) (gas) *Ten-Year Network Development Plan (TYNDP)*
public datasets.

---

## Table of contents

- [Features](#features)
- [How it works](#how-it-works)
- [Repository structure](#repository-structure)
- [Installation](#installation)
- [Running the app](#running-the-app)
- [Using the web UI](#using-the-web-ui)
- [Outputs](#outputs)
  - [Normal mode](#normal-mode)
  - [openTEPES mode](#opentepes-mode)
  - [Processing.log](#processinglog)
- [Data sources](#data-sources)
- [Data limitations by scenario](#data-limitations-by-scenario)
- [License](#license)
- [Credits](#credits)

---

## Features

- **Interactive map selector** — countries render red, turn green when selected; pick
  individual bidding zones per country, with partial-selection (`–`) indicators.
- **Scenario aware** — TYNDP scenario years **2030 / 2040 / 2050**, configurable climate
  year and hours-per-year horizon.
- **Two export formats**
  - **Normal** — one Excel workbook per zone plus a shared network workbook.
  - **openTEPES** — a full `oT_Data_*` / `oT_Dict_*` CSV input set ready to solve.
- **Infrastructure scenario switches** for gas & hydrogen pipelines, storage and terminals.
- **Rich HTML visualisations** — capacity charts, hourly profile time series, and
  Leaflet electricity / gas / hydrogen network maps.
- **One-click ZIP download** containing all outputs plus a `Processing.log`.

---

## How it works

```
 Raw ENTSO-E / ENTSO-G files            Web UI (Django)              Export
 ────────────────────────────    ─────────────────────────    ────────────────────
  PEMMDB2  (capacities/chars)                                    Normal  → *.xlsx
  PECD     (RES profiles)     →   select zones + scenario   →    openTEPES → oT_*.csv
  Prices   (TYNDP commodity)      click "Generate"               HTMLs   → *.html
  Networks / Storages / …                                        Processing.log
```

The Django `generate` view calls `collector.main.run(...)`, which executes the full
pipeline (load → transform → visualise → export) and streams a ZIP of the results back
to the browser.

---

## Repository structure

```
Data Collector/
├── collector/                 # Data pipeline (pure Python, importable)
│   ├── main.py                # run() — orchestrates the whole pipeline
│   ├── data/loader.py         # Readers for PEMMDB / PECD / prices / networks
│   ├── processing/transforms.py # Network / storage / terminal / profile transforms
│   ├── models/
│   │   ├── core.py            # "Normal" per-zone Excel export
│   │   └── opentepes.py       # openTEPES CSV export
│   ├── visualization/plots.py # HTML charts and network maps
│   ├── utils/config.py        # Column definitions, file paths, constants
│   ├── inputs/                # Raw source data (ENTSO-E / ENTSO-G files)
│   └── outputs/               # Generated results
│       ├── HTMLs/
│       └── Excel Files/{Normal,openTEPES}/
├── ui/                        # Django project (web front-end)
│   ├── manage.py
│   ├── selector/              # App: map UI, session state, /api/generate/
│   └── siteproj/settings.py
├── opentepes/                 # Notebook to solve the exported openTEPES case
│   └── openTEPES.ipynb
├── run.bat                    # Windows launcher (starts server + opens browser)
└── requirements.txt
```

---

## Installation

**Requirements:** Python 3.10+ (Windows is the primary supported platform).

### Automatic (recommended)

Just run the launcher — on **any computer that has Python installed**, it creates a
fresh local virtual environment, installs the dependencies, applies migrations, starts
the server and opens the browser:

```bash
run.bat
```

### Manual

```bash
# 1. Create and activate a virtual environment
python -m venv collector-venv
collector-venv\Scripts\activate        # PowerShell: collector-venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialise the database (seeds the countries / zones)
python ui/manage.py migrate
```

### As an installable package (optional)

The repository ships a `setup.py` so the pipeline can be installed as a proper
Python package (`entso-e-collector`) rather than run from the source tree. This is
optional — `run.bat` and the web UI do **not** require it — but it is useful if you
want to `import collector` from elsewhere or run the pipeline from the command line.

```bash
# Editable/develop install: puts the `collector` package on the import path
# (dependencies come from requirements.txt) while keeping the source live.
pip install -e .
```

This also registers a **`collector-run`** console command (mapped to
`collector.main:run`), so you can trigger the pipeline directly instead of going
through Django. Requires Python 3.10+.

> The raw ENTSO-E / ENTSO-G source files must be present under `collector/inputs/`
> (PEMMDB2, PECD, Prices, Networks.xlsx, Storages.xlsx, Terminals.xlsx, etc.).
> These are large TYNDP datasets and are **not** distributed in this repository.

---

## Running the app

**Windows (quickest):**

```bash
run.bat
```

This starts the Django server and opens `http://localhost:8000` in your browser.

**Manual:**

```bash
python ui/manage.py runserver 0.0.0.0:8000
```

Endpoints:

| URL | Purpose |
| --- | --- |
| `/` | Interactive map + settings UI |
| `/api/selection/` | Current zone/scenario selection (JSON) |
| `/api/generate/` | Runs the pipeline, returns the output ZIP (POST) |

---

## Using the web UI

1. **Settings** (top box) — choose the **Scenario** year, **Climate Year**,
   **Output Format** (`Normal` or `openTEPES`), **Hours per Year**, and the gas/hydrogen
   pipeline, storage and terminal infrastructure levels.
2. **Countries** — tick a country to activate it (turns green on the map). Expand it to
   select individual **zones**; a partially-selected country shows a `–` indicator.
3. **Generate** — builds the dataset and downloads `collector_outputs.zip`.

---

## Outputs

The downloaded ZIP has this layout:

```
collector_outputs.zip
├── HTMLs/                      # Interactive charts & maps
├── Excel Files/
│   └── <Normal | openTEPES>/   # Only the selected mode is included
└── Processing.log              # Full run log
```

### Normal mode

One workbook **per zone** (e.g. `ES00.xlsx`) plus a shared **`Networks.xlsx`**.

Per-zone workbook sheets:

| Sheet | Contents |
| --- | --- |
| Technology Capacities | Installed MW per technology |
| Storage Capacities | Storage energy (MWh) per technology |
| Reserve Requirements | FCR / FRR reserve needs |
| Hourly Profiles | Hourly time series (demand, RES, flows, exports) |
| Technology Characteristics | Efficiency, ramps, min stable power, fuel cost, CO₂, … |
| Gas & Hydrogen Assets | Pipeline / storage / terminal capacities |

`Networks.xlsx` holds the electricity, gas and hydrogen line/pipeline tables, plus a
**`Data`** sheet with the scenario `CO2 Price (EUR/ton)` and `Gas Price (EUR/MWh)`.

### openTEPES mode

A complete openTEPES input set: `oT_Dict_*.csv` (index sets — nodes, zones, generators,
technologies, load levels, …) and `oT_Data_*.csv` (parameters — generation, demand,
network, reserves, energy inflows, etc.). This folder can be dropped straight into an
openTEPES case (see [below](#running-opentepes-on-the-output)).

### Processing.log

A plain-text log written to the ZIP root, capturing **all console output** produced
during the run (every pipeline step, warnings about skipped files, timings), bracketed
by a header (start time, selected zones, mode, scenario) and a footer (finish time).
Use it to trace exactly what was loaded and to diagnose missing-data warnings.

---

## Data sources

All input data is taken from the publicly published *Ten-Year Network Development Plan
(TYNDP)* datasets:

- **[ENTSO-E](https://www.entsoe.eu/)** — European Network of Transmission System
  Operators for **Electricity**. Source of PEMMDB2 generation capacities and
  characteristics, PECD RES/hydro profiles, electricity demand, and electricity network
  data.
- **[ENTSO-G](https://www.entsog.eu/)** — European Network of Transmission System
  Operators for **Gas**. Source of gas and hydrogen demand, pipelines, storage and
  terminal infrastructure.
- **TYNDP 2024 commodity prices** — fuel and CO₂ prices (EUR/GJ → EUR/MWh, CO₂ in EUR/ton).

---

## Data limitations by scenario

Not every dataset is published for every TYNDP scenario year. The pipeline degrades
gracefully (it warns in `Processing.log` and fills gaps with zeros) but you should be
aware of the following:

| Limitation | Affected scenario(s) | Effect |
| --- | --- | --- |
| **Hydrogen demand profiles** are only published for 2030 and 2040 | **2050** | Generating for 2050 raises an error / omits H₂ demand; H₂-into-electricity demand conversion is unavailable. |
| **Cross-border exchange** results are published only for the **2009 climate year**, and only for the **2030 and 2040** scenarios | **2050**, and **any non-2009 climate year** | For **2050** the exchange series are unavailable, so exports-to-demand contributions are zero. For **2030 / 2040** the exchange always uses **climate year 2009**, regardless of the climate year you select — the selection is ignored for exchanges. |
| **Gas price is not available for the 2050 scenario** — the *Gas blend NT+* row has no 2050 value in the TYNDP price sheet | **2050** | `Gas Price (EUR/MWh)` is unavailable and falls back to 0 for 2050. |
| Some technologies / DSR types may be absent for a given zone | any | Missing entries are skipped rather than written as zero rows. |

Always check `Processing.log` after a run — any skipped source file is reported there.

---

## License

Released under the [MIT License](LICENSE) — © 2026 **Emad Nematbakhsh**.

The ENTSO-E / ENTSO-G TYNDP source data is **not** covered by this license and remains
subject to its original terms.

## Credits

© **Emad Nematbakhsh**
[IIT](https://www.iit.comillas.edu/) · [Comillas Pontifical University](https://www.comillas.edu/en/)

Data © [ENTSO-E](https://www.entsoe.eu/) and [ENTSO-G](https://www.entsog.eu/) (TYNDP).
