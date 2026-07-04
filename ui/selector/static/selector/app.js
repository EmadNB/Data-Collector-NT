/* global L */

const GEOJSON_URL =
  "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json";

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(";").shift();
  return null;
}

function parseCountries() {
  const el = document.getElementById("countries-data");
  return JSON.parse(el.textContent);
}

function defaultZonesForCountry(country) {
  if (!Array.isArray(country?.zones)) return [];
  if (country.zones.length > 1) return country.zones.slice();
  return country.zones.slice(0, 1);
}

async function apiGetSelection() {
  const res = await fetch("/api/selection/", { credentials: "same-origin" });
  if (!res.ok) throw new Error(`GET /api/selection failed: ${res.status}`);
  return await res.json();
}

async function apiSetMeta(fields) {
  const res = await fetch("/api/selection/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify(fields),
  });
  if (!res.ok) throw new Error(`POST /api/selection failed: ${res.status}`);
  return await res.json();
}

async function apiSetCountry({ country, active, zones }) {
  const res = await fetch("/api/selection/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({ country, active, zones }),
  });
  if (!res.ok) throw new Error(`POST /api/selection failed: ${res.status}`);
  return await res.json();
}

function createMap(activeIso3Set, { onCountryClick } = {}) {
  const map = L.map("map", {
    zoomControl: true,
    minZoom: 2,
  }).setView([48.0, 10.0], 4);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
  }).addTo(map);

  const baseStyle = (feature) => {
    const iso3 = feature?.id;
    const active = iso3 && activeIso3Set.has(iso3);
    return {
      color: "rgba(255,255,255,0.45)",
      weight: 1,
      fillColor: active ? "#22c55e" : "#ef4444",
      fillOpacity: 0.45,
    };
  };

  const layer = L.geoJSON(null, {
    style: baseStyle,
    onEachFeature: (feature, l) => {
      const name = feature?.properties?.name || feature?.id;
      l.bindTooltip(name, { sticky: true, direction: "top" });
      l.on("click", () => {
        const iso3 = feature?.id;
        if (iso3 && typeof onCountryClick === "function") onCountryClick(iso3);
      });
    },
  }).addTo(map);

  async function loadGeoJson(allowedIso3) {
    const res = await fetch(GEOJSON_URL);
    if (!res.ok) throw new Error(`GeoJSON load failed: ${res.status}`);
    const fc = await res.json();
    const filtered = {
      type: "FeatureCollection",
      features: fc.features.filter((f) => allowedIso3.has(f.id)),
    };
    layer.addData(filtered);
    fitSelected();
  }

  function restyle() {
    layer.setStyle(baseStyle);
  }

  // Zoom so the given bounds fill the map's height (N–S) with a small margin,
  // allowing horizontal overflow. Used when none / all countries are selected.
  function fitToHeight(bounds, marginPx = 12) {
    try {
      const north = bounds.getNorth();
      const south = bounds.getSouth();
      const lng = (bounds.getEast() + bounds.getWest()) / 2;
      const availH = map.getSize().y - 2 * marginPx;
      let best = map.getMinZoom();
      for (let z = map.getMaxZoom(); z >= map.getMinZoom(); z--) {
        const top = map.project([north, lng], z);
        const bot = map.project([south, lng], z);
        if (Math.abs(bot.y - top.y) <= availH) { best = z; break; }
      }
      map.setView(bounds.getCenter(), best);
    } catch (_) {}
  }

  function fitSelected() {
    const allLayers = layer.getLayers();
    const activeLayers = allLayers.filter(l => activeIso3Set.has(l.feature?.id));
    // Nothing selected or everything selected → fit all countries to map height
    if (activeLayers.length === 0 || activeLayers.length === allLayers.length) {
      fitToHeight(layer.getBounds());
      return;
    }
    try {
      const group = L.featureGroup(activeLayers);
      map.fitBounds(group.getBounds(), { padding: [10, 10], maxZoom: 10 });
    } catch (_) {}
  }

  return { map, layer, loadGeoJson, restyle, fitSelected };
}

