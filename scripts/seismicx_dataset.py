#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utilities bundled with the SeismicX dataset skill."""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import fnmatch
import glob
import hashlib
import json
import math
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


SKILL_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = SKILL_DIR / "assets"
MSEEDINDEX_DIR = ASSETS_DIR / "mseedindex"
MSEEDINDEX_REPO = "https://github.com/EarthScope/mseedindex.git"

DEFAULT_LOCATION = "--"
CANONICAL_FORMAT = "seismicx_canonical_labels_v1"
HDF5_FORMAT = "seismicx_standard_hdf5_v1"

WAVEFORM_SUFFIXES = {
    ".mseed",
    ".msd",
    ".miniseed",
    ".seed",
    ".sac",
    ".sacpz",
    ".gcf",
    ".segy",
    ".sgy",
    ".su",
    ".wav",
}

EVENT_FIELDS = [
    "type",
    "event_id",
    "source_type",
    "source_origintime",
    "source_origintime_err",
    "source_origintime_ref",
    "time_standard",
    "source_longitude_deg",
    "source_latitude_deg",
    "source_depth_km",
    "source_magnitude_type",
    "source_magnitude",
    "source_magnitude_error",
    "preferred_magnitude_type",
    "source_area",
    "source_agency",
    "location_method",
    "velocity_model_id",
    "num_phases_used",
    "num_stations_used",
    "max_azimuthal_gap_deg",
    "station_azimuth_uniformity",
    "min_epicentral_dist_km",
    "max_epicentral_dist_km",
    "horizontal_uncertainty_major_km",
    "horizontal_uncertainty_minor_km",
    "horizontal_uncertainty_azimuth",
    "vertical_uncertainty_km",
    "residual_mean_sec",
    "location_rms_sec",
    "event_status",
    "updated_time",
    "source_moment",
    "source_fault_plane",
    "source_fault_plane_err",
    "event_remark",
]

STATION_FIELDS = [
    "type",
    "station_id",
    "station_network",
    "station_station",
    "station_location",
    "station_channel_list",
    "station_longitude_deg",
    "station_latitude_deg",
    "station_elevation_m",
    "station_depth_m",
    "station_area",
    "station_agency",
    "station_remark",
]

LABEL_FIELDS = [
    "phase_name",
    "phase_arrival_time",
    "phase_name_prob",
    "phase_name_snr",
    "polarity_type",
    "polarity_clarity",
    "phase_annotation_method",
    "polarity_annotation_method",
    "user_defined",
]

ALIASES: Dict[str, Sequence[str]] = {
    "event_id": ("event_id", "evid", "ev_id", "id", "source_id", "quake_id"),
    "source_type": ("source_type", "event_type", "type", "etype"),
    "source_origintime": ("source_origintime", "event_time", "origin_time", "origintime", "time", "ot"),
    "source_longitude_deg": ("source_longitude_deg", "longitude", "lon", "evlo"),
    "source_latitude_deg": ("source_latitude_deg", "latitude", "lat", "evla"),
    "source_depth_km": ("source_depth_km", "depth_km", "depth", "evdp"),
    "source_magnitude": ("source_magnitude", "magnitude", "mag", "ml", "mw", "mb", "md"),
    "source_magnitude_type": ("source_magnitude_type", "magnitude_type", "mag_type", "mtype"),
    "source_agency": ("source_agency", "source", "agency", "catalog"),
    "station_id": ("station_id", "stid", "seed_id"),
    "station_network": ("station_network", "network", "net"),
    "station_station": ("station_station", "station", "sta"),
    "station_location": ("station_location", "location", "loc"),
    "station_channel_list": ("station_channel_list", "channels", "channel_hint", "component"),
    "station_longitude_deg": ("station_longitude_deg", "station_longitude", "station_lon", "stlo"),
    "station_latitude_deg": ("station_latitude_deg", "station_latitude", "station_lat", "stla"),
    "station_elevation_m": ("station_elevation_m", "elevation_m", "elevation", "stel", "elev_m"),
    "station_depth_m": ("station_depth_m", "local_depth_m", "depth_m"),
    "phase_name": ("phase_name", "phase", "phase_type", "type"),
    "phase_arrival_time": ("phase_arrival_time", "pick_time", "arrival_time", "phase_time", "time"),
    "phase_name_prob": ("phase_name_prob", "score", "probability", "confidence", "phase_score"),
    "phase_name_snr": ("phase_name_snr", "snr", "phase_snr"),
    "polarity_type": ("polarity_type", "polarity", "updown", "first_motion"),
    "polarity_clarity": ("polarity_clarity", "clarity", "quality", "onset"),
    "phase_annotation_method": ("phase_annotation_method", "status", "method", "picker", "source"),
}


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def import_required(module_name: str, install_hint: str = ""):
    try:
        return __import__(module_name)
    except ImportError as exc:
        hint = install_hint or f"Install it with: python -m pip install {module_name}"
        raise SystemExit(f"Missing required Python module '{module_name}'. {hint}") from exc


def now_utc_date() -> str:
    return _dt.datetime.now(_dt.timezone.utc).date().isoformat()


def normalize_location(value: Any, default: str = DEFAULT_LOCATION) -> str:
    if value is None:
        return default
    text = str(value).strip()
    if text in {"", "--", "None", "none", "null", "NULL"}:
        return default
    return text


def split_station_id(station_id: str, default_location: str = DEFAULT_LOCATION) -> Tuple[str, str, str]:
    parts = str(station_id or "").split(".")
    network = parts[0] if len(parts) > 0 else ""
    station = parts[1] if len(parts) > 1 else ""
    location = parts[2] if len(parts) > 2 else default_location
    return network, station, normalize_location(location, default_location)


def make_station_id(network: Any, station: Any, location: Any = DEFAULT_LOCATION) -> str:
    return ".".join([
        str(network or "").strip(),
        str(station or "").strip(),
        normalize_location(location),
    ])


def station_key(station_id: str) -> str:
    network, station, _ = split_station_id(station_id)
    return f"{network}.{station}"


def parse_float(value: Any, default: float = math.nan) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.lower() in {"", "none", "null", "nan"}:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def parse_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        text = str(value).strip()
        if not text:
            return default
        return int(float(text))
    except Exception:
        return default


def listify(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                loaded = json.loads(text)
                return loaded if isinstance(loaded, list) else [loaded]
            except Exception:
                pass
        if "," in text:
            return [x.strip() for x in text.split(",") if x.strip()]
    return [value]


def clean_time_string(value: Any) -> str:
    if value is None:
        return "none"
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat().replace("+00:00", "Z")
        except Exception:
            pass
    text = str(value).strip()
    if not text:
        return "none"
    text = text.replace("/", "-")
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    if text.endswith("Z"):
        return text
    if re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", text):
        return text
    return text


def canonical_pick_method(value: Any, automatic_default: str = "automatic_unknown") -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "null"}:
        return "manual_unknown"
    lowered = text.lower()
    if lowered.startswith(("manual_", "automatic_")):
        return text
    if lowered in {"manual", "human", "reviewed"}:
        return "manual_unknown"
    if lowered in {"automatic", "auto"}:
        return automatic_default
    return f"manual_{text}" if lowered in {"m", "man"} else text


def pick_value(row: Dict[str, Any], field: str, mapping: Optional[Dict[str, Any]] = None, default: Any = None) -> Any:
    candidates: List[str] = []
    if mapping and field in mapping:
        mapped = mapping[field]
        candidates.extend(mapped if isinstance(mapped, list) else [mapped])
    candidates.extend(ALIASES.get(field, (field,)))

    lower_lookup = {str(k).lower(): k for k in row.keys()}
    for candidate in candidates:
        if candidate in row:
            value = row[candidate]
        else:
            key = lower_lookup.get(str(candidate).lower())
            if key is None:
                continue
            value = row[key]
        if value is not None and str(value).strip() != "":
            return value
    return default


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def h5_attr_value(value: Any) -> Any:
    if value is None:
        return "none"
    if isinstance(value, (list, tuple, dict)):
        return safe_json(value)
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    return str(value)


