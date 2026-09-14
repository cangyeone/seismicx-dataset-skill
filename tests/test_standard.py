"""Behavioral regression tests using small synthetic, non-research waveforms."""

import json
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest
from obspy import Stream, Trace, UTCDateTime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seismicx_dataset as sx
from seismicx_standard import validate_hdf5, waveform_datasets


def trace(offset=0, channel="BHZ", data=None):
    values = np.arange(10, dtype="int32") if data is None else data
    return Trace(values, {"network": "XX", "station": "TEST", "location": "",
                          "channel": channel, "sampling_rate": 10.0,
                          "starttime": UTCDateTime("2026-01-01") + offset})


@pytest.fixture
def inputs(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    # Filename order deliberately disagrees with time order; preserve overlaps.
    for name, tr in [("a", trace(2)), ("b", trace(0)), ("c", trace(0.5)), ("d", trace(0, "BHN"))]:
        tr.write(str(raw / f"{name}.mseed"), format="MSEED")
    station = sx.normalize_station_dict({"network": "XX", "station": "TEST", "station_longitude_deg": 100,
                                         "station_latitude_deg": 30, "station_elevation_m": 10, "station_depth_m": 0,
                                         "station_channel_list": ["BHZ", "BHN"], "sensor_model": "synthetic"})
    station["picks"] = [dict(phase_name="P", phase_arrival_time="2026-01-01T00:00:00.700000Z", phase_name_prob=0.9,
                             phase_annotation_method=method, user_defined={"review": "kept"})
                        for method in ("manual_TEST", "automatic_test_picker")]
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(sx.json_value({"events": [{"event_id": "catalog/uri/1", "source_type": "eq",
        "source_origintime": "2026-01-01T00:00:00Z", "source_magnitude_type": ["Ml", "Mw"],
        "source_magnitude": [1.2, 1.1], "stations": [station], "custom_review": "keep"}]})))
    return raw, catalog


def make(tmp_path, inputs, mode, *extra):
    raw, catalog = inputs
    output = tmp_path / mode / "dataset.h5"
    args = ["make-hdf5", mode, "--waveform-input", str(raw), "--output", str(output),
            "--license-text", "Synthetic test data only. CC0-1.0.", "--trace-quality"]
    if mode == "event":
        args += ["--catalog", str(catalog), "--event-window-before", "0", "--event-window-after", "5"]
    args += list(extra)
    sx.main(args)
    return output


@pytest.mark.parametrize("mode", ["event", "continuous"])
def test_release_roundtrip_and_quality(tmp_path, inputs, mode):
    output = make(tmp_path, inputs, mode)
    assert validate_hdf5(output, release=True)["valid"]
    with h5py.File(output) as h5:
        sample = next(iter(h5["data"].values()))
        st = next(iter(sample.values()))
        ch = st["waveform/BHZ"]
        assert [ds.attrs["seg_id"] for ds in waveform_datasets(ch)] == [0, 1, 2]
        assert ch.attrs["num_of_seg"] == 3
        assert ch.attrs["continuity_rate"] == pytest.approx(25 / 30)
        expected = np.array([0] * 5 + [2] * 5 + [0] * 5 + [1] * 5 + [0] * 10)
        np.testing.assert_array_equal(ch["trace_quality"][()], expected)
        for ds in waveform_datasets(ch):
            np.testing.assert_array_equal(ds[()], np.arange(10, dtype="int32"))
            assert ds.attrs["quality_metric"].dtype == np.dtype("uint64")
        assert set(h5["information/XX.TEST.--"].attrs["station_channel_list"]) == {"BHZ", "BHN"}
        if mode == "continuous":
            assert "source_origintime" not in sample.attrs
            assert h5.attrs["num_events"] == 0
        else:
            assert sample.attrs["event_id"] == "catalog/uri/1"
            assert json.loads(sample.attrs["user_defined"])["custom_review"] == "keep"
            assert len(st["label/phase_name"]) == 2
            assert np.isnan(sample.attrs["num_phases_used"])
        assert "starttime" not in ch["0"].attrs
    db = output.parent / "index.sqlite"
    sx.main(["build-hdf5-index", "--h5", str(output), "--db", str(db)])
    dataset = sx.SeismicXHDF5Dataset(str(output), str(db))
    assert len(dataset) == 4  # trace_quality must never enter the waveform index.
    item = next(dataset[i] for i in range(len(dataset)) if dataset[i]["channel"] == "BHZ")
    assert len(item["trace_quality"]) == 30
    assert len(item["waveform"]) == 10
    assert not validate_hdf5(output, release=True)["valid"]  # Newly added index needs a checksum.
    sx.main(["package-dataset", "--h5", str(output)])
    assert validate_hdf5(output, release=True)["valid"]
    output.with_suffix(".json").write_text("{}")
    report = validate_hdf5(output, release=True)
    assert not report["valid"] and any("JSON" in msg for msg in report["errors"])


