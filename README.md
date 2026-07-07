![SeismicX Dataset](logo.png)

# SeismicX Dataset Skill

Agent-friendly workflows and helper tools for standardized seismological AI
dataset production from local waveform archives, miniSEED indexes, earthquake
catalogs, phase-pick annotations, and continuous waveform directories. The
package is usable from Codex-style skills, OpenCode `AGENTS.md`, Claude Code
`CLAUDE.md`, or any agent that can read Markdown instructions and run local
scripts.

## What It Does

This repository packages a publishable, agent-agnostic skill for making
standardized SeismicX HDF5 datasets:

- Read ObsPy-readable waveform formats such as MSEED, miniSEED, SAC, SEED,
  GCF, SEGY, SU, and other formats supported by the local ObsPy installation.
- Convert waveform archives to miniSEED and build an EarthScope `mseedindex`
  SQLite waveform database.
- Query the `mseedindex` database and read trimmed waveform windows back from
  indexed miniSEED files.
- Infer heterogeneous earthquake catalog, phase-pick, or annotation formats
  into `seismicx_canonical_labels_v1` JSON.
- Convert the mini annotation JSON style used by
  `mini_data/data/label/annotations_mini_two_hours.json` into the canonical
  label contract.
- Build two standardized dataset families: event-oriented earthquake datasets
  and continuous-waveform datasets.
- Store both families with the same HDF5 hierarchy, group `type` attributes,
  and standard English metadata fields from the SeismicX dataset standard.
- Build a dataset SQLite index over produced HDF5 waveform datasets.
- Read generated HDF5 files with a minimal dataloader compatible with
  `torch.utils.data.DataLoader` when PyTorch is available.

## Repository Layout

```text
SKILL.md
AGENTS.md
CLAUDE.md
agents/openai.yaml
scripts/seismicx_dataset.py
references/
assets/
logo.png
README.md
LICENSE
```

Large waveform examples, generated HDF5 files, generated SQLite databases,
compiled binaries, and local reference datasets are intentionally not published
in the skill package. The repository does include the EarthScope
`mseedindex` source tree under `assets/mseedindex/` so agents can build it on
the user's machine. Small templates such as `assets/stations_template.csv` and
`assets/label_mapping_template.json` are included for new dataset runs.

## Quick Start

Check dependencies and build or locate the bundled `mseedindex` binary:

```bash
python scripts/seismicx_dataset.py check-deps
python scripts/seismicx_dataset.py install-mseedindex
```

Convert waveform files to miniSEED and create a waveform database:

```bash
python scripts/seismicx_dataset.py convert-waveforms \
  --input <raw_waveforms> \
  --output-dir work/mseed

python scripts/seismicx_dataset.py index-mseed \
  --input work/mseed \
  --db work/waveform.sqlite \
  --reset
```

Normalize earthquake catalog or annotation labels:

```bash
python scripts/seismicx_dataset.py normalize-labels \
  --input <catalog_or_annotations> \
  --output work/labels.canonical.json
```

If the catalog format is unusual, write a mapping JSON after inspecting
representative records, then rerun:

```bash
python scripts/seismicx_dataset.py normalize-labels \
  --input <catalog> \
  --mapping mapping.json \
  --output work/labels.canonical.json
```

Use `assets/label_mapping_template.json` as a starting point for custom
catalogs and `assets/stations_template.csv` for station metadata.

Build an event-oriented earthquake dataset:

```bash
python scripts/seismicx_dataset.py make-hdf5 event \
  --catalog work/labels.canonical.json \
  --mseed-index-db work/waveform.sqlite \
  --output work/seismicx_event.h5 \
  --event-window-before 60 \
  --event-window-after 180
```

Build a continuous-waveform dataset:

```bash
python scripts/seismicx_dataset.py make-hdf5 continuous \
  --waveform-input work/mseed \
  --station-csv stations.csv \
  --output work/seismicx_continuous.h5 \
  --split-interval hour
```

Index and read produced HDF5 datasets:

```bash
python scripts/seismicx_dataset.py build-hdf5-index \
  --h5 "work/seismicx_*.h5" \
  --db work/dataset_index.sqlite \
  --reset

python scripts/seismicx_dataset.py example-dataloader \
  --h5 "work/seismicx_*.h5" \
  --index-db work/dataset_index.sqlite \
  --n-samples 3
```

## Dataset Standard

Both event and continuous datasets use the same top-level HDF5 contract:

```text
/
  information/
  data/
    {sample_id}/
      {station_id}/
        waveform/
          {channel}/
            {seg_id}
        label/
```

Use `references/standard_hdf5_schema.md` as the field contract. Important
rules:

- Keep `information`, `data`, `event`, `station`, `waveform`, `channel`,
  `trace`, and `label` as the layer `type` values.
- Use standard names such as `source_origintime`,
  `source_longitude_deg`, `source_latitude_deg`, `source_depth_km`,
  `source_magnitude`, `seg_start_time`, and `sample_rate`.
- Store missing strings as `"none"` and missing numeric values as `NaN`.
- For event datasets, store picks as labels and use explicit event windows for
  waveform extraction; do not cut waveform snippets from pick arrival times
  unless the user explicitly requests that behavior.

## Related Tools

- [EarthScope mseedindex](https://github.com/EarthScope/mseedindex)
- [ObsPy](https://github.com/obspy/obspy)
- [seismological-ai-tools](https://github.com/cangyeone/seismological-ai-tools)
- [SeismicX Catalog Skill](https://github.com/cangyeone/seismicx-catalog-skill)

## Maintainers

- Xin Liu: xinliu_geo@outlook.com
- Yuqi Cai: caiyuqiming@foxmail.com
- Ziye Yu: yuziye@hotmail.com