def set_attrs(obj: Any, attrs: Dict[str, Any]) -> None:
    for key, value in attrs.items():
        obj.attrs[key] = h5_attr_value(value)


def stable_event_id(event_time: str, lat: Any, lon: Any, fallback: str) -> str:
    seed = "|".join([str(event_time), str(lat), str(lon), str(fallback)])
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def normalize_event_dict(raw: Dict[str, Any], mapping: Optional[Dict[str, Any]] = None, fallback_id: str = "event") -> Dict[str, Any]:
    event_time = clean_time_string(pick_value(raw, "source_origintime", mapping, "none"))
    lon = parse_float(pick_value(raw, "source_longitude_deg", mapping))
    lat = parse_float(pick_value(raw, "source_latitude_deg", mapping))
    event_id = str(pick_value(raw, "event_id", mapping, "") or "").strip()
    if not event_id:
        event_id = stable_event_id(event_time, lat, lon, fallback_id)

    mag_value = pick_value(raw, "source_magnitude", mapping, None)
    mag_type = pick_value(raw, "source_magnitude_type", mapping, None)

    event = {
        "type": "event",
        "event_id": event_id,
        "source_type": str(pick_value(raw, "source_type", mapping, "eq") or "eq"),
        "source_origintime": event_time,
        "source_origintime_err": parse_float(raw.get("source_origintime_err")),
        "source_origintime_ref": parse_float(raw.get("source_origintime_ref")),
        "time_standard": str(raw.get("time_standard", "UTC") or "UTC"),
        "source_longitude_deg": lon,
        "source_latitude_deg": lat,
        "source_depth_km": parse_float(pick_value(raw, "source_depth_km", mapping)),
        "source_magnitude_type": listify(mag_type) or ["none"],
        "source_magnitude": [parse_float(x) for x in (listify(mag_value) or [math.nan])],
        "source_magnitude_error": listify(raw.get("source_magnitude_error")),
        "preferred_magnitude_type": str(raw.get("preferred_magnitude_type") or (listify(mag_type) or ["none"])[0]),
        "source_area": str(raw.get("source_area", "none") or "none"),
        "source_agency": str(pick_value(raw, "source_agency", mapping, "none") or "none"),
        "location_method": str(raw.get("location_method", "none") or "none"),
        "velocity_model_id": str(raw.get("velocity_model_id", "none") or "none"),
        "num_phases_used": parse_int(raw.get("num_phases_used"), 0),
        "num_stations_used": parse_int(raw.get("num_stations_used"), 0),
        "max_azimuthal_gap_deg": parse_float(raw.get("max_azimuthal_gap_deg")),
        "station_azimuth_uniformity": parse_float(raw.get("station_azimuth_uniformity")),
        "min_epicentral_dist_km": parse_float(raw.get("min_epicentral_dist_km")),
        "max_epicentral_dist_km": parse_float(raw.get("max_epicentral_dist_km")),
        "horizontal_uncertainty_major_km": parse_float(raw.get("horizontal_uncertainty_major_km")),
        "horizontal_uncertainty_minor_km": parse_float(raw.get("horizontal_uncertainty_minor_km")),
        "horizontal_uncertainty_azimuth": parse_float(raw.get("horizontal_uncertainty_azimuth")),
        "vertical_uncertainty_km": parse_float(raw.get("vertical_uncertainty_km")),
        "residual_mean_sec": parse_float(raw.get("residual_mean_sec")),
        "location_rms_sec": parse_float(raw.get("location_rms_sec")),
        "event_status": str(raw.get("event_status", "none") or "none"),
        "updated_time": clean_time_string(raw.get("updated_time", "none")),
        "source_moment": listify(raw.get("source_moment")),
        "source_fault_plane": listify(raw.get("source_fault_plane")),
        "source_fault_plane_err": listify(raw.get("source_fault_plane_err")),
        "event_remark": str(raw.get("event_remark", "none") or "none"),
        "stations": [],
    }
    return event


