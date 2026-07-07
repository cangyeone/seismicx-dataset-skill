---
name: seismicx-dataset
description: Build SeismicX seismological AI datasets from waveform files and earthquake catalogs. Use when converting arbitrary seismic waveform formats to miniSEED, building and querying EarthScope mseedindex SQLite databases, inferring heterogeneous earthquake catalog or phase-pick formats into canonical JSON, creating standardized HDF5 event or continuous waveform datasets, building dataset SQLite indexes, or reading those datasets with a dataloader in OpenCode, Claude, or Codex.
---

# SeismicX Dataset

Use this skill to produce standardized seismic AI datasets from raw waveforms,
miniSEED archives, mseedindex databases, and heterogeneous event or phase-pick
catalogs.

## First steps

1. Inspect the user's waveform paths, catalog files, station files, and desired
   dataset mode: `event` or `continuous`.
2. Read [references/standard_hdf5_schema.md](references/standard_hdf5_schema.md)
   before writing HDF5 so field names and hierarchy match the standard.
3. Read [references/catalog_normalization.md](references/catalog_normalization.md)
   when the label or catalog format is not already canonical JSON.
4. Read [references/mseedindex_workflow.md](references/mseedindex_workflow.md)
   when converting waveforms, compiling mseedindex, indexing miniSEED, or
   reading waveforms from a mseedindex database.
5. Use `scripts/seismicx_dataset.py` for deterministic work. Run it with
   `--help` and subcommand `--help` when parameters are uncertain.

## Required workflow

For waveform preparation:

```bash
python scripts/seismicx_dataset.py install-mseedindex
python scripts/seismicx_dataset.py convert-waveforms --input RAW_DIR --output-dir mseed
python scripts/seismicx_dataset.py index-mseed --input mseed --db waveform.sqlite --reset
python scripts/seismicx_dataset.py query-mseed --db waveform.sqlite --network '*' --station '*' --channel '*' --starttime 2020-01-01T00:00:00 --endtime 2020-01-01T00:01:00
```

For label normalization:

```bash
python scripts/seismicx_dataset.py normalize-labels --input catalog_or_annotations --output labels.canonical.json
```

If automatic normalization is ambiguous, inspect representative records with
the model, create a mapping JSON, then rerun:

```bash
python scripts/seismicx_dataset.py normalize-labels --input catalog.txt --mapping mapping.json --output labels.canonical.json
```

For event datasets:

```bash
python scripts/seismicx_dataset.py make-hdf5 event \
  --catalog labels.canonical.json \
  --mseed-index-db waveform.sqlite \
  --output seismicx_event.h5 \
  --event-window-before 60 \
  --event-window-after 180
```

Event windows are based on `source_origintime` and explicit window parameters.
Do not cut waveforms from pick arrival times unless the user explicitly asks.
Picks are stored as labels.

For continuous waveform datasets:

```bash
python scripts/seismicx_dataset.py make-hdf5 continuous \
  --waveform-input mseed \
  --station-csv stations.csv \
  --output seismicx_continuous.h5 \
  --split-interval hour
```

For dataset indexing and dataloader checks:

```bash
python scripts/seismicx_dataset.py build-hdf5-index --h5 seismicx_*.h5 --db dataset_index.sqlite --reset
python scripts/seismicx_dataset.py query-hdf5-index --db dataset_index.sqlite --network '*' --station '*' --channel '*'
python scripts/seismicx_dataset.py example-dataloader --h5 seismicx_*.h5 --n-samples 3
```

## HDF5 rules

Always use the same layer names and attributes for both dataset modes:

- `/information` for station and instrument metadata.
- `/data` for samples.
- `/data/{sample_id}/{station_id}/waveform/{channel}/{seg_id}` for waveform
  trace datasets.
- `/data/{sample_id}/{station_id}/label/{field}` for label vectors.
- Use `type` attributes exactly as defined in the standard: `information`,
  `data`, `event`, `station`, `waveform`, `channel`, `trace`, and `label`.
- Use the standard English field names. Do not invent alternate synonyms such
  as `lat`, `lon`, `mag`, `starttime`, or `sampling_rate` when the standard
  requires `source_latitude_deg`, `source_longitude_deg`,
  `source_magnitude`, `seg_start_time`, or `sample_rate`. Compatibility aliases
  may be added only in addition to the standard fields.
- For missing strings write `"none"`. For missing numeric values write `NaN`.

## Catalog inference

When the catalog format is unknown, use the model to infer field meaning from
headers, nearby values, units, and repeated blocks. Preserve the raw source in
`user_defined` when information does not map cleanly. Normalize into
`seismicx_canonical_labels_v1` before HDF5 creation.

The reference JSON shape is represented by
`mini_data/data/label/annotations_mini_two_hours.json`: it is hierarchical by
year, day, event, station, and picks. The canonical JSON used by this skill is
flatter and stricter so many catalog formats can be converted into it.

## Validation

Before handing off a completed dataset or skill edit:

1. Run `python scripts/seismicx_dataset.py check-deps`.
2. Run `python scripts/seismicx_dataset.py install-mseedindex --no-build` or
   without `--no-build` when a compiler is available.
3. Run `python scripts/seismicx_dataset.py normalize-labels` on a small catalog
   sample when labels are involved.
4. Run `python scripts/seismicx_dataset.py build-hdf5-index` and
   `example-dataloader` on produced HDF5 files.
5. Run the skill validator:
   `python /path/to/skill-creator/scripts/quick_validate.py /path/to/this/skill`.
