import io
import json
import os
import sys
import traceback
import zipfile
from datetime import datetime
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from collector.utils.config import (
    GAS_PIPE_OPTIONS,
    GAS_STORAGE_OPTIONS,
    GAS_TERMINAL_OPTIONS,
    HYDROGEN_PIPE_OPTIONS,
    HYDROGEN_STORAGE_OPTIONS,
    HYDROGEN_TERMINAL_OPTIONS,
    OUTPUT_MODES,
)

from .models import Country

SESSION_KEY_COUNTRIES = "country_zone_selection"
SESSION_KEY_META = "required_data_meta"


class _Tee:
    """Write to several streams at once (e.g. real stdout + an in-memory log)."""

    def __init__(self, *streams: Any) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        for s in self._streams:
            try:
                s.write(data)
            except Exception:
                pass
        return len(data)

    def flush(self) -> None:
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass

_META_VALIDATORS: dict[str, Any] = {
    "scenario":          lambda v: v in ("2030", "2040", "2050"),
    "climate_year":      lambda v: v in ("2009",),
    "gas_pipe":          lambda v: v in GAS_PIPE_OPTIONS,
    "hydrogen_pipe":     lambda v: v in HYDROGEN_PIPE_OPTIONS,
    "gas_storage":       lambda v: v in GAS_STORAGE_OPTIONS,
    "hydrogen_storage":  lambda v: v in HYDROGEN_STORAGE_OPTIONS,
    "gas_terminal":      lambda v: v in GAS_TERMINAL_OPTIONS,
    "hydrogen_terminal": lambda v: v in HYDROGEN_TERMINAL_OPTIONS,
    "output_mode":       lambda v: v in OUTPUT_MODES,
    "hours":             lambda v: str(v).isdigit() and 1 <= int(v) <= 8760,
    "generate_html":     lambda v: v in ("yes", "no"),
}

_META_DEFAULTS: dict[str, str] = {
    "scenario":          "2030",
    "climate_year":      "2009",
    "gas_pipe":          "Existing",
    "hydrogen_pipe":     "PCI/PMI",
    "gas_storage":       "Low",
    "hydrogen_storage":  "PCI/PMI",
    "gas_terminal":      "Low",
    "hydrogen_terminal": "PCI/PMI",
    "output_mode":       "Normal",
    "hours":             "8736",
    "generate_html":     "no",
}


def _get_countries_selection(request: HttpRequest) -> dict[str, Any]:
    raw = request.session.get(SESSION_KEY_COUNTRIES)
    return raw if isinstance(raw, dict) else {}


def _set_countries_selection(request: HttpRequest, selection: dict[str, Any]) -> None:
    request.session[SESSION_KEY_COUNTRIES] = selection
    request.session.modified = True


def _get_meta(request: HttpRequest) -> dict[str, Any]:
    raw = request.session.get(SESSION_KEY_META)
    return raw if isinstance(raw, dict) else {}


def _set_meta(request: HttpRequest, meta: dict[str, Any]) -> None:
    request.session[SESSION_KEY_META] = meta
    request.session.modified = True


def _response_payload(request: HttpRequest) -> dict[str, Any]:
    return {"meta": _get_meta(request), "countries": _get_countries_selection(request)}


@require_http_methods(["GET"])
def index(request: HttpRequest) -> HttpResponse:
    countries = Country.objects.prefetch_related("zones").all()
    data = [
        {
            "iso3": c.iso3,
            "iso2": c.iso2,
            "name": c.name,
            "zones": [z.code for z in c.zones.all()],
        }
        for c in countries
    ]
    return render(request, "selector/index.html", {"countries_json": json.dumps(data)})