def normalize_station_dict(raw: Dict[str, Any], mapping: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    station_id = str(pick_value(raw, "station_id", mapping, "") or "").strip()
    network = pick_value(raw, "station_network", mapping, None)
    station = pick_value(raw, "station_station", mapping, None)
    location = pick_value(raw, "station_location", mapping, DEFAULT_LOCATION)
    if not station_id and network and station:
        station_id = make_station_id(network, station, location)
    if station_id:
        network, station, location = split_station_id(station_id)
    station_id = station_id or make_station_id(network or "", station or "", location)

    channels = listify(pick_value(raw, "station_channel_list", mapping, []))
    channels = [str(x).strip() for x in channels if str(x).strip()]

    return {
        "type": "station",
        "station_id": station_id,
        "station_network": str(network or ""),
        "station_station": str(station or ""),
        "station_location": normalize_location(location),
        "station_channel_list": channels,
        "station_longitude_deg": parse_float(pick_value(raw, "station_longitude_deg", mapping)),
        "station_latitude_deg": parse_float(pick_value(raw, "station_latitude_deg", mapping)),
        "station_elevation_m": parse_float(pick_value(raw, "station_elevation_m", mapping)),
        "station_depth_m": parse_float(pick_value(raw, "station_depth_m", mapping), 0.0),
        "station_area": str(raw.get("station_area", "none") or "none"),
        "station_agency": str(raw.get("station_agency", "none") or "none"),
        "station_remark": str(raw.get("station_remark", "none") or "none"),
        "picks": [],
    }


def normalize_pick_dict(raw: Dict[str, Any], mapping: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    method = canonical_pick_method(pick_value(raw, "phase_annotation_method", mapping, raw.get("status")))
    polarity_method = canonical_pick_method(raw.get("polarity_annotation_method", method))
    user_defined = {
        k: v
        for k, v in raw.items()
        if k not in set(sum((list(v) for v in ALIASES.values()), [])) and k not in LABEL_FIELDS
    }
    return {
        "type": "label",
        "phase_name": str(pick_value(raw, "phase_name", mapping, "none") or "none"),
        "phase_arrival_time": clean_time_string(pick_value(raw, "phase_arrival_time", mapping, "none")),
        "phase_name_prob": parse_float(pick_value(raw, "phase_name_prob", mapping)),
        "phase_name_snr": parse_float(pick_value(raw, "phase_name_snr", mapping)),
        "polarity_type": str(pick_value(raw, "polarity_type", mapping, "none") or "none"),
        "polarity_clarity": str(pick_value(raw, "polarity_clarity", mapping, "none") or "none"),
        "phase_annotation_method": method,
        "polarity_annotation_method": polarity_method,
        "user_defined": raw.get("user_defined", user_defined),
    }


def canonical_from_mini_annotations(obj: Dict[str, Any]) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    for year in obj.get("years", {}).values():
        for day in year.get("days", {}).values():
            for event_id, event_node in day.get("events", {}).items():
                raw_event = dict(event_node.get("event", {}))
                raw_event.setdefault("event_id", event_node.get("event_id", event_id))
                event = normalize_event_dict(raw_event, fallback_id=str(event_id))
                preferred_origin = event_node.get("preferred_origin", {}) or {}
                preferred_magnitude = event_node.get("preferred_magnitude", {}) or {}
                if preferred_origin:
                    event["source_origintime"] = clean_time_string(preferred_origin.get("time", event["source_origintime"]))
                    event["source_longitude_deg"] = parse_float(preferred_origin.get("longitude"), event["source_longitude_deg"])
                    event["source_latitude_deg"] = parse_float(preferred_origin.get("latitude"), event["source_latitude_deg"])
                    event["source_depth_km"] = parse_float(preferred_origin.get("depth_m"), math.nan) / 1000.0
                if preferred_magnitude:
                    event["source_magnitude"] = [parse_float(preferred_magnitude.get("mag"))]
                    event["source_magnitude_type"] = [str(preferred_magnitude.get("magnitude_type", "none"))]
                    event["preferred_magnitude_type"] = str(preferred_magnitude.get("magnitude_type", "none"))

                for station_node in event_node.get("stations", {}).values():
                    raw_station = dict(station_node.get("station_metadata", {}))
                    raw_station.setdefault("station_id", station_node.get("station_id"))
                    raw_station.setdefault("network", station_node.get("network"))
                    raw_station.setdefault("station", station_node.get("station"))
                    raw_station.setdefault("location", station_node.get("location"))
                    raw_station.setdefault("station_latitude", raw_station.get("latitude"))
                    raw_station.setdefault("station_longitude", raw_station.get("longitude"))
                    raw_station.setdefault("elevation_m", raw_station.get("elevation"))
                    raw_station.setdefault("station_channel_list", raw_station.get("component"))
                    station = normalize_station_dict(raw_station)
                    for pick in station_node.get("picks", []):
                        station["picks"].append(normalize_pick_dict(pick))
                    if not station["station_channel_list"]:
                        for rec in station_node.get("records", []):
                            station["station_channel_list"].extend(listify(rec.get("component")))
                    station["station_channel_list"] = sorted(set(station["station_channel_list"]))
                    event["stations"].append(station)
                events.append(event)

    return {
        "format": CANONICAL_FORMAT,
        "events": events,
        "metadata": {
            "source_format": obj.get("format", "annotations_mini_like"),
            "warnings": [],
        },
    }


def canonical_from_flat_rows(rows: Sequence[Dict[str, Any]], mapping: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    events_by_id: Dict[str, Dict[str, Any]] = {}
    stations_by_event: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)

    for idx, row in enumerate(rows):
        event = normalize_event_dict(row, mapping, fallback_id=f"row-{idx}")
        event_id = event["event_id"]
        if event_id not in events_by_id:
            events_by_id[event_id] = event

        station = normalize_station_dict(row, mapping)
        station_id = station["station_id"]
        if station_id not in stations_by_event[event_id]:
            stations_by_event[event_id][station_id] = station

        has_pick = any(pick_value(row, field, mapping, None) not in (None, "") for field in ("phase_name", "phase_arrival_time"))
        if has_pick:
            stations_by_event[event_id][station_id]["picks"].append(normalize_pick_dict(row, mapping))

    for event_id, event in events_by_id.items():
        event["stations"] = list(stations_by_event[event_id].values())
        event["num_stations_used"] = len(event["stations"])
        event["num_phases_used"] = sum(len(st.get("picks", [])) for st in event["stations"])

    return {
        "format": CANONICAL_FORMAT,
        "events": list(events_by_id.values()),
        "metadata": {"source_format": "flat_rows", "warnings": []},
    }


def iter_dicts(obj: Any) -> Iterator[Dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_dicts(item)


def looks_like_flat_pick(row: Dict[str, Any]) -> bool:
    keys = {str(k).lower() for k in row.keys()}
    return bool(keys.intersection({"phase", "phase_name", "pick_time", "arrival_time"})) and bool(
        keys.intersection({"event_id", "evid", "origin_time", "event_time", "source_origintime"})
    )


def canonical_from_json(obj: Any, mapping: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if isinstance(obj, dict) and obj.get("format") == CANONICAL_FORMAT:
        return obj
    if isinstance(obj, dict) and "years" in obj:
        return canonical_from_mini_annotations(obj)
    if isinstance(obj, dict) and isinstance(obj.get("events"), list):
        events = []
        for idx, item in enumerate(obj["events"]):
            event = normalize_event_dict(item, mapping, fallback_id=f"event-{idx}")
            stations = item.get("stations", [])
            if isinstance(stations, dict):
                stations = list(stations.values())
            for st_idx, station_item in enumerate(stations or []):
                station = normalize_station_dict(station_item, mapping)
                picks = station_item.get("picks", [])
                station["picks"] = [normalize_pick_dict(p, mapping) for p in picks if isinstance(p, dict)]
                event["stations"].append(station)
            events.append(event)
        return {"format": CANONICAL_FORMAT, "events": events, "metadata": {"source_format": "events_list", "warnings": []}}
    if isinstance(obj, list) and all(isinstance(x, dict) for x in obj):
        return canonical_from_flat_rows(obj, mapping)

    rows = [d for d in iter_dicts(obj) if looks_like_flat_pick(d)]
    if rows:
        return canonical_from_flat_rows(rows, mapping)
    raise SystemExit("Could not infer catalog JSON shape. Provide --mapping or convert to canonical JSON.")


def parse_delimited_catalog(path: Path, mapping: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;| ")
    except csv.Error:
        dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, dialect=dialect)
        rows = [dict(row) for row in reader]
    return canonical_from_flat_rows(rows, mapping)


def parse_cea_time(tokens: Sequence[str], year_idx: int, month_idx: int, day_idx: int, hour_idx: int, minute_idx: int, second_idx: int, micro_idx: int) -> str:
    try:
        second = str(tokens[second_idx]).zfill(2)
        micro = str(tokens[micro_idx]).ljust(6, "0")[:6]
        text = (
            f"{tokens[year_idx]}-{str(tokens[month_idx]).zfill(2)}-{str(tokens[day_idx]).zfill(2)}T"
            f"{str(tokens[hour_idx]).zfill(2)}:{str(tokens[minute_idx]).zfill(2)}:{second}.{micro}Z"
        )
        return text
    except Exception:
        return "none"


def parse_cea_phase_catalog(path: Path) -> Dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    events: List[Dict[str, Any]] = []
    for block_index, block in enumerate(content.split("#")):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        head = [x for x in lines[0].split() if x]
        if len(head) < 19:
            continue
        event_raw = {
            "event_id": head[1],
            "source_type": head[2],
            "source_origintime": parse_cea_time(head, 3, 4, 5, 7, 8, 9, 10),
            "source_longitude_deg": head[12],
            "source_latitude_deg": head[13],
            "source_depth_km": -1 if head[15] == "NONE" else head[15],
            "source_magnitude": head[18],
            "source_magnitude_type": "none",
            "event_remark": ",".join(head),
        }
        event = normalize_event_dict(event_raw, fallback_id=f"cea-{block_index}")
        stations: Dict[str, Dict[str, Any]] = {}
        for line in lines[1:]:
            parts = [x for x in line.split() if x]
            if len(parts) < 20 or parts[0].upper() != "PHASE":
                continue
            network = parts[4] if len(parts) > 4 else ""
            station_code = parts[5] if len(parts) > 5 else ""
            location = parts[6] if len(parts) > 6 else DEFAULT_LOCATION
            channel = parts[7] if len(parts) > 7 else ""
            station_id = make_station_id(network, station_code, location)
            if station_id not in stations:
                stations[station_id] = normalize_station_dict(
                    {
                        "station_id": station_id,
                        "station_channel_list": channel,
                    }
                )
            phase_time = event["source_origintime"]
            if len(parts) > 19 and parts[12] != "YYYY":
                phase_time = parse_cea_time(parts, 12, 13, 14, 16, 17, 18, 19)
            pick = normalize_pick_dict(
                {
                    "phase": parts[8] if len(parts) > 8 else "none",
                    "pick_time": phase_time,
                    "status": parts[3] if len(parts) > 3 else "manual_unknown",
                    "polarity": parts[27] if len(parts) > 27 and parts[3] == "POLARITY" else "none",
                    "clarity": parts[28] if len(parts) > 28 and parts[3] == "POLARITY" else "none",
                    "distaz": parts[24] if len(parts) > 24 else None,
                    "raw": ",".join(parts),
                }
            )
            stations[station_id]["picks"].append(pick)
        event["stations"] = list(stations.values())
        event["num_stations_used"] = len(event["stations"])
        event["num_phases_used"] = sum(len(st.get("picks", [])) for st in event["stations"])
        events.append(event)
    return {"format": CANONICAL_FORMAT, "events": events, "metadata": {"source_format": "cea_phase_text", "warnings": []}}


def load_mapping(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize_catalog(path: Path, mapping: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in {".json", ".geojson"}:
        return canonical_from_json(json.loads(path.read_text(encoding="utf-8")), mapping)
    if suffix == ".jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return canonical_from_flat_rows(rows, mapping)
    if suffix in {".csv", ".tsv"}:
        return parse_delimited_catalog(path, mapping)
    return parse_cea_phase_catalog(path)


def resolve_files(input_value: str, suffixes: Optional[Iterable[str]] = None, recursive: bool = True) -> List[Path]:
    p = Path(input_value)
    suffix_set = {s.lower() for s in suffixes} if suffixes else None
    if p.is_file():
        return [p]
    if p.is_dir():
        pattern = "**/*" if recursive else "*"
        files = [x for x in p.glob(pattern) if x.is_file()]
    else:
        files = [Path(x) for x in sorted(glob.glob(input_value, recursive=recursive))]
    if suffix_set:
        files = [x for x in files if x.suffix.lower() in suffix_set]
    return sorted(files)


def mseedindex_binary() -> Path:
    exe_name = "mseedindex.exe" if platform.system().lower().startswith("win") else "mseedindex"
    return MSEEDINDEX_DIR / exe_name


def run(cmd: Sequence[str], cwd: Optional[Path] = None) -> None:
    print("[RUN]", " ".join(str(x) for x in cmd))
    subprocess.run([str(x) for x in cmd], cwd=str(cwd) if cwd else None, check=True)


def ensure_mseedindex(no_build: bool = False, force_clone: bool = False) -> Path:
    if force_clone and MSEEDINDEX_DIR.exists():
        shutil.rmtree(MSEEDINDEX_DIR)
    if not MSEEDINDEX_DIR.exists():
        MSEEDINDEX_DIR.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--depth", "1", MSEEDINDEX_REPO, str(MSEEDINDEX_DIR)])
        git_dir = MSEEDINDEX_DIR / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir)

    binary = mseedindex_binary()
    if no_build:
        return binary
    if binary.exists():
        return binary

    make = shutil.which("make") or shutil.which("gmake")
    if not make:
        raise SystemExit("No make/gmake found. Install build tools or build assets/mseedindex manually.")
    run([make], cwd=MSEEDINDEX_DIR)
    if not binary.exists():
        raise SystemExit(f"mseedindex build finished but binary was not found at {binary}")
    return binary


def cmd_install_mseedindex(args: argparse.Namespace) -> None:
    binary = ensure_mseedindex(no_build=args.no_build, force_clone=args.force_clone)
    print(f"mseedindex source: {MSEEDINDEX_DIR}")
    print(f"mseedindex binary: {binary}")
    if binary.exists():
        subprocess.run([str(binary), "-V"], check=False)


def cmd_check_deps(args: argparse.Namespace) -> None:
    modules = ["numpy", "h5py", "obspy"]
    if args.include_torch:
        modules.append("torch")
    for module in modules:
        try:
            imported = __import__(module)
            print(f"[OK] {module}: {getattr(imported, '__version__', 'available')}")
        except Exception as exc:
            print(f"[MISSING] {module}: {exc}")
    binary = mseedindex_binary()
    print(f"[{'OK' if binary.exists() else 'MISSING'}] mseedindex binary: {binary}")


def cmd_convert_waveforms(args: argparse.Namespace) -> None:
    obspy = import_required("obspy", "Install with: python -m pip install obspy")
    read = obspy.read
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffixes = None if args.all_files else {x.lower() for x in args.suffixes.split(",") if x.strip()}
    files = resolve_files(args.input, suffixes=suffixes, recursive=args.recursive)
    if not files:
        raise SystemExit(f"No input waveform files found from {args.input}")
    written = 0
    for index, file_path in enumerate(files, start=1):
        try:
            stream = read(str(file_path), format=args.obspy_format) if args.obspy_format else read(str(file_path))
            if args.merge:
                fill_value = None if args.fill_value.lower() == "none" else float(args.fill_value)
                stream.merge(method=1, fill_value=fill_value)
            safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", file_path.stem)
            out_path = output_dir / f"{safe_stem}.mseed"
            if out_path.exists() and not args.overwrite:
                out_path = output_dir / f"{safe_stem}.{index}.mseed"
            stream.write(str(out_path), format="MSEED")
            written += 1
            print(f"[OK] {file_path} -> {out_path} ({len(stream)} trace(s))")
        except Exception as exc:
            message = f"[WARN] Failed to convert {file_path}: {exc}"
            if args.strict:
                raise SystemExit(message) from exc
            print(message)
    print(f"[OK] Converted {written}/{len(files)} files to miniSEED")


def cmd_index_mseed(args: argparse.Namespace) -> None:
    binary = ensure_mseedindex(no_build=False)
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if args.reset and db_path.exists():
        db_path.unlink()
    files = resolve_files(args.input, suffixes={".mseed", ".msd", ".miniseed", ".seed"}, recursive=args.recursive)
    if not files:
        raise SystemExit(f"No miniSEED files found from {args.input}")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
        list_file = Path(fh.name)
        for file_path in files:
            fh.write(str(file_path.resolve() if not args.keep_paths else file_path) + "\n")
    try:
        cmd = [str(binary), "-sqlite", str(db_path)]
        if args.skip_non_data:
            cmd.append("-snd")
        if args.keep_paths:
            cmd.append("-kp")
        if args.no_updates:
            cmd.append("-noup")
        cmd.append(f"@{list_file}")
        run(cmd)
    finally:
        list_file.unlink(missing_ok=True)
    print(f"[OK] Indexed {len(files)} miniSEED file(s) into {db_path}")


def wildcard_to_sql(pattern: str) -> str:
    return str(pattern or "*").replace("*", "%").replace("?", "_")


def obspy_utc(value: Any):
    obspy = import_required("obspy", "Install with: python -m pip install obspy")
    return obspy.UTCDateTime(value)


def sql_time(value: Any) -> str:
    text = str(obspy_utc(value))
    return text[:-1] if text.endswith("Z") else text


def query_tsindex_rows(db_path: str, network: str, station: str, location: str, channel: str, starttime: Any, endtime: Any, limit: Optional[int] = None) -> List[sqlite3.Row]:
    sql = """
    SELECT *
    FROM tsindex
    WHERE network LIKE ?
      AND station LIKE ?
      AND location LIKE ?
      AND channel LIKE ?
      AND endtime >= ?
      AND starttime <= ?
    ORDER BY network, station, location, channel, starttime
    """
    params: List[Any] = [
        wildcard_to_sql(network),
        wildcard_to_sql(station),
        wildcard_to_sql(location),
        wildcard_to_sql(channel),
        sql_time(starttime),
        sql_time(endtime),
    ]
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return list(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def read_stream_from_tsindex_rows(rows: Sequence[sqlite3.Row], starttime: Any, endtime: Any):
    obspy = import_required("obspy", "Install with: python -m pip install obspy")
    read = obspy.read
    Stream = obspy.Stream
    start = obspy.UTCDateTime(starttime)
    end = obspy.UTCDateTime(endtime)
    out = Stream()
    seen: set = set()
    for row in rows:
        filename = row["filename"]
        key = (filename, row["network"], row["station"], row["location"], row["channel"])
        if key in seen:
            continue
        seen.add(key)
        try:
            stream = read(filename)
        except Exception as exc:
            print(f"[WARN] Could not read indexed file {filename}: {exc}")
            continue
        for trace in stream:
            stats = trace.stats
            if str(stats.network) != str(row["network"]):
                continue
            if str(stats.station) != str(row["station"]):
                continue
            if normalize_location(stats.location) != normalize_location(row["location"]):
                continue
            if str(stats.channel) != str(row["channel"]):
                continue
            if trace.stats.endtime < start or trace.stats.starttime > end:
                continue
            tr = trace.copy()
            tr.trim(start, end, pad=False)
            tr.stats.seismicx_source_file = filename
            out += tr
    return out


def cmd_query_mseed(args: argparse.Namespace) -> None:
    rows = query_tsindex_rows(args.db, args.network, args.station, args.location, args.channel, args.starttime, args.endtime, args.limit)
    print(f"[OK] Matched {len(rows)} tsindex row(s)")
    for row in rows[: args.preview]:
        print(
            f"{row['network']}.{row['station']}.{normalize_location(row['location'])}.{row['channel']} "
            f"{row['starttime']} {row['endtime']} {row['samplerate']}Hz {row['filename']}"
        )
    if args.output:
        stream = read_stream_from_tsindex_rows(rows, args.starttime, args.endtime)
        stream.write(args.output, format="MSEED")
        print(f"[OK] Wrote {len(stream)} trace(s) to {args.output}")


def cmd_normalize_labels(args: argparse.Namespace) -> None:
    mapping = load_mapping(args.mapping)
    canonical = normalize_catalog(Path(args.input), mapping)
    canonical.setdefault("metadata", {})
    canonical["metadata"]["source_file"] = str(Path(args.input))
    canonical["metadata"]["normalized_time"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(canonical, ensure_ascii=False, indent=2), encoding="utf-8")
    n_events = len(canonical.get("events", []))
    n_stations = sum(len(e.get("stations", [])) for e in canonical.get("events", []))
    n_picks = sum(len(st.get("picks", [])) for e in canonical.get("events", []) for st in e.get("stations", []))
    print(f"[OK] Wrote canonical labels to {args.output}: events={n_events}, stations={n_stations}, picks={n_picks}")


def load_station_csv(path: Optional[str]) -> Dict[str, Dict[str, Any]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        has_header = any(name in sample.lower().splitlines()[0] for name in ("net", "network", "sta", "station"))
        if has_header:
            reader = csv.DictReader(fh)
            rows = [dict(row) for row in reader]
        else:
            rows = []
            for row in csv.reader(fh):
                if len(row) >= 5:
                    rows.append(
                        {
                            "network": row[0],
                            "station": row[1],
                            "station_latitude": row[2],
                            "station_longitude": row[3],
                            "elevation_m": row[4],
                            "start": row[5] if len(row) > 5 else "",
                            "end": row[6] if len(row) > 6 else "",
                        }
                    )
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        station = normalize_station_dict(row)
        out[station["station_id"]] = station
        out[station_key(station["station_id"])] = station
    return out


def init_h5_file(h5: Any, args: argparse.Namespace, mode: str) -> Tuple[Any, Any]:
    set_attrs(
        h5,
        {
            "type": "hdf5_file",
            "format": HDF5_FORMAT,
            "dataset_mode": mode,
            "name": args.name,
            "version": args.version,
            "license": "LICENSE",
            "md5": "md5sum.txt",
            "processing_time": now_utc_date(),
            "agency": listify(args.agency),
            "author": listify(args.author),
            "num_stations": 0,
            "num_events": 0,
            "annotation_types": [],
            "annotation_counts": [],
            "description": args.description,
            "file_size": "none",
        },
    )
    info = h5.require_group("information")
    set_attrs(info, {"type": "information"})
    data = h5.require_group("data")
    set_attrs(data, {"type": "data"})
    return info, data


def sample_attrs_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    attrs = {field: event.get(field) for field in EVENT_FIELDS}
    attrs["type"] = "event"
    return attrs


def continuous_sample_attrs(sample_id: str, starttime: str, endtime: str) -> Dict[str, Any]:
    return {
        "type": "event",
        "event_id": sample_id,
        "source_type": "cont",
        "source_origintime": starttime,
        "source_origintime_err": math.nan,
        "source_origintime_ref": math.nan,
        "time_standard": "UTC",
        "source_longitude_deg": math.nan,
        "source_latitude_deg": math.nan,
        "source_depth_km": math.nan,
        "source_magnitude_type": ["none"],
        "source_magnitude": [math.nan],
        "source_magnitude_error": [],
        "preferred_magnitude_type": "none",
        "source_area": "none",
        "source_agency": "none",
        "location_method": "none",
        "velocity_model_id": "none",
        "num_phases_used": 0,
        "num_stations_used": 0,
        "max_azimuthal_gap_deg": math.nan,
        "station_azimuth_uniformity": math.nan,
        "min_epicentral_dist_km": math.nan,
        "max_epicentral_dist_km": math.nan,
        "horizontal_uncertainty_major_km": math.nan,
        "horizontal_uncertainty_minor_km": math.nan,
        "horizontal_uncertainty_azimuth": math.nan,
        "vertical_uncertainty_km": math.nan,
        "residual_mean_sec": math.nan,
        "location_rms_sec": math.nan,
        "event_status": "none",
        "updated_time": "none",
        "source_moment": [],
        "source_fault_plane": [],
        "source_fault_plane_err": [],
        "event_remark": f"continuous window {starttime} to {endtime}",
    }


def ensure_information_station(info_group: Any, station: Dict[str, Any], channel: Optional[str] = None) -> Any:
    station = dict(station)
    if channel:
        channels = set(str(x) for x in station.get("station_channel_list", []))
        channels.add(str(channel))
        station["station_channel_list"] = sorted(channels)
    group = info_group.require_group(station["station_id"])
    attrs = {field: station.get(field) for field in STATION_FIELDS}
    attrs["type"] = "station"
    set_attrs(group, attrs)
    return group


def ensure_sample_station(sample_group: Any, station: Dict[str, Any]) -> Any:
    group = sample_group.require_group(station["station_id"])
    attrs = {field: station.get(field) for field in STATION_FIELDS}
    attrs["type"] = "station"
    set_attrs(group, attrs)
    return group


def next_segment_id(channel_group: Any) -> int:
    ids = [int(k) for k in channel_group.keys() if str(k).isdigit()]
    return (max(ids) + 1) if ids else 0


def update_channel_attrs(channel_group: Any, channel: str, start: str, end: str) -> None:
    old_count = parse_int(channel_group.attrs.get("num_of_seg"), 0)
    starts = [str(channel_group.attrs.get("start_time", "")), start]
    ends = [str(channel_group.attrs.get("end_time", "")), end]
    starts = [x for x in starts if x and x != "none"]
    ends = [x for x in ends if x and x != "none"]
    set_attrs(
        channel_group,
        {
            "type": "channel",
            "station_channel_id": channel,
            "num_of_seg": old_count + 1,
            "start_time": min(starts) if starts else start,
            "end_time": max(ends) if ends else end,
            "continuity_rate": math.nan,
            "orientation": [],
            "user_defined": {},
        },
    )


def create_trace_dataset(
    station_group: Any,
    data: Any,
    network: str,
    station: str,
    location: str,
    channel: str,
    sample_rate: float,
    start: str,
    end: str,
    unit: str,
    source_file: str,
    compression: str,
    compression_opts: int,
) -> Any:
    waveform = station_group.require_group("waveform")
    set_attrs(waveform, {"type": "waveform"})
    channel_group = waveform.require_group(str(channel))
    seg_id = next_segment_id(channel_group)
    update_channel_attrs(channel_group, str(channel), start, end)

    kwargs: Dict[str, Any] = {}
    if compression and compression != "none":
        kwargs["compression"] = compression
        if compression == "gzip":
            kwargs["compression_opts"] = compression_opts
        kwargs["shuffle"] = True
    ds = channel_group.create_dataset(str(seg_id), data=data, **kwargs)
    set_attrs(
        ds,
        {
            "type": "trace",
            "seg_id": seg_id,
            "unit": unit,
            "sample_rate": float(sample_rate),
            "seg_start_time": start,
            "seg_end_time": end,
            "quality_flag": "D",
            "quality_metric": 0,
            "quality_metric_description": "none",
            "network": network,
            "station": station,
            "location": normalize_location(location),
            "channel": channel,
            "starttime": start,
            "endtime": end,
            "sampling_rate": float(sample_rate),
            "npts": int(len(data)),
            "dtype": str(getattr(data, "dtype", "")),
            "source_file": source_file,
        },
    )
    return ds


def write_label_group(station_group: Any, picks: Sequence[Dict[str, Any]]) -> None:
    h5py = import_required("h5py", "Install with: python -m pip install h5py")
    np = import_required("numpy", "Install with: python -m pip install numpy")
    label = station_group.require_group("label")
    set_attrs(label, {"type": "label", "num_labels": len(picks)})
    string_dtype = h5py.string_dtype(encoding="utf-8")
    for field in LABEL_FIELDS:
        if field in label:
            del label[field]
        values = [pick.get(field) for pick in picks]
        if field in {"phase_name_prob", "phase_name_snr"}:
            data = np.asarray([parse_float(x) for x in values], dtype="float64")
            ds = label.create_dataset(field, data=data)
        else:
            if field == "user_defined":
                values = [safe_json(v if v is not None else {}) for v in values]
            else:
                values = [str(v if v not in (None, "") else "none") for v in values]
            ds = label.create_dataset(field, data=np.asarray(values, dtype=object), dtype=string_dtype)
        set_attrs(ds, {"type": "label", "field_name": field})


def floor_utc_to_interval(t: Any, interval_seconds: Optional[int]):
    if interval_seconds is None:
        return t
    epoch = float(t.timestamp)
    return type(t)(int(epoch // interval_seconds) * interval_seconds)


def split_trace_indices(trace: Any, interval_seconds: Optional[int]) -> Iterator[Tuple[int, int, Any, Any]]:
    npts = int(trace.stats.npts)
    if npts <= 0:
        return
    sr = float(trace.stats.sampling_rate)
    if interval_seconds is None:
        yield 0, npts, trace.stats.starttime, trace.stats.endtime
        return
    idx = 0
    while idx < npts:
        sample_time = trace.stats.starttime + idx / sr
        interval_start = floor_utc_to_interval(sample_time, interval_seconds)
        next_boundary = interval_start + int(interval_seconds)
        idx_end = int(math.ceil((float(next_boundary - trace.stats.starttime) * sr) - 1e-9))
        idx_end = max(idx + 1, min(idx_end, npts))
        seg_start = trace.stats.starttime + idx / sr
        seg_end = trace.stats.starttime + (idx_end - 1) / sr
        yield idx, idx_end, seg_start, seg_end
        idx = idx_end


def sample_id_from_time(prefix: str, t: Any, interval_seconds: Optional[int]) -> str:
    if interval_seconds is None:
        return f"{prefix}_single"
    start = floor_utc_to_interval(t, interval_seconds)
    if interval_seconds == 3600:
        return f"{prefix}_{start.year:04d}{start.month:02d}{start.day:02d}_{start.hour:02d}"
    if interval_seconds == 86400:
        return f"{prefix}_{start.year:04d}{start.month:02d}{start.day:02d}"
    return f"{prefix}_{start.year:04d}{start.month:02d}{start.day:02d}T{start.hour:02d}{start.minute:02d}{start.second:02d}_{interval_seconds}s"


def interval_seconds_from_arg(value: str, custom: int) -> Optional[int]:
    if value == "single":
        return None
    if value == "hour":
        return 3600
    if value == "day":
        return 86400
    if value == "custom":
        if custom <= 0:
            raise SystemExit("--custom-interval-seconds must be positive")
        return int(custom)
    raise SystemExit(f"Unsupported split interval: {value}")


def cmd_make_hdf5_continuous(args: argparse.Namespace) -> None:
    obspy = import_required("obspy", "Install with: python -m pip install obspy")
    h5py = import_required("h5py", "Install with: python -m pip install h5py")
    np = import_required("numpy", "Install with: python -m pip install numpy")
    station_lookup = load_station_csv(args.station_csv)
    files = resolve_files(args.waveform_input, suffixes=None if args.all_files else WAVEFORM_SUFFIXES, recursive=True)
    if not files:
        raise SystemExit(f"No waveform files found from {args.waveform_input}")
    interval_seconds = interval_seconds_from_arg(args.split_interval, args.custom_interval_seconds)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    station_ids: set = set()

    with h5py.File(output, "w") as h5:
        info, data_group = init_h5_file(h5, args, "continuous")
        for file_index, file_path in enumerate(files, start=1):
            try:
                stream = obspy.read(str(file_path))
            except Exception as exc:
                print(f"[WARN] Could not read {file_path}: {exc}")
                continue
            for trace in stream:
                network = str(trace.stats.network or "")
                station_code = str(trace.stats.station or "")
                location = normalize_location(trace.stats.location)
                channel = str(trace.stats.channel or "")
                sid = make_station_id(network, station_code, location)
                station_meta = dict(station_lookup.get(sid) or station_lookup.get(station_key(sid)) or normalize_station_dict({"station_id": sid}))
                station_meta["station_channel_list"] = sorted(set(listify(station_meta.get("station_channel_list")) + [channel]))
                ensure_information_station(info, station_meta, channel)
                station_ids.add(sid)
                for idx0, idx1, seg_start, seg_end in split_trace_indices(trace, interval_seconds):
                    sample_id = sample_id_from_time("cont", seg_start, interval_seconds)
                    sample_group = data_group.require_group(sample_id)
                    if "type" not in sample_group.attrs:
                        set_attrs(sample_group, continuous_sample_attrs(sample_id, str(seg_start), str(seg_end)))
                    st_group = ensure_sample_station(sample_group, station_meta)
                    create_trace_dataset(
                        station_group=st_group,
                        data=np.asarray(trace.data[idx0:idx1]),
                        network=network,
                        station=station_code,
                        location=location,
                        channel=channel,
                        sample_rate=float(trace.stats.sampling_rate),
                        start=str(seg_start),
                        end=str(seg_end),
                        unit=args.unit,
                        source_file=str(file_path),
                        compression=args.compression,
                        compression_opts=args.compression_opts,
                    )
                    write_label_group(st_group, [])
            if file_index % 100 == 0 or file_index == len(files):
                print(f"[INFO] processed {file_index}/{len(files)} waveform files")
        h5.attrs["num_stations"] = len(station_ids)
        h5.attrs["num_events"] = len(data_group.keys())
        h5.attrs["file_size"] = "pending"
    write_sidecars(output, args.license_text)
    print(f"[OK] Continuous HDF5 written to {output}")


def cmd_make_hdf5_event(args: argparse.Namespace) -> None:
    h5py = import_required("h5py", "Install with: python -m pip install h5py")
    np = import_required("numpy", "Install with: python -m pip install numpy")
    catalog = normalize_catalog(Path(args.catalog), load_mapping(args.mapping))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    station_ids: set = set()
    phase_counter: Counter = Counter()

    with h5py.File(output, "w") as h5:
        info, data_group = init_h5_file(h5, args, "event")
        for event in catalog.get("events", []):
            event_id = str(event.get("event_id") or stable_event_id(event.get("source_origintime"), event.get("source_latitude_deg"), event.get("source_longitude_deg"), "event"))
            sample_group = data_group.require_group(event_id)
            set_attrs(sample_group, sample_attrs_from_event(event))
            stations = event.get("stations", [])
            for raw_station in stations:
                raw_picks = raw_station.get("picks", []) if isinstance(raw_station, dict) else []
                station = normalize_station_dict(raw_station)
                station["picks"] = [normalize_pick_dict(p) for p in raw_picks if isinstance(p, dict)]
                sid = station["station_id"]
                station_ids.add(sid)
                ensure_information_station(info, station)
                st_group = ensure_sample_station(sample_group, station)
                write_label_group(st_group, station.get("picks", []))
                for pick in station.get("picks", []):
                    phase_counter[str(pick.get("phase_name", "none"))] += 1
                if args.mseed_index_db or args.waveform_input:
                    write_event_waveforms(sample_group, st_group, station, event, args, np)
            sample_group.attrs["num_stations_used"] = len(stations)
            sample_group.attrs["num_phases_used"] = sum(len(st.get("picks", [])) for st in stations)
        h5.attrs["num_stations"] = len(station_ids)
        h5.attrs["num_events"] = len(catalog.get("events", []))
        h5.attrs["annotation_types"] = list(phase_counter.keys())
        h5.attrs["annotation_counts"] = [phase_counter[k] for k in phase_counter.keys()]
        h5.attrs["file_size"] = "pending"
    write_sidecars(output, args.license_text)
    print(f"[OK] Event HDF5 written to {output}")


def write_event_waveforms(sample_group: Any, station_group: Any, station: Dict[str, Any], event: Dict[str, Any], args: argparse.Namespace, np: Any) -> None:
    origin = event.get("source_origintime")
    if not origin or origin == "none":
        return
    start = obspy_utc(origin) - float(args.event_window_before)
    end = obspy_utc(origin) + float(args.event_window_after)
    network, station_code, location = split_station_id(station["station_id"])
    channels = args.channels or "*"
    stream = None
    if args.mseed_index_db:
        rows = query_tsindex_rows(args.mseed_index_db, network or "*", station_code or "*", location or "*", channels, start, end)
        stream = read_stream_from_tsindex_rows(rows, start, end)
    elif args.waveform_input:
        obspy = import_required("obspy", "Install with: python -m pip install obspy")
        stream = obspy.Stream()
        for file_path in resolve_files(args.waveform_input, suffixes=None if args.all_files else WAVEFORM_SUFFIXES, recursive=True):
            try:
                candidate = obspy.read(str(file_path))
            except Exception:
                continue
            for tr in candidate:
                if network and str(tr.stats.network) != network:
                    continue
                if station_code and str(tr.stats.station) != station_code:
                    continue
                if location and normalize_location(tr.stats.location) != normalize_location(location):
                    continue
                if not fnmatch.fnmatch(str(tr.stats.channel), channels):
                    continue
                if tr.stats.endtime < start or tr.stats.starttime > end:
                    continue
                tr = tr.copy()
                tr.trim(start, end, pad=False)
                stream += tr
    if not stream:
        return
    for trace in stream:
        create_trace_dataset(
            station_group=station_group,
            data=np.asarray(trace.data),
            network=str(trace.stats.network or network),
            station=str(trace.stats.station or station_code),
            location=normalize_location(trace.stats.location or location),
            channel=str(trace.stats.channel),
            sample_rate=float(trace.stats.sampling_rate),
            start=str(trace.stats.starttime),
            end=str(trace.stats.endtime),
            unit=args.unit,
            source_file=str(getattr(trace.stats, "seismicx_source_file", getattr(trace.stats, "_format", "mseedindex"))),
            compression=args.compression,
            compression_opts=args.compression_opts,
        )


def write_sidecars(output_h5: Path, license_text: str) -> None:
    out_dir = output_h5.parent
    license_path = out_dir / "LICENSE"
    if not license_path.exists():
        license_path.write_text(license_text.rstrip() + "\n", encoding="utf-8")
    checksum_path = out_dir / "md5sum.txt"
    entries = []
    for path in [output_h5, license_path]:
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        entries.append(f"{digest}  {path.name}")
    checksum_path.write_text("\n".join(entries) + "\n", encoding="utf-8")


def cmd_make_hdf5(args: argparse.Namespace) -> None:
    if args.hdf5_mode == "event":
        cmd_make_hdf5_event(args)
    elif args.hdf5_mode == "continuous":
        cmd_make_hdf5_continuous(args)
    else:
        raise SystemExit(f"Unsupported mode: {args.hdf5_mode}")


def iter_hdf5_files(value: str) -> List[Path]:
    p = Path(value)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted(list(p.glob("*.h5")) + list(p.glob("*.hdf5")))
    return sorted(Path(x) for x in Path(".").glob(value))


def iter_standard_waveform_datasets(h5_file: Path) -> Iterator[Dict[str, Any]]:
    h5py = import_required("h5py", "Install with: python -m pip install h5py")
    with h5py.File(h5_file, "r") as h5:
        def visitor(name: str, obj: Any) -> None:
            return None

        datasets: List[Tuple[str, Any]] = []
        h5.visititems(lambda name, obj: datasets.append((name, obj)) if hasattr(obj, "shape") and obj.attrs.get("type") == "trace" else None)
        for name, ds in datasets:
            parts = name.split("/")
            sample_id = parts[1] if len(parts) > 1 and parts[0] == "data" else ""
            station_id = parts[2] if len(parts) > 2 and parts[0] == "data" else ""
            network, station, location = split_station_id(station_id)
            start = str(ds.attrs.get("seg_start_time", ds.attrs.get("starttime", "")))
            end = str(ds.attrs.get("seg_end_time", ds.attrs.get("endtime", "")))
            try:
                start_epoch = float(obspy_utc(start).timestamp)
                end_epoch = float(obspy_utc(end).timestamp)
            except Exception:
                start_epoch = math.nan
                end_epoch = math.nan
            yield {
                "h5_file": str(h5_file),
                "dataset_path": "/" + name,
                "sample_id": sample_id,
                "station_id": station_id,
                "network": str(ds.attrs.get("network", network)),
                "station": str(ds.attrs.get("station", station)),
                "location": normalize_location(ds.attrs.get("location", location)),
                "channel": str(ds.attrs.get("channel", parts[-2] if len(parts) > 1 else "")),
                "starttime": start,
                "endtime": end,
                "start_epoch": start_epoch,
                "end_epoch": end_epoch,
                "sample_rate": parse_float(ds.attrs.get("sample_rate", ds.attrs.get("sampling_rate"))),
                "npts": parse_int(ds.attrs.get("npts"), int(ds.shape[0]) if ds.shape else 0),
                "dtype": str(ds.dtype),
                "source_file": str(ds.attrs.get("source_file", "")),
            }


def cmd_build_hdf5_index(args: argparse.Namespace) -> None:
    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    if args.reset:
        cur.execute("DROP TABLE IF EXISTS waveform_segments")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS waveform_segments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          h5_file TEXT NOT NULL,
          dataset_path TEXT NOT NULL,
          sample_id TEXT,
          station_id TEXT,
          network TEXT,
          station TEXT,
          location TEXT,
          channel TEXT,
          starttime TEXT,
          endtime TEXT,
          start_epoch REAL,
          end_epoch REAL,
          sample_rate REAL,
          npts INTEGER,
          dtype TEXT,
          source_file TEXT,
          UNIQUE(h5_file, dataset_path)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_waveform_nslc_time ON waveform_segments(network, station, location, channel, start_epoch, end_epoch)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_waveform_sample ON waveform_segments(sample_id)")
    total = 0
    for h5_file in iter_hdf5_files(args.h5):
        rows = list(iter_standard_waveform_datasets(h5_file))
        cur.executemany(
            """
            INSERT OR IGNORE INTO waveform_segments (
              h5_file, dataset_path, sample_id, station_id, network, station,
              location, channel, starttime, endtime, start_epoch, end_epoch,
              sample_rate, npts, dtype, source_file
            )
            VALUES (
              :h5_file, :dataset_path, :sample_id, :station_id, :network, :station,
              :location, :channel, :starttime, :endtime, :start_epoch, :end_epoch,
              :sample_rate, :npts, :dtype, :source_file
            )
            """,
            rows,
        )
        total += len(rows)
        print(f"[INFO] indexed {len(rows)} waveform dataset(s) from {h5_file}")
    conn.commit()
    conn.close()
    print(f"[OK] HDF5 dataset index written to {db}; waveform_segments={total}")


def cmd_query_hdf5_index(args: argparse.Namespace) -> None:
    clauses = ["network LIKE ?", "station LIKE ?", "location LIKE ?", "channel LIKE ?"]
    params: List[Any] = [wildcard_to_sql(args.network), wildcard_to_sql(args.station), wildcard_to_sql(args.location), wildcard_to_sql(args.channel)]
    if args.sample_id:
        clauses.append("sample_id LIKE ?")
        params.append(wildcard_to_sql(args.sample_id))
    if args.starttime and args.endtime:
        clauses.append("end_epoch >= ?")
        clauses.append("start_epoch <= ?")
        params.extend([float(obspy_utc(args.starttime).timestamp), float(obspy_utc(args.endtime).timestamp)])
    sql = "SELECT * FROM waveform_segments WHERE " + " AND ".join(clauses) + " ORDER BY network, station, location, channel, start_epoch"
    if args.limit:
        sql += " LIMIT ?"
        params.append(int(args.limit))
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    print(json.dumps(rows, ensure_ascii=False, indent=2 if args.pretty else None))
    print(f"[OK] rows={len(rows)}", file=sys.stderr)


class SeismicXHDF5Dataset:
    """Minimal dataset object compatible with torch.utils.data.DataLoader."""

    def __init__(self, h5: str, index_db: Optional[str] = None):
        self.h5_input = h5
        self.index_db = index_db
        if index_db:
            conn = sqlite3.connect(index_db)
            conn.row_factory = sqlite3.Row
            self.items = [dict(r) for r in conn.execute("SELECT * FROM waveform_segments ORDER BY id").fetchall()]
            conn.close()
        else:
            self.items = []
            for h5_file in iter_hdf5_files(h5):
                self.items.extend(iter_standard_waveform_datasets(h5_file))

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> Dict[str, Any]:
        h5py = import_required("h5py", "Install with: python -m pip install h5py")
        item = dict(self.items[index])
        with h5py.File(item["h5_file"], "r") as h5:
            ds = h5[item["dataset_path"]]
            waveform = ds[()]
            attrs = {k: ds.attrs[k] for k in ds.attrs.keys()}
            item["waveform"] = waveform
            item["attrs"] = attrs
            parts = item["dataset_path"].strip("/").split("/")
            if len(parts) >= 3 and parts[0] == "data":
                label_path = "/" + "/".join(parts[:3] + ["label"])
                if label_path in h5:
                    label_group = h5[label_path]
                    labels = {}
                    for key in label_group.keys():
                        values = label_group[key][()]
                        if hasattr(values, "tolist"):
                            values = values.tolist()
                        labels[key] = [v.decode("utf-8") if isinstance(v, bytes) else v for v in values]
                    item["labels"] = labels
        return item


def cmd_example_dataloader(args: argparse.Namespace) -> None:
    dataset = SeismicXHDF5Dataset(args.h5, args.index_db)
    print(f"[OK] dataset samples={len(dataset)}")
    if args.use_torch:
        torch = import_required("torch", "Install with: python -m pip install torch")
        loader = torch.utils.data.DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=0, collate_fn=lambda x: x)
        iterator = iter(loader)
        for i in range(min(args.n_samples, len(dataset))):
            batch = next(iterator)
            item = batch[0]
            print_sample(i, item)
    else:
        for i in range(min(args.n_samples, len(dataset))):
            print_sample(i, dataset[i])


def print_sample(index: int, item: Dict[str, Any]) -> None:
    waveform = item.get("waveform")
    shape = getattr(waveform, "shape", None)
    print(
        f"sample={index} station={item.get('station_id')} channel={item.get('channel')} "
        f"time={item.get('starttime')}..{item.get('endtime')} shape={shape} "
        f"labels={list((item.get('labels') or {}).keys())}"
    )


def add_common_hdf5_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", required=True)
    parser.add_argument("--name", default="SeismicX dataset")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--agency", default="none")
    parser.add_argument("--author", default="none")
    parser.add_argument("--description", default="Standardized SeismicX HDF5 dataset")
    parser.add_argument("--unit", default="counts")
    parser.add_argument("--compression", choices=["gzip", "lzf", "none"], default="gzip")
    parser.add_argument("--compression-opts", type=int, default=4)
    parser.add_argument("--license-text", default="Dataset license should be provided by the data owner.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SeismicX dataset skill helper")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check-deps")
    p.add_argument("--include-torch", action="store_true")
    p.set_defaults(func=cmd_check_deps)

    p = sub.add_parser("install-mseedindex")
    p.add_argument("--no-build", action="store_true")
    p.add_argument("--force-clone", action="store_true")
    p.set_defaults(func=cmd_install_mseedindex)

    p = sub.add_parser("convert-waveforms")
    p.add_argument("--input", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--recursive", action="store_true", default=True)
    p.add_argument("--all-files", action="store_true")
    p.add_argument("--suffixes", default=",".join(sorted(WAVEFORM_SUFFIXES)))
    p.add_argument("--obspy-format", default=None)
    p.add_argument("--merge", action="store_true")
    p.add_argument("--fill-value", default="none")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.set_defaults(func=cmd_convert_waveforms)

    p = sub.add_parser("index-mseed")
    p.add_argument("--input", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--recursive", action="store_true", default=True)
    p.add_argument("--reset", action="store_true")
    p.add_argument("--keep-paths", action="store_true")
    p.add_argument("--skip-non-data", action="store_true")
    p.add_argument("--no-updates", action="store_true")
    p.set_defaults(func=cmd_index_mseed)

    p = sub.add_parser("query-mseed")
    p.add_argument("--db", required=True)
    p.add_argument("--network", default="*")
    p.add_argument("--station", default="*")
    p.add_argument("--location", default="*")
    p.add_argument("--channel", default="*")
    p.add_argument("--starttime", required=True)
    p.add_argument("--endtime", required=True)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--preview", type=int, default=20)
    p.add_argument("--output", default=None)
    p.set_defaults(func=cmd_query_mseed)

    p = sub.add_parser("normalize-labels")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--mapping", default=None)
    p.set_defaults(func=cmd_normalize_labels)

    p = sub.add_parser("make-hdf5")
    mode_sub = p.add_subparsers(dest="hdf5_mode", required=True)

    event = mode_sub.add_parser("event")
    add_common_hdf5_args(event)
    event.add_argument("--catalog", required=True)
    event.add_argument("--mapping", default=None)
    event.add_argument("--mseed-index-db", default=None)
    event.add_argument("--waveform-input", default=None)
    event.add_argument("--channels", default="*")
    event.add_argument("--all-files", action="store_true")
    event.add_argument("--event-window-before", type=float, default=60.0)
    event.add_argument("--event-window-after", type=float, default=180.0)
    event.set_defaults(func=cmd_make_hdf5)

    cont = mode_sub.add_parser("continuous")
    add_common_hdf5_args(cont)
    cont.add_argument("--waveform-input", required=True)
    cont.add_argument("--station-csv", default=None)
    cont.add_argument("--all-files", action="store_true")
    cont.add_argument("--split-interval", choices=["single", "hour", "day", "custom"], default="hour")
    cont.add_argument("--custom-interval-seconds", type=int, default=3600)
    cont.set_defaults(func=cmd_make_hdf5)

    p = sub.add_parser("build-hdf5-index")
    p.add_argument("--h5", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--reset", action="store_true")
    p.set_defaults(func=cmd_build_hdf5_index)

    p = sub.add_parser("query-hdf5-index")
    p.add_argument("--db", required=True)
    p.add_argument("--network", default="*")
    p.add_argument("--station", default="*")
    p.add_argument("--location", default="*")
    p.add_argument("--channel", default="*")
    p.add_argument("--sample-id", default=None)
    p.add_argument("--starttime", default=None)
    p.add_argument("--endtime", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--pretty", action="store_true")
    p.set_defaults(func=cmd_query_hdf5_index)

    p = sub.add_parser("example-dataloader")
    p.add_argument("--h5", required=True)
    p.add_argument("--index-db", default=None)
    p.add_argument("--n-samples", type=int, default=3)
    p.add_argument("--use-torch", action="store_true")
    p.add_argument("--batch-size", type=int, default=1)
    p.set_defaults(func=cmd_example_dataloader)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