function countryFlagEl(country) {
  // Derive ISO2 from the first zone code (e.g. "ES00" → "es")
  const raw = (country.zones?.[0] ?? "").slice(0, 2).toUpperCase();
  // ENTSO-E quirks: UK → gb, EL (Greece) → gr
  const map = { UK: "gb", EL: "gr" };
  const iso2 = (map[raw] ?? raw).toLowerCase();
  const el = document.createElement("span");
  el.className = `fi fi-${iso2} country__flag`;
  return el;
}

function buildUI({ countries, state, onChange }) {
  const listEl = document.getElementById("country-list");
  listEl.innerHTML = "";

  const byIso3 = new Map(countries.map((c) => [c.iso3, c]));

  function getSelectedZones(iso3) {
    const entry = state?.countries?.[iso3];
    if (entry && Array.isArray(entry.zones)) return entry.zones;
    return [];
  }

  function isActive(iso3) {
    return Boolean(state?.countries?.[iso3]?.active);
  }

  function setSelection(next) {
    state = next;
  }

  function createCountryRow(country) {
    const wrapper = document.createElement("div");
    wrapper.className = "country";

    const top = document.createElement("div");
    top.className = "country__top";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = isActive(country.iso3);

    const nameWrap = document.createElement("div");
    nameWrap.className = "country__name";
    nameWrap.appendChild(countryFlagEl(country));
    const nameText = document.createElement("span");
    nameText.textContent = country.name;
    nameWrap.appendChild(nameText);

    const code = document.createElement("div");
    code.className = "country__code";
    code.textContent = country.iso2 || country.iso3;

    top.appendChild(cb);
    top.appendChild(nameWrap);
    top.appendChild(code);

    const hasManyZones = Array.isArray(country.zones) && country.zones.length > 1;
    const singleOrNoneZones = Array.isArray(country.zones) ? country.zones.slice(0, 1) : [];

    const zonesWrap = document.createElement("div");
    zonesWrap.className = "zones" + (cb.checked ? " zones--active" : "");
    if (!hasManyZones) {
      zonesWrap.style.display = "none";
    }

    const actions = document.createElement("div");
    actions.className = "zones__actions";

    const btnAll = document.createElement("button");
    btnAll.className = "btn";
    btnAll.type = "button";
    btnAll.textContent = "Select all zones";

    const btnNone = document.createElement("button");
    btnNone.className = "btn";
    btnNone.type = "button";
    btnNone.textContent = "Select none";

    actions.appendChild(btnAll);
    actions.appendChild(btnNone);
    zonesWrap.appendChild(actions);

    const zoneList = document.createElement("div");
    zoneList.className = "zone-list";
    zonesWrap.appendChild(zoneList);

    // Reflect partial zone selection as an indeterminate ("-") country checkbox
    const updateCountryCb = () => {
      if (!hasManyZones) {
        cb.checked = isActive(country.iso3);
        cb.indeterminate = false;
        return;
      }
      const selCount = getSelectedZones(country.iso3).length;
      const total = country.zones.length;
      cb.checked = total > 0 && selCount === total;
      cb.indeterminate = selCount > 0 && selCount < total;
    };

    const zoneCheckboxes = new Map();
    const renderZones = () => {
      zoneList.innerHTML = "";
      zoneCheckboxes.clear();

      const selected = new Set(getSelectedZones(country.iso3));
      for (const z of country.zones) {
        const label = document.createElement("label");
        label.className = "zone";

        const zcb = document.createElement("input");
        zcb.type = "checkbox";
        zcb.checked = selected.has(z);
        zoneCheckboxes.set(z, zcb);

        const text = document.createElement("span");
        text.innerHTML = `<code>${z}</code>`;

        label.appendChild(zcb);
        label.appendChild(text);
        zoneList.appendChild(label);

        zcb.addEventListener("change", async () => {
          const nextZones = Array.from(zoneCheckboxes.entries())
            .filter(([_, el]) => el.checked)
            .map(([code]) => code);

          if (nextZones.length === 0) {
            cb.checked = false;
            zonesWrap.classList.remove("zones--active");
            await onChange({ iso3: country.iso3, active: false, zones: [], setSelection });
          } else {
            await onChange({ iso3: country.iso3, active: true, zones: nextZones, setSelection });
          }
          renderZones();
        });
      }
      updateCountryCb();
    };

    const setAll = async (checked) => {
      for (const el of zoneCheckboxes.values()) el.checked = checked;
      const nextZones = checked ? [...country.zones] : [];
      if (nextZones.length === 0) {
        cb.checked = false;
        zonesWrap.classList.remove("zones--active");
        await onChange({ iso3: country.iso3, active: false, zones: [], setSelection });
      } else {
        await onChange({ iso3: country.iso3, active: true, zones: nextZones, setSelection });
      }
      renderZones();
    };

    if (hasManyZones) {
      btnAll.addEventListener("click", async () => setAll(true));
      btnNone.addEventListener("click", async () => setAll(false));
    }

    cb.addEventListener("change", async () => {
      if (!cb.checked) {
        zonesWrap.classList.remove("zones--active");
        await onChange({ iso3: country.iso3, active: false, zones: [], setSelection });
        return;
      }

      if (hasManyZones) zonesWrap.classList.add("zones--active");
      const defaultZones = hasManyZones ? country.zones.slice() : singleOrNoneZones;
      if (defaultZones.length === 0) {
        cb.checked = false;
        zonesWrap.classList.remove("zones--active");
        await onChange({ iso3: country.iso3, active: false, zones: [], setSelection });
        return;
      }
      await onChange({ iso3: country.iso3, active: true, zones: defaultZones, setSelection });
      if (hasManyZones) renderZones();
    });

    if (hasManyZones) renderZones();

    wrapper.appendChild(top);
    if (hasManyZones) wrapper.appendChild(zonesWrap);
    return wrapper;
  }

  const sorted = [...countries].sort((a, b) => a.name.localeCompare(b.name));
  for (const c of sorted) listEl.appendChild(createCountryRow(c));

  return {
    setSelection,
    getCountryByIso3: (iso3) => byIso3.get(iso3),
  };
}

