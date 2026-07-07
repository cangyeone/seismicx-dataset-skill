# SeismicX Dataset Agent Instructions

This repository is an agent-agnostic skill for standardized seismological AI
dataset production. Use it when a user asks to convert waveform archives,
build miniSEED indexes, normalize earthquake annotations, produce standardized
HDF5 event or continuous datasets, build dataset indexes, or read generated
datasets with a dataloader.

## Canonical Workflow

- Read `SKILL.md` first; it is the source of truth for the workflow.
- Load `references/standard_hdf5_schema.md` before writing HDF5 or adapting
  field names.
- Load `references/catalog_normalization.md` before converting unknown catalog
  or label formats.
- Load `references/mseedindex_workflow.md` before converting waveform files,
  compiling EarthScope `mseedindex`, building miniSEED SQLite databases, or
  reading indexed waveforms.

## Core Commands

```bash
python scripts/seismicx_dataset.py check-deps
python scripts/seismicx_dataset.py install-mseedindex
python scripts/seismicx_dataset.py convert-waveforms --input <raw_waveforms> --output-dir work/mseed
python scripts/seismicx_dataset.py index-mseed --input work/mseed --db work/waveform.sqlite --reset
python scripts/seismicx_dataset.py normalize-labels --input <catalog_or_annotations> --output work/labels.canonical.json
python scripts/seismicx_dataset.py make-hdf5 event --catalog work/labels.canonical.json --mseed-index-db work/waveform.sqlite --output work/seismicx_event.h5
python scripts/seismicx_dataset.py make-hdf5 continuous --waveform-input work/mseed --station-csv stations.csv --output work/seismicx_continuous.h5 --split-interval hour
python scripts/seismicx_dataset.py build-hdf5-index --h5 "work/seismicx_*.h5" --db work/dataset_index.sqlite --reset
python scripts/seismicx_dataset.py example-dataloader --h5 "work/seismicx_*.h5" --index-db work/dataset_index.sqlite --n-samples 3
```

Use event mode for earthquake samples with labels and optional event-window
waveform extraction. Use continuous mode for long waveform archives that should
be split by hour, day, or another fixed interval.

## Guardrails

- Do not commit raw waveform archives, generated HDF5 files, generated SQLite
  indexes, compiled binaries, local virtual environments, or large reference
  datasets.
- Keep the EarthScope `mseedindex` source under `assets/mseedindex`; build
  products are ignored by git.
- Keep both dataset modes on the same HDF5 hierarchy and standard field names.
- Preserve unrecognized catalog fields under `user_defined` during label
  normalization.
- Record dependencies, source paths, label mapping assumptions, event windows,
  split intervals, and validation commands in final run notes.

## Validation

Before finishing changes, run:

```bash
python -m py_compile scripts/seismicx_dataset.py
python scripts/seismicx_dataset.py install-mseedindex --no-build
```

If the skill structure changed, also run the local skill validator when
available:

```bash
python /Users/yuziye/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```