def test_continuous_labels_do_not_change_waveform_windows(tmp_path, inputs):
    output = make(tmp_path, inputs, "continuous", "--catalog", str(inputs[1]))
    item = sx.SeismicXHDF5Dataset(str(output))[0]
    assert item["labels"]["phase_name"] == ["P", "P"]
    assert json.loads(item["labels"]["user_defined"][0])["source_event_id"] == "catalog/uri/1"


def test_split_masked_and_nonfinite_without_fill():
    values = np.ma.array([1., 2., 3., np.nan, 5., 6.], mask=[0, 1, 0, 0, 0, 0])
    stream = sx.split_missing_stream(Stream([trace(data=values)]))
    assert [list(tr.data) for tr in stream] == [[1.], [3.], [5., 6.]]
    assert [float(tr.stats.starttime - UTCDateTime("2026-01-01")) for tr in stream] == [0, 0.2, 0.4]
    assert all(tr.stats.seismicx_quality_metric & 16 for tr in stream)


def test_normalization_missing_values_mapping_and_provenance(tmp_path):
    event = sx.normalize_event_dict({"event_id": "a", "origin_time": "2026-01-01T08:00:00+08:00",
                                     "depth_m": 2000, "used": 5}, {"num_phases_used": "used"})
    assert event["source_origintime"] == "2026-01-01T00:00:00.000000Z"
    assert event["num_phases_used"] == 5
    assert event["user_defined"]["depth_m"] == 2000  # No silent unit assumption.
    assert np.isnan(sx.normalize_station_dict({})["station_depth_m"])
    unknown = sx.normalize_pick_dict({"phase": "P", "picker": "unknown-method", "user_defined": {"keep": 1}, "extra": 2})
    assert unknown["phase_annotation_method"] == "none"
    assert unknown["user_defined"]["original_phase_annotation_method"] == "unknown-method"
    assert unknown["user_defined"]["extra"] == 2
    assert unknown["user_defined"]["keep"] == 1
    source = tmp_path / "labels.json"
    source.write_text(json.dumps({"events": [{"event_id": "a", "stations": []}]}))
    target = tmp_path / "canonical.json"
    sx.main(["normalize-labels", "--input", str(source), "--output", str(target)])
    text = target.read_text()
    assert "NaN" not in text and "Infinity" not in text
    assert json.loads(text)["events"][0]["source_depth_km"] is None


def test_magnitude_misalignment_rejected():
    with pytest.raises(ValueError, match="equal lengths"):
        sx.normalize_event_dict({"source_magnitude_type": ["Ml", "Mw"], "source_magnitude": [1.]})


def test_no_placeholder_license_or_silent_overwrite(tmp_path, inputs):
    raw, _ = inputs
    with pytest.raises(SystemExit, match="license"):
        sx.main(["make-hdf5", "continuous", "--waveform-input", str(raw), "--output", str(tmp_path / "out/d.h5")])
    output = make(tmp_path, inputs, "continuous")
    with pytest.raises(SystemExit, match="Output exists"):
        sx.main(["make-hdf5", "continuous", "--waveform-input", str(raw), "--output", str(output)])


def test_validator_rejects_broken_schema(tmp_path, inputs):
    output = make(tmp_path, inputs, "event")
    with h5py.File(output, "r+") as h5:
        sample = next(iter(h5["data"].values()))
        st = next(iter(sample.values()))
        del st.attrs["station_depth_m"]
        ds = st["waveform/BHZ/0"]
        ds.attrs["seg_id"] = 9
        ds.attrs["quality_metric"] = 0
        ds.attrs["sampling_rate"] = 10.
        st["label/phase_name_prob"][0] = 2.
    report = validate_hdf5(output)
    assert not report["valid"]
    for needle in ("station_depth_m", "seg_id", "uint64", "alias", "probability"):
        assert any(needle in error for error in report["errors"]), report


