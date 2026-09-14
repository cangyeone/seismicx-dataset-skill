"""HDF5 profile and release validation for the 2026-08-31 revision draft."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


STANDARD_REVISION = "2026-08-31-draft"
MAX_STRING_BYTES = 65535
ROOT_REQUIRED = {"name": "str", "version": "str", "license": "str", "md5": "str"}
STATION_REQUIRED = {
    "type": "str", "station_id": "str", "station_longitude_deg": "float",
    "station_latitude_deg": "float", "station_elevation_m": "float", "station_depth_m": "float",
}
CHANNEL_REQUIRED = {
    "type": "str", "station_channel_id": "str", "num_of_seg": "int", "start_time": "time",
}
TRACE_REQUIRED = {
    "type": "str", "seg_id": "int", "unit": "str", "sample_rate": "float", "seg_start_time": "time",
}
EVENT_REQUIRED = {
    "type": "str", "event_id": "str", "source_type": "str", "source_origintime": "str",
    "time_standard": "str", "source_longitude_deg": "float", "source_latitude_deg": "float",
    "source_depth_km": "float", "source_magnitude_type": "list", "source_magnitude": "list",
}
CONTINUOUS_REQUIRED = {"type": "str", "event_id": "str"}
QUALITY_REQUIRED = {"type": "str", "trace_quality": "str", "sample_rate": "float", "start_time": "time"}
LABEL_NUMERIC = {"phase_name_prob", "phase_name_snr"}
LIST_FIELDS = {
    "agency", "author", "annotation_types", "annotation_counts", "station_channel_list", "orientation",
    "source_magnitude_type", "source_magnitude", "source_magnitude_error", "source_moment",
    "source_fault_plane", "source_fault_plane_err",
}
STRING_LIST_FIELDS = {"agency", "author", "annotation_types", "station_channel_list", "source_magnitude_type"}
INTEGER_FIELDS = {"seg_id", "num_of_seg", "num_stations", "num_events", "num_phases_used", "num_stations_used"}
FLOAT_FIELDS = {
    "source_origintime_err", "source_origintime_ref", "source_longitude_deg", "source_latitude_deg",
    "source_depth_km", "max_azimuthal_gap_deg", "station_azimuth_uniformity", "min_epicentral_dist_km",
    "max_epicentral_dist_km", "horizontal_uncertainty_major_km", "horizontal_uncertainty_minor_km",
    "horizontal_uncertainty_azimuth", "vertical_uncertainty_km", "residual_mean_sec", "location_rms_sec",
    "station_longitude_deg", "station_latitude_deg", "station_elevation_m", "station_depth_m",
    "sample_rate", "continuity_rate",
}


def json_value(value):
    """JSON has no NaN token; null is the documented reversible missing value."""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if hasattr(value, "tolist"):
        return json_value(value.tolist())
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def json_text(value):
    return json.dumps(json_value(value), ensure_ascii=False, allow_nan=False, sort_keys=True)


def set_standard_attrs(obj, attrs):
    import h5py
    import numpy as np

    for key, value in attrs.items():
        if " " in key:
            raise ValueError(f"Attribute name contains spaces: {key}")
        if key in LIST_FIELDS:
            value = [] if value is None else value
            if key in STRING_LIST_FIELDS:
                value = np.asarray([str(x or "none") for x in value], dtype=h5py.string_dtype("utf-8"))
            else:
                value = np.asarray(value, dtype="int64" if key == "annotation_counts" else "float64")
        elif key == "quality_metric":
            value = np.uint64(value)
        elif key in FLOAT_FIELDS:
            value = np.float64(math.nan if value is None else value)
        elif key in INTEGER_FIELDS:
            value = np.float64(math.nan) if value is None or not math.isfinite(float(value)) else np.int64(value)
        elif isinstance(value, (dict, list, tuple)):
            value = json_text(value)
        elif value is None:
            value = "none"
        if isinstance(value, str) and len(value.encode("utf-8")) > MAX_STRING_BYTES:
            raise ValueError(f"{obj.name}@{key}: string exceeds {MAX_STRING_BYTES} UTF-8 bytes")
        if isinstance(value, np.ndarray) and value.dtype.kind == "O":
            if any(len(str(x).encode("utf-8")) > MAX_STRING_BYTES for x in value.flat):
                raise ValueError(f"{obj.name}@{key}: string list element too long")
        obj.attrs[key] = value


def waveform_datasets(channel):
    import h5py
    return [ds for ds in channel.values() if isinstance(ds, h5py.Dataset)
            and ds.attrs.get("type") == "trace" and "trace_quality" not in ds.attrs]


def epoch(value):
    from obspy import UTCDateTime
    if isinstance(value, (int, float)):
        return float(value)
    return float(UTCDateTime(str(value)).timestamp)


def finalize_channels(h5, trace_quality=False, max_quality_samples=10000000):
    """Sort segments without changing samples; compute union coverage, not summed coverage."""
    import h5py
    import numpy as np

    channels = []
    h5.visititems(lambda _, obj: channels.append(obj) if isinstance(obj, h5py.Group)
                 and obj.attrs.get("type") == "channel" else None)
    for channel in channels:
        traces = sorted(waveform_datasets(channel), key=lambda ds: epoch(ds.attrs["seg_start_time"]))
        if not traces:
            continue
        names = [ds.name.rsplit("/", 1)[-1] for ds in traces]
        for i, name in enumerate(names):
            channel.move(name, f"_sort_{i}")
        for i in range(len(names)):
            channel.move(f"_sort_{i}", str(i))
            channel[str(i)].attrs["seg_id"] = np.int64(i)
        traces = [channel[str(i)] for i in range(len(names))]
        spans = [(epoch(ds.attrs["seg_start_time"]), epoch(ds.attrs["seg_start_time"]) + len(ds) / float(ds.attrs["sample_rate"])) for ds in traces]
        left, right = spans[0]
        covered = 0.0
        gaps = False
        overlaps = False
        for start, end in spans[1:]:
            if start > right + 1e-6:
                covered += right - left
                left, right = start, end
                gaps = True
            else:
                overlaps |= start < right - 1e-6
                right = max(right, end)
        covered += right - left
        total = max(e for _, e in spans) - spans[0][0]
        set_standard_attrs(channel, {
            "num_of_seg": len(traces), "start_time": traces[0].attrs["seg_start_time"],
            "end_time": max(traces, key=lambda ds: epoch(ds.attrs["seg_end_time"])).attrs["seg_end_time"],
            "continuity_rate": min(1.0, max(0.0, covered / total)),
            "user_defined": {"coverage_method": "union of half-open observed intervals",
                             "gaps": gaps, "overlaps": overlaps, "overlap_policy": "preserve all records"},
        })
        for ds in traces:
            if gaps:
                ds.attrs["quality_metric"] = np.uint64(int(ds.attrs["quality_metric"]) | (1 << 4))
                previous = str(ds.attrs.get("quality_metric_description", "none"))
                ds.attrs["quality_metric_description"] = (previous + "; " if previous != "none" else "") + "bit 4: missing intervals in this channel; no filling"
        if not trace_quality:
            continue
        rate = float(traces[0].attrs["sample_rate"])
        offsets = [(s - spans[0][0]) * rate for s, _ in spans]
        if any(float(ds.attrs["sample_rate"]) != rate for ds in traces) or any(abs(x - round(x)) > 1e-3 for x in offsets):
            raise ValueError(f"{channel.name}: trace_quality needs one aligned sampling grid; split channels by rate/epoch or omit --trace-quality")
        length = max(round(offset) + len(ds) for offset, ds in zip(offsets, traces))
        if length > max_quality_samples:
            raise ValueError(f"{channel.name}: quality timeline has {length} samples; use shorter windows or raise --max-quality-samples")
        counts = np.zeros(length, dtype="uint32")
        for offset, ds in zip(offsets, traces):
            counts[round(offset):round(offset) + len(ds)] += 1
        quality = np.where(counts == 0, 1, np.where(counts > 1, 2, 0)).astype("uint8")
        ds = channel.create_dataset("trace_quality", data=quality, compression="gzip")
        set_standard_attrs(ds, {"type": "trace", "trace_quality": "trace_quality", "sample_rate": rate,
                               "start_time": channel.attrs["start_time"], "end_time": channel.attrs["end_time"],
                               "user_defined": {"0": "observed once; other quality not assessed",
                                                "1": "missing", "2": "overlap", "3": "calibration (not inferred)",
                                                "method": "sample-grid coverage counts", "alignment_tolerance_samples": 0.001}})


def export_metadata(h5):
    import h5py

    def node(obj):
        out = {"attributes": json_value(dict(obj.attrs))}
        if isinstance(obj, h5py.Group):
            out["children"] = {name: node(child) for name, child in obj.items()}
        else:
            out["shape"] = list(obj.shape)
            out["dtype"] = str(obj.dtype)
            if obj.attrs.get("type") == "label":
                out["values"] = json_value(obj[()])
        return out

    return node(h5)


def file_md5(path):
    digest = hashlib.md5()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_checksums(directory):
    directory = Path(directory)
    files = sorted(p for p in directory.rglob("*") if p.is_file() and p.name not in {"checksums.md5", "md5sum.txt"})
    lines = [f"{file_md5(p)}  {p.relative_to(directory).as_posix()}" for p in files]
    text = "\n".join(lines) + "\n"
    for name in ("checksums.md5", "md5sum.txt"):
        (directory / name).write_text(text, encoding="utf-8")


def write_release_sidecars(output_h5):
    import h5py
    output_h5 = Path(output_h5)
    with h5py.File(output_h5, "r+") as h5:
        # Fixed storage length avoids changing file size when recording its own size.
        if "file_size" in h5.attrs:
            del h5.attrs["file_size"]
        h5.attrs.create("file_size", b"pending", dtype="S64")
        h5.flush()
        h5.attrs.modify("file_size", f"{output_h5.stat().st_size} bytes".encode("ascii"))
    with h5py.File(output_h5, "r") as h5:
        metadata = export_metadata(h5)
    output_h5.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_checksums(output_h5.parent)


def validate_hdf5(path, release=False):
    """Report structural/value errors separately from permissible missing metadata."""
    import h5py
    import numpy as np
    path = Path(path)
    errors, warnings = [], []

    def error(obj, message):
        errors.append(f"{obj.name}: {message}")

    def check_attrs(obj, required):
        for key, kind in required.items():
            if key not in obj.attrs:
                error(obj, f"missing required attribute {key}")
                continue
            value = obj.attrs[key]
            arr = np.asarray(value)
            good = ((kind == "str" and isinstance(value, (str, bytes))) or
                    (kind == "float" and arr.ndim == 0 and arr.dtype.kind == "f") or
                    (kind == "int" and arr.ndim == 0 and (arr.dtype.kind in "iu" or (arr.dtype.kind == "f" and np.isnan(value)))) or
                    (kind == "list" and arr.ndim >= 1) or
                    (kind == "time" and (isinstance(value, (str, bytes)) or arr.ndim == 0 and arr.dtype.kind in "fiu")))
            if not good:
                error(obj, f"{key} must have type {kind}")
            if (isinstance(value, str) and value == "none") or (arr.ndim == 0 and arr.dtype.kind == "f" and np.isnan(value)):
                warnings.append(f"{obj.name}@{key}: missing value placeholder")
        for key, value in obj.attrs.items():
            if " " in key:
                error(obj, f"attribute name contains spaces: {key}")
            if isinstance(value, str) and len(value.encode("utf-8")) > MAX_STRING_BYTES:
                error(obj, f"{key} exceeds UTF-8 string limit")
            arr = np.asarray(value)
            if key in FLOAT_FIELDS and (arr.ndim != 0 or arr.dtype != np.dtype("float64")):
                error(obj, f"{key} must be float64")
            if key in INTEGER_FIELDS and (arr.ndim != 0 or not (arr.dtype == np.dtype("int64") or arr.dtype == np.dtype("float64") and np.isnan(value))):
                error(obj, f"{key} must be int64, or float64 NaN when missing")
            if key in LIST_FIELDS and arr.ndim == 0:
                error(obj, f"{key} must be a native HDF5 list, not JSON text")
            elif key in LIST_FIELDS and arr.size and key not in STRING_LIST_FIELDS and arr.dtype != np.dtype("int64" if key == "annotation_counts" else "float64"):
                error(obj, f"{key} has inconsistent numeric precision")
            for text in ([value] if isinstance(value, str) else arr.flat if key in STRING_LIST_FIELDS else []):
                if len(str(text).encode("utf-8")) > MAX_STRING_BYTES:
                    error(obj, f"{key} exceeds UTF-8 string limit")
            if key == "user_defined" and isinstance(value, str):
                try:
                    json.loads(value)
                except ValueError:
                    error(obj, "user_defined attribute must encode JSON")

    try:
        with h5py.File(path, "r") as h5:
            check_attrs(h5, ROOT_REQUIRED)
            if h5.attrs.get("license") != "LICENSE":
                error(h5, "license must reference LICENSE")
            if h5.attrs.get("standard_revision") != STANDARD_REVISION:
                error(h5, f"expected profile revision {STANDARD_REVISION}; migrate legacy files before validation")
            for name in ("information", "data"):
                if name not in h5 or not isinstance(h5[name], h5py.Group) or h5[name].attrs.get("type") != name:
                    error(h5, f"missing or invalid /{name} group")
            mode = h5.attrs.get("dataset_mode")
            if mode not in {"event", "continuous"}:
                error(h5, "dataset_mode must be event or continuous")
            events, station_ids, phase_counts, trace_count = [], set(), {}, [0]

            def visit(_, obj):
                kind = obj.attrs.get("type")
                is_group = isinstance(obj, h5py.Group)
                if kind not in {"information", "data", "event", "station", "waveform", "channel", "trace", "label"}:
                    error(obj, "missing or unsupported hierarchy type")
                    return
                if kind not in {"trace", "label"} and not is_group:
                    error(obj, "expected a group")
                    return
                if kind == "event":
                    check_attrs(obj, CONTINUOUS_REQUIRED if mode == "continuous" else EVENT_REQUIRED)
                    if obj.parent.attrs.get("type") != "data":
                        error(obj, "sample must be under a data group")
                    events.append(str(obj.attrs.get("event_id")))
                    sample_traces = []
                    obj.visititems(lambda _, child: sample_traces.append(child.name) if isinstance(child, h5py.Dataset)
                                   and child.attrs.get("type") == "trace" and "trace_quality" not in child.attrs else None)
                    if not sample_traces:
                        error(obj, "sample contains no waveform segments")
                    if mode == "event":
                        mags = obj.attrs.get("source_magnitude", [])
                        types = obj.attrs.get("source_magnitude_type", [])
                        if len(np.atleast_1d(mags)) != len(np.atleast_1d(types)):
                            error(obj, "magnitude values/types must align")
                        errs = obj.attrs.get("source_magnitude_error", [])
                        if len(np.atleast_1d(errs)) not in (0, len(np.atleast_1d(types))):
                            error(obj, "magnitude errors must align")
                        preferred = obj.attrs.get("preferred_magnitude_type", "none")
                        if preferred != "none" and preferred not in np.atleast_1d(types):
                            error(obj, "preferred_magnitude_type is not in source_magnitude_type")
                        for key, bound in (("source_longitude_deg", 180), ("source_latitude_deg", 90)):
                            value = obj.attrs.get(key, math.nan)
                            if isinstance(value, (float, np.floating)) and math.isfinite(value) and abs(value) > bound:
                                error(obj, f"out-of-range {key}")
                        plane = np.asarray(obj.attrs.get("source_fault_plane", []))
                        plane_err = np.asarray(obj.attrs.get("source_fault_plane_err", []))
                        if plane.size and plane.shape not in {(3,), (2, 3)}:
                            error(obj, "source_fault_plane must have shape (3,) or (2,3)")
                        if plane_err.size and plane_err.shape != plane.shape:
                            error(obj, "source_fault_plane_err must align with source_fault_plane")
                        moment = np.asarray(obj.attrs.get("source_moment", []))
                        if moment.size and moment.shape not in {(6,), (3, 3)}:
                            error(obj, "source_moment must contain six components or a 3x3 matrix")
                        origin = str(obj.attrs.get("source_origintime", "none"))
                        if origin != "none":
                            try:
                                epoch(origin)
                            except Exception:
                                error(obj, "invalid source_origintime")
                            if obj.attrs.get("time_standard") == "UTC" and not (origin.endswith("Z") or origin.endswith("+00:00")):
                                error(obj, "UTC source_origintime must explicitly include Z or +00:00")
                elif kind == "station":
                    check_attrs(obj, STATION_REQUIRED)
                    sid = str(obj.attrs.get("station_id"))
                    station_ids.add(sid)
                    if obj.parent.attrs.get("type") == "event":
                        for child in ("waveform", "label"):
                            if child not in obj or obj[child].attrs.get("type") != child:
                                error(obj, f"missing {child} group")
                    elif obj.parent.attrs.get("type") != "information":
                        error(obj, "station must be under event or information")
                    for key, bound in (("station_longitude_deg", 180), ("station_latitude_deg", 90)):
                        value = obj.attrs.get(key, math.nan)
                        if isinstance(value, (float, np.floating)) and math.isfinite(value) and abs(value) > bound:
                            error(obj, f"out-of-range {key}")
                elif kind == "channel":
                    check_attrs(obj, CHANNEL_REQUIRED)
                    if obj.parent.attrs.get("type") != "waveform":
                        error(obj, "channel must be under waveform")
                    traces = waveform_datasets(obj)
                    if obj.attrs.get("num_of_seg") != len(traces):
                        error(obj, "num_of_seg disagrees with waveform segment count")
                    ordered = sorted(traces, key=lambda ds: epoch(ds.attrs.get("seg_start_time", 0)))
                    if [ds.attrs.get("seg_id") for ds in ordered] != list(range(len(ordered))):
                        error(obj, "seg_id must start at zero and follow start-time order")
                    channel_id = obj.attrs.get("station_channel_id")
                    if channel_id not in obj.parent.parent.attrs.get("station_channel_list", []):
                        error(obj, "channel code missing from station_channel_list")
                    orientation = np.asarray(obj.attrs.get("orientation", []))
                    if orientation.shape not in {(0,), (2,)}:
                        error(obj, "orientation must be [azimuth_deg, dip_deg]")
                    rate = obj.attrs.get("continuity_rate", math.nan)
                    if not isinstance(rate, (float, np.floating)) or (math.isfinite(rate) and not 0 <= rate <= 1):
                        error(obj, "continuity_rate must be float in [0, 1] or NaN")
                elif kind == "trace":
                    if is_group:
                        error(obj, "trace must be a dataset")
                        return
                    quality = "trace_quality" in obj.attrs
                    check_attrs(obj, QUALITY_REQUIRED if quality else TRACE_REQUIRED)
                    if obj.parent.attrs.get("type") != "channel" or obj.ndim != 1:
                        error(obj, "trace must be a 1-D dataset under channel")
                    if obj.dtype.kind not in "iuf":
                        error(obj, "trace must be numeric")
                    sr = float(obj.attrs.get("sample_rate", math.nan))
                    if not math.isfinite(sr) or sr <= 0 or len(obj) == 0:
                        error(obj, "trace requires positive sample_rate and nonempty data")
                    else:
                        start_key, end_key = ("start_time", "end_time") if quality else ("seg_start_time", "seg_end_time")
                        if end_key in obj.attrs:
                            expected = epoch(obj.attrs.get(start_key, 0)) + (len(obj) - 1) / sr
                            if abs(epoch(obj.attrs[end_key]) - expected) > max(1e-6, 1e-3 / sr):
                                error(obj, "end time disagrees with length/sample_rate")
                    if quality:
                        if obj.name.rsplit("/", 1)[-1] != "trace_quality" or obj.attrs["trace_quality"] != "trace_quality":
                            error(obj, "quality sequence must be named trace_quality")
                        if obj.dtype.kind not in "iu":
                            error(obj, "quality codes must be integers")
                        if obj.attrs.get("start_time") != obj.parent.attrs.get("start_time") or obj.attrs.get("end_time") != obj.parent.attrs.get("end_time"):
                            error(obj, "quality timeline must cover the whole channel")
                    else:
                        trace_count[0] += 1
                        for offset in range(0, len(obj), 1000000):
                            if not np.isfinite(obj[offset:offset + 1000000]).all():
                                error(obj, "missing/nonfinite waveform values must be split into separate segments")
                                break
                        if obj.attrs.get("quality_flag", "D") not in {"D", "R", "Q", "M", "none"}:
                            error(obj, "invalid quality_flag")
                        if "quality_metric" in obj.attrs and np.asarray(obj.attrs["quality_metric"]).dtype != np.dtype("uint64"):
                            error(obj, "quality_metric must be uint64")
                        for alias in ("starttime", "endtime", "sampling_rate", "network", "station", "location", "channel"):
                            if alias in obj.attrs:
                                error(obj, f"duplicate/nonstandard field alias: {alias}")
                elif kind == "label":
                    if is_group:
                        if obj.parent.attrs.get("type") != "station":
                            error(obj, "label group must be under station")
                        lengths = {len(ds) for ds in obj.values() if isinstance(ds, h5py.Dataset) and ds.ndim == 1}
                        if len(lengths) > 1:
                            error(obj, "label vectors must have equal lengths")
                        if "phase_name" in obj:
                            for phase in obj["phase_name"].asstr()[()]:
                                phase_counts[phase] = phase_counts.get(phase, 0) + 1
                    elif obj.parent.attrs.get("type") != "label" or obj.ndim != 1:
                        error(obj, "label must be a 1-D dataset under label group")
                    elif obj.name.rsplit("/", 1)[-1] in LABEL_NUMERIC:
                        if obj.dtype != np.dtype("float64"):
                            error(obj, "numeric labels must be float64")
                        if obj.name.endswith("/phase_name_prob") and np.any((obj[()] < 0) | (obj[()] > 1)):
                            error(obj, "phase probability outside [0, 1]")
                    elif h5py.check_string_dtype(obj.dtype) is None:
                        error(obj, "text labels must use UTF-8 strings")
                    else:
                        for value in obj.asstr()[()]:
                            if len(value.encode("utf-8")) > MAX_STRING_BYTES:
                                error(obj, "label exceeds UTF-8 string limit")
                            if obj.name.endswith("_annotation_method") and value != "none" and not value.startswith(("manual_", "automatic_")):
                                error(obj, "annotation method needs manual_ or automatic_ prefix")
                            if obj.name.endswith("/user_defined"):
                                try:
                                    json.loads(value)
                                except ValueError:
                                    error(obj, "user_defined must contain JSON strings")
                elif kind == "waveform" and obj.parent.attrs.get("type") != "station":
                    error(obj, "waveform must be under station")
                check_attrs(obj, {})

            h5.visititems(visit)
            if len(events) != len(set(events)):
                error(h5, "duplicate event_id")
            if not events or not trace_count[0]:
                error(h5, "dataset must contain samples and waveform data")
            if "num_stations" in h5.attrs and h5.attrs["num_stations"] != len(station_ids):
                error(h5, "num_stations disagrees with station metadata")
            if "num_events" in h5.attrs and h5.attrs["num_events"] != (len(events) if mode == "event" else 0):
                error(h5, "num_events counts earthquake events, not continuous windows")
            types = list(h5.attrs.get("annotation_types", []))
            counts = list(h5.attrs.get("annotation_counts", []))
            if len(types) != len(counts) or dict(zip(types, counts)) != phase_counts:
                error(h5, "annotation types/counts disagree with labels")
            expected_json = export_metadata(h5)
            checksum_name = str(h5.attrs.get("md5", "md5sum.txt"))
            if release and json_value(h5.attrs.get("file_size")) != f"{path.stat().st_size} bytes":
                error(h5, "file_size is not the finalized HDF5 size")
        if release:
            sidecar = path.with_suffix(".json")
            if mode == "continuous" or sidecar.exists():
                if not sidecar.exists():
                    errors.append("Continuous dataset requires a hierarchical JSON sidecar")
                else:
                    actual = json.loads(sidecar.read_text(encoding="utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"Invalid JSON token: {x}")))
                    if actual != expected_json:
                        errors.append("JSON sidecar does not match HDF5 hierarchy, attributes and labels")
            license_path = path.parent / "LICENSE"
            if not license_path.exists() or not license_path.read_text(encoding="utf-8").strip() or "Dataset license should be provided" in license_path.read_text(encoding="utf-8"):
                errors.append("A data-owner-supplied non-placeholder LICENSE is required")
            if checksum_name not in {"checksums.md5", "md5sum.txt"}:
                errors.append("Unsupported checksum filename")
            manifest = path.parent / checksum_name
            if not manifest.exists():
                errors.append("Missing checksum manifest")
            else:
                mirror = path.parent / ("checksums.md5" if checksum_name == "md5sum.txt" else "md5sum.txt")
                if not mirror.exists() or mirror.read_bytes() != manifest.read_bytes():
                    errors.append("The profile requires identical checksums.md5 and md5sum.txt manifests")
                recorded = {}
                for line in manifest.read_text(encoding="utf-8").splitlines():
                    digest, name = line.split("  ", 1)
                    target = (path.parent / name).resolve()
                    if not target.is_relative_to(path.parent.resolve()) or not target.is_file():
                        errors.append(f"Invalid checksum path: {name}")
                    elif file_md5(target) != digest:
                        errors.append(f"Checksum mismatch: {name}")
                    recorded[name] = digest
                expected = {p.relative_to(path.parent).as_posix() for p in path.parent.rglob("*") if p.is_file() and p.name not in {"checksums.md5", "md5sum.txt"}}
                if set(recorded) != expected:
                    errors.append("Checksums must cover all release files except checksum manifests themselves")
    except (ValueError, TypeError, KeyError, OSError) as exc:
        errors.append(f"Cannot validate {path.name}: {exc}")
    return {"file": str(path), "standard_revision": STANDARD_REVISION, "valid": not errors,
            "errors": errors, "warnings": warnings}
