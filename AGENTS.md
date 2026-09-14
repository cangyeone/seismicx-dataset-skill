# SeismicX Dataset Agent Instructions

This repository is an agent-agnostic skill for standardized seismological AI
dataset production. Use it when a user asks to convert waveform archives,
build miniSEED indexes, normalize earthquake annotations, produce standardized
HDF5 event or continuous datasets, build dataset indexes, or read generated
datasets with a dataloader.

Also use it to answer questions about making seismological datasets, selecting
event versus continuous mode, interpreting the standard, labels, quality flags,
release files and dataloaders. For how-to questions, read
`references/dataset_questions.md` and answer without starting a build or
installing dependencies. Execute when the user requests an action.

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
python scripts/seismicx_dataset.py make-hdf5 event --catalog work/labels.canonical.json --mseed-index-db work/waveform.sqlite --output release/seismicx_event.h5 --license-file DATA_LICENSE --unit counts
python scripts/seismicx_dataset.py make-hdf5 continuous --waveform-input work/mseed --station-csv stations.csv --output release/seismicx_continuous.h5 --license-file DATA_LICENSE --unit counts --split-interval hour
python scripts/seismicx_dataset.py build-hdf5-index --h5 "release/seismicx_*.h5" --db release/dataset_index.sqlite --reset
python scripts/seismicx_dataset.py example-dataloader --h5 "release/seismicx_*.h5" --index-db release/dataset_index.sqlite --n-samples 3
python scripts/seismicx_dataset.py package-dataset --h5 'release/seismicx_*.h5'
python scripts/seismicx_dataset.py validate-hdf5 --h5 'release/seismicx_*.h5' --release
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
- Keep both modes on the same hierarchy and standard field names, using
  D.1 continuous or D.2 event sample attributes from the 2026-08-31 draft.
- Preserve gaps as separate segments and overlaps as original records.
  Never interpolate missing data or count trace_quality as a waveform.
- Supply a data-owner LICENSE, export hierarchical JSON and refresh all
  checksums with package-dataset after adding release files.
- Require validate-hdf5 --release to pass; report permitted missing-value
  warnings and unresolved scientific metadata separately.
- Preserve unrecognized catalog fields under `user_defined` during label
  normalization.
- Record dependencies, source paths, label mapping assumptions, event windows,
  split intervals, and validation commands in final run notes.

## Validation

Before finishing changes, run:

```bash
python -m py_compile scripts/seismicx_dataset.py scripts/seismicx_standard.py
python scripts/seismicx_dataset.py install-mseedindex --no-build
```

If the skill structure changed, also run the local skill validator when
available:

```bash
python /Users/yuziye/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```