def test_quality_grid_mismatch_rejected(tmp_path, inputs):
    raw, _ = inputs
    trace(0.025).write(str(raw / "offgrid.mseed"), format="MSEED")
    with pytest.raises(ValueError, match="aligned sampling grid"):
        make(tmp_path, inputs, "continuous")


def test_mseedindex_empty_location_event_read(tmp_path, inputs):
    raw, catalog = inputs
    db = tmp_path / "waveform.sqlite"
    sx.main(["index-mseed", "--input", str(raw), "--db", str(db), "--reset"])
    output = tmp_path / "indexed/dataset.h5"
    sx.main(["make-hdf5", "event", "--catalog", str(catalog), "--mseed-index-db", str(db),
             "--output", str(output), "--license-text", "Synthetic test data. CC0-1.0."])
    assert len(sx.SeismicXHDF5Dataset(str(output))) == 4
    assert validate_hdf5(output, release=True)["valid"]


def test_explicit_station_codes_and_relative_origin(tmp_path, inputs):
    _, catalog = inputs
    obj = json.loads(catalog.read_text())
    event = obj["events"][0]
    event["source_origintime"] = "2025-12-31T23:59:00Z"
    event["source_origintime_ref"] = 60.
    event["stations"][0]["station_id"] = "station/custom/identifier"
    catalog.write_text(json.dumps(obj))
    output = make(tmp_path, inputs, "event")
    ds = sx.SeismicXHDF5Dataset(str(output))
    assert len(ds) == 4
    assert ds[0]["station_id"] == "station/custom/identifier"
    assert ds[0]["network"] == "XX"
    assert np.isnan(ds[0]["labels"]["phase_name_snr"][0])