// ── Generate: call pipeline and trigger ZIP download ─────────────────────────

function setGenerateState(btn, statusEl, { loading, message, error }) {
  btn.disabled = loading;
  btn.textContent = loading ? "Running…" : "Generate";
  statusEl.textContent = message || "";
  statusEl.className = "generate-status" +
    (error ? " generate-status--error" : loading ? " generate-status--running" : "");
}

async function handleGenerate(btn, statusEl) {
  setGenerateState(btn, statusEl, { loading: true, message: "Pipeline running, please wait…" });
  const startTime = Date.now();

  try {
    const res = await fetch("/api/generate/", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": getCookie("csrftoken") },
    });

    if (!res.ok) {
      let msg = `Server error ${res.status}`;
      try {
        const body = await res.json();
        if (body.error) msg = body.error;
      } catch (_) {}
      throw new Error(msg);
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "collector_outputs.zip";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    setGenerateState(btn, statusEl, { loading: false, message: `Done — outputs downloaded. (${elapsed}s)` });
  } catch (err) {
    setGenerateState(btn, statusEl, { loading: false, message: err.message, error: true });
  }
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  const countries = parseCountries();
  const allowedIso3 = new Set(countries.map((c) => c.iso3));
  const countryByIso3 = new Map(countries.map((c) => [c.iso3, c]));

  let state = { meta: {}, countries: {} };
  try {
    const loaded = await apiGetSelection();
    if (loaded && typeof loaded === "object") state = loaded;
  } catch (_) {
    state = { meta: {}, countries: {} };
  }

  // ── Restore saved meta into controls ───────────────────────────────────────
  const meta = state.meta || {};

  const scenarioEl         = document.getElementById("scenario-select");
  const climateEl          = document.getElementById("climate-year-select");
  const outputModeEl       = document.getElementById("output-mode-select");
  const hoursEl            = document.getElementById("hours-input");
  const gasPipeEl          = document.getElementById("gas-pipe-select");
  const hydrogenPipeEl     = document.getElementById("hydrogen-pipe-select");
  const gasStorageEl       = document.getElementById("gas-storage-select");
  const hydrogenStorageEl  = document.getElementById("hydrogen-storage-select");
  const gasTerminalEl      = document.getElementById("gas-terminal-select");
  const hydrogenTerminalEl = document.getElementById("hydrogen-terminal-select");
  const selectAllEl        = document.getElementById("select-all-countries");
  const generateEl         = document.getElementById("generate-btn");
  const statusEl           = document.getElementById("generate-status");
  const networkToggleEl    = document.getElementById("network-toggle");
  const networkBodyEl      = document.getElementById("network-body");

  if (scenarioEl && meta.scenario)               scenarioEl.value         = meta.scenario;
  if (climateEl && meta.climate_year)            climateEl.value          = meta.climate_year;
  if (outputModeEl && meta.output_mode)          outputModeEl.value       = meta.output_mode;
  if (hoursEl && meta.hours)                     hoursEl.value            = meta.hours;
  if (gasPipeEl && meta.gas_pipe)                gasPipeEl.value          = meta.gas_pipe;
  if (hydrogenPipeEl && meta.hydrogen_pipe)      hydrogenPipeEl.value     = meta.hydrogen_pipe;
  if (gasStorageEl && meta.gas_storage)          gasStorageEl.value       = meta.gas_storage;
  if (hydrogenStorageEl && meta.hydrogen_storage) hydrogenStorageEl.value = meta.hydrogen_storage;
  if (gasTerminalEl && meta.gas_terminal)        gasTerminalEl.value      = meta.gas_terminal;
  if (hydrogenTerminalEl && meta.hydrogen_terminal) hydrogenTerminalEl.value = meta.hydrogen_terminal;

  // ── Network options toggle ─────────────────────────────────────────────────
  if (networkToggleEl && networkBodyEl) {
    networkToggleEl.addEventListener("click", () => {
      const open = networkToggleEl.getAttribute("aria-expanded") === "true";
      networkToggleEl.setAttribute("aria-expanded", String(!open));
      networkToggleEl.classList.toggle("section-toggle--open", !open);
      networkBodyEl.classList.toggle("section-body--open", !open);
    });
  }

  // ── Meta change handlers ───────────────────────────────────────────────────
  function bindMeta(el, key) {
    if (!el) return;
    el.addEventListener("change", async () => {
      const next = await apiSetMeta({ [key]: el.value });
      state = next;
    });
  }
  function bindMetaInput(el, key) {
    if (!el) return;
    el.addEventListener("change", async () => {
      const val = el.value.trim();
      if (!val) return;
      const next = await apiSetMeta({ [key]: val });
      state = next;
    });
  }

  bindMeta(scenarioEl,         "scenario");
  bindMeta(climateEl,          "climate_year");
  bindMeta(outputModeEl,       "output_mode");
  bindMeta(gasPipeEl,          "gas_pipe");
  bindMeta(hydrogenPipeEl,     "hydrogen_pipe");
  bindMeta(gasStorageEl,       "gas_storage");
  bindMeta(hydrogenStorageEl,  "hydrogen_storage");
  bindMeta(gasTerminalEl,      "gas_terminal");
  bindMeta(hydrogenTerminalEl, "hydrogen_terminal");
  bindMetaInput(hoursEl,       "hours");

  // ── Country / zone selection ───────────────────────────────────────────────
  const activeIso3Set = new Set(
    Object.entries(state.countries || {})
      .filter(([_, v]) => v && v.active)
      .map(([iso3]) => iso3),
  );

  async function onCountryChange({ iso3, active, zones, setSelection }) {
    const next = await apiSetCountry({ country: iso3, active, zones });
    state = next;
    setSelection(next);
    if (active) activeIso3Set.add(iso3);
    else activeIso3Set.delete(iso3);
    mapCtx.restyle();
    mapCtx.fitSelected();
  }

  function syncSelectAllCheckbox() {
    if (!selectAllEl) return;
    const total = countries.length;
    const activeCount = Object.values(state.countries || {}).filter((v) => v?.active).length;
    selectAllEl.indeterminate = activeCount > 0 && activeCount < total;
    selectAllEl.checked = total > 0 && activeCount === total;
  }

  function updateSelectionCount() {
    const el = document.getElementById("selection-count");
    if (!el) return;
    const entries = Object.values(state.countries || {}).filter((v) => v?.active);
    const numCountries = entries.length;
    const numZones = entries.reduce((sum, v) => sum + (v.zones?.length || 0), 0);
    if (numCountries === 0) {
      el.textContent = "";
      return;
    }
    const cLabel = numCountries === 1 ? "Country" : "Countries";
    const zLabel = numZones === 1 ? "Zone" : "Zones";
    el.textContent = `(${numCountries} ${cLabel} and ${numZones} ${zLabel} Selected)`;
  }

  function renderCountriesUI() {
    const ui = buildUI({
      countries,
      state,
      onChange: async (args) => {
        await onCountryChange(args);
        syncSelectAllCheckbox();
        updateSelectionCount();
      },
    });
    ui.setSelection(state);
    syncSelectAllCheckbox();
    updateSelectionCount();
  }

  let mapClickBusy = false;
  let mapCtx;

  async function toggleCountryFromMap(iso3) {
    if (mapClickBusy) return;
    if (!allowedIso3.has(iso3)) return;
    const country = countryByIso3.get(iso3);
    if (!country) return;

    mapClickBusy = true;
    try {
      const currentlyActive = Boolean(state?.countries?.[iso3]?.active);
      if (currentlyActive) {
        state = await apiSetCountry({ country: iso3, active: false, zones: [] });
        activeIso3Set.delete(iso3);
      } else {
        const zones = defaultZonesForCountry(country);
        if (zones.length === 0) return;
        state = await apiSetCountry({ country: iso3, active: true, zones });
        activeIso3Set.add(iso3);
      }
      renderCountriesUI();
      mapCtx.restyle();
      mapCtx.fitSelected();
    } finally {
      mapClickBusy = false;
    }
  }

  mapCtx = createMap(activeIso3Set, { onCountryClick: toggleCountryFromMap });
  await mapCtx.loadGeoJson(allowedIso3);

  renderCountriesUI();
  mapCtx.restyle();

  if (selectAllEl) {
    selectAllEl.addEventListener("change", async () => {
      const turnOn = selectAllEl.checked;
      selectAllEl.indeterminate = false;

      for (const c of countries) {
        const zones = turnOn ? defaultZonesForCountry(c) : [];
        const active = turnOn && zones.length > 0;
        state = await apiSetCountry({ country: c.iso3, active, zones });
      }

      activeIso3Set.clear();
      for (const [iso3, v] of Object.entries(state.countries || {})) {
        if (v?.active) activeIso3Set.add(iso3);
      }

      renderCountriesUI();
      mapCtx.restyle();
      mapCtx.fitSelected();
    });
  }

  // ── Generate button ────────────────────────────────────────────────────────
  if (generateEl) {
    generateEl.addEventListener("click", () => handleGenerate(generateEl, statusEl));
  }
}

main().catch((err) => {
  console.error(err);
});