@require_http_methods(["GET", "POST"])
def selection_api(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse(_response_payload(request))

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # ── Meta update: any known meta key present in the payload ───────────────
    meta_keys_in_payload = set(payload.keys()) & set(_META_VALIDATORS.keys())
    if meta_keys_in_payload:
        meta = _get_meta(request)
        for key in meta_keys_in_payload:
            value = payload[key]
            if not _META_VALIDATORS[key](str(value)):
                return JsonResponse(
                    {"error": f"Invalid value for '{key}': {value!r}"}, status=400
                )
            meta[key] = str(value)
        _set_meta(request, meta)
        return JsonResponse(_response_payload(request))

    # ── Country / zone update ────────────────────────────────────────────────
    country = payload.get("country")
    active = payload.get("active")
    zones = payload.get("zones", [])

    if not isinstance(country, str) or len(country) != 3:
        return JsonResponse({"error": "country must be ISO3 string"}, status=400)
    if not isinstance(active, bool):
        return JsonResponse({"error": "active must be boolean"}, status=400)
    if not isinstance(zones, list) or not all(isinstance(z, str) for z in zones):
        return JsonResponse({"error": "zones must be list[str]"}, status=400)

    selection = _get_countries_selection(request)
    if not active:
        selection.pop(country, None)
    else:
        selection[country] = {"active": True, "zones": zones}
    _set_countries_selection(request, selection)
    return JsonResponse(_response_payload(request))


@require_http_methods(["POST"])
def generate(request: HttpRequest) -> HttpResponse:
    selection = _get_countries_selection(request)
    meta = _get_meta(request)

    # Collect flat list of zone codes from all active countries
    selected_zones: list[str] = []
    for entry in selection.values():
        if entry.get("active"):
            selected_zones.extend(entry.get("zones", []))

    if not selected_zones:
        return JsonResponse({"error": "No zones selected"}, status=400)

    def _get(key: str) -> str:
        return meta.get(key, _META_DEFAULTS[key])

    # Capture all print()/stdout+stderr output produced during the run so it can
    # be saved as Processing.log inside the ZIP (still echoed to the console).
    log_buf = io.StringIO()
    log_buf.write(f"Data Collector — Processing log\n")
    log_buf.write(f"Started: {datetime.now().isoformat(timespec='seconds')}\n")
    log_buf.write(f"Zones  : {', '.join(selected_zones)}\n")
    log_buf.write(f"Mode   : {_get('output_mode')}  |  Scenario: {_get('scenario')}\n")
    log_buf.write("=" * 70 + "\n")

    _old_out, _old_err = sys.stdout, sys.stderr
    try:
        from collector.main import run

        sys.stdout = _Tee(_old_out, log_buf)
        sys.stderr = _Tee(_old_err, log_buf)
        try:
            run(
                selected_scenario=int(_get("scenario")),
                selected_climate_year=int(_get("climate_year")),
                selected_zones=selected_zones,
                selected_hours=int(_get("hours")),
                selected_gas_pipe=_get("gas_pipe"),
                selected_hydrogen_pipe=_get("hydrogen_pipe"),
                selected_gas_storage=_get("gas_storage"),
                selected_hydrogen_storage=_get("hydrogen_storage"),
                selected_gas_terminal=_get("gas_terminal"),
                selected_hydrogen_terminal=_get("hydrogen_terminal"),
                selected_output=_get("output_mode"),
                selected_generate_html=(_get("generate_html") == "yes"),
                base_path=settings.COLLECTOR_BASE_PATH,
            )
        finally:
            sys.stdout, sys.stderr = _old_out, _old_err
    except Exception as exc:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)  # full traceback to the server console
        return JsonResponse({"error": f"{exc}\n\n{tb}"}, status=500)

    log_buf.write("=" * 70 + "\n")
    log_buf.write(f"Finished: {datetime.now().isoformat(timespec='seconds')}\n")

    # Build ZIP: all HTMLs + Excel files for the selected mode only
    outputs_root = os.path.join(settings.COLLECTOR_BASE_PATH, "outputs")
    output_mode  = _get("output_mode")
    zip_sources  = [
        (os.path.join(outputs_root, "Excel Files", output_mode), os.path.join("Excel Files", output_mode)),
    ]
    # Only include the HTMLs folder when HTML output generation is enabled.
    if _get("generate_html") == "yes":
        zip_sources.insert(0, (os.path.join(outputs_root, "HTMLs"), "HTMLs"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for src_dir, arc_prefix in zip_sources:
            if not os.path.isdir(src_dir):
                continue
            for fname in os.listdir(src_dir):
                fpath = os.path.join(src_dir, fname)
                if os.path.isfile(fpath):
                    zf.write(fpath, os.path.join(arc_prefix, fname))
        # Processing log at the ZIP root, next to HTMLs and Excel Files
        zf.writestr("Processing.log", log_buf.getvalue())
    buf.seek(0)

    response = HttpResponse(buf.read(), content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="collector_outputs.zip"'
    return response