def test_hour_boundary_no_lost_or_duplicated_samples(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    values = np.arange(20, dtype="float64")
    tr = trace(3599.5, data=values)
    tr.write(str(raw / "boundary.mseed"), format="MSEED")
    output = make(tmp_path, (raw, None), "continuous")
    ds = sx.SeismicXHDF5Dataset(str(output))
    assert len(ds) == 2
    np.testing.assert_array_equal(np.concatenate([ds[i]["waveform"] for i in range(2)]), values)


def test_nested_data_groups_use_attributes_for_index(tmp_path, inputs):
    output = make(tmp_path, inputs, "event")
    with h5py.File(output, "r+") as h5:
        sample_key = next(iter(h5["data"]))
        h5["data"].create_group("train").attrs["type"] = "data"
        h5.move(f"data/{sample_key}", f"data/train/{sample_key}")
    sx.main(["package-dataset", "--h5", str(output)])
    ds = sx.SeismicXHDF5Dataset(str(output))
    assert len(ds) == 4
    assert ds[0]["sample_id"] == "catalog/uri/1"
    assert ds[0]["labels"]["phase_name"] == ["P", "P"]


def test_continuous_opaque_station_metadata_and_labels(tmp_path, inputs):
    _, catalog = inputs
    obj = json.loads(catalog.read_text())
    obj["events"][0]["stations"][0]["station_id"] = "inventory-001"
    catalog.write_text(json.dumps(obj))
    csv_path = tmp_path / "stations.csv"
    csv_path.write_text("station_id,network,station,location,station_longitude_deg,station_latitude_deg,station_elevation_m,station_depth_m\ninventory-001,XX,TEST,,100,30,10,123\n")
    output = make(tmp_path, inputs, "continuous", "--station-csv", str(csv_path), "--catalog", str(catalog))
    item = sx.SeismicXHDF5Dataset(str(output))[0]
    assert item["station_id"] == "inventory-001"
    assert item["station_attrs"]["station_depth_m"] == 123
    assert item["labels"]["phase_name"] == ["P", "P"]


def test_station_metadata_does_not_cross_locations(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    tr = trace()
    tr.stats.location = "10"
    tr.write(str(raw / "wave.mseed"), format="MSEED")
    csv_path = tmp_path / "stations.csv"
    csv_path.write_text("network,station,location,station_depth_m\nXX,TEST,00,123\n")
    output = make(tmp_path, (raw, None), "continuous", "--station-csv", str(csv_path))
    item = sx.SeismicXHDF5Dataset(str(output))[0]
    assert item["station_id"] == "XX.TEST.10"
    assert np.isnan(item["station_attrs"]["station_depth_m"])


@pytest.mark.parametrize("numeric", [False, True])
@pytest.mark.parametrize("missing_end", [False, True])
def test_index_numeric_time_optional_end_and_channel_identifier(tmp_path, inputs, numeric, missing_end):
    output = make(tmp_path, inputs, "event")
    with h5py.File(output, "r+") as h5:
        sample = next(iter(h5["data"].values()))
        st = next(iter(sample.values()))
        st["waveform"].move("BHZ", "channel-key-1")
        for channel in st["waveform"].values():
            del channel["trace_quality"]
            if numeric:
                for field in ("start_time", "end_time"):
                    channel.attrs[field] = float(UTCDateTime(channel.attrs[field]).timestamp)
            for ds in waveform_datasets(channel):
                if numeric:
                    for field in ("seg_start_time", "seg_end_time"):
                        ds.attrs[field] = float(UTCDateTime(ds.attrs[field]).timestamp)
                if missing_end:
                    del ds.attrs["seg_end_time"]
    assert validate_hdf5(output)["valid"]
    rows = list(sx.iter_standard_waveform_datasets(output))
    t0 = float(UTCDateTime("2026-01-01").timestamp)
    assert len(rows) == 4
    assert all(t0 <= row["start_epoch"] <= row["end_epoch"] <= t0 + 3 for row in rows)
    assert {row["channel"] for row in rows} == {"BHZ", "BHN"}


def test_index_declared_relative_time(tmp_path, inputs):
    output = make(tmp_path, inputs, "event")
    with h5py.File(output, "r+") as h5:
        sample = next(iter(h5["data"].values()))
        st = next(iter(sample.values()))
        for channel in st["waveform"].values():
            del channel["trace_quality"]
            channel.attrs["user_defined"] = json.dumps({"time_reference": "2026-01-01T00:00:00Z"})
            for key in ("start_time", "end_time"):
                channel.attrs[key] = float(UTCDateTime(channel.attrs[key]) - UTCDateTime("2026-01-01"))
            for ds in waveform_datasets(channel):
                for key in ("seg_start_time", "seg_end_time"):
                    ds.attrs[key] = float(UTCDateTime(ds.attrs[key]) - UTCDateTime("2026-01-01"))
    assert validate_hdf5(output)["valid"]
    rows = list(sx.iter_standard_waveform_datasets(output))
    assert all(row["start_epoch"] >= UTCDateTime("2026-01-01").timestamp for row in rows)


def test_optional_quality_end_and_annotation_summary(tmp_path, inputs):
    output = make(tmp_path, inputs, "event")
    with h5py.File(output, "r+") as h5:
        del h5.attrs["annotation_types"]
        del h5.attrs["annotation_counts"]
        del h5.attrs["file_size"]
        sample = next(iter(h5["data"].values()))
        st = next(iter(sample.values()))
        for channel in st["waveform"].values():
            del channel["trace_quality"].attrs["end_time"]
            del channel.attrs["end_time"]
            for ds in waveform_datasets(channel):
                del ds.attrs["seg_end_time"]
    report = validate_hdf5(output)
    assert report["valid"], report
    sx.main(["package-dataset", "--h5", str(output)])
    assert validate_hdf5(output, release=True)["valid"]


@pytest.mark.parametrize("problem", ["mixed-rate", "unaligned", "channel-bounds"])
def test_validator_quality_grid_and_channel_bounds(tmp_path, inputs, problem):
    output = make(tmp_path, inputs, "event")
    with h5py.File(output, "r+") as h5:
        sample = next(iter(h5["data"].values()))
        channel = next(iter(sample.values()))["waveform/BHZ"]
        if problem == "mixed-rate":
            attrs = dict(channel["0"].attrs)
            del channel["0"]
            ds = channel.create_dataset("0", data=np.arange(19, dtype="int32"))
            for key, value in attrs.items():
                ds.attrs[key] = value
            ds.attrs["sample_rate"] = 20.
        elif problem == "unaligned":
            for field in ("seg_start_time", "seg_end_time"):
                channel["1"].attrs[field] = str(UTCDateTime(channel["1"].attrs[field]) + .025)
        else:
            del channel["trace_quality"]
            channel.attrs["start_time"] = "2027-01-01T00:00:00Z"
    report = validate_hdf5(output)
    assert not report["valid"]
    needle = "bounds" if problem == "channel-bounds" else "aligned sampling grid"
    assert any(needle in error for error in report["errors"]), report
