# SeismicX Dataset Claude Code Context

This repository is a generic agent skill for SeismicX dataset production, not
a Claude-only project. Use `SKILL.md` as the canonical workflow and treat this
file as a short Claude Code entrypoint.

## What To Do

- For waveform conversion and miniSEED indexing:

```bash
python scripts/seismicx_dataset.py install-mseedindex
python scripts/seismicx_dataset.py convert-waveforms --input <raw_waveforms> --output-dir work/mseed
python scripts/seismicx_dataset.py index-mseed --input work/mseed --db work/waveform.sqlite --reset
```

- For labels and event datasets:

```bash
python scripts/seismicx_dataset.py normalize-labels --input <catalog_or_annotations> --output work/labels.canonical.json
python scripts/seismicx_dataset.py make-hdf5 event --catalog work/labels.canonical.json --mseed-index-db work/waveform.sqlite --output work/seismicx_event.h5
```

- For continuous waveform datasets:

```bash
python scripts/seismicx_dataset.py make-hdf5 continuous --waveform-input work/mseed --station-csv stations.csv --output work/seismicx_continuous.h5 --split-interval hour
```

- For reading and smoke testing:

```bash
python scripts/seismicx_dataset.py build-hdf5-index --h5 "work/seismicx_*.h5" --db work/dataset_index.sqlite --reset
python scripts/seismicx_dataset.py example-dataloader --h5 "work/seismicx_*.h5" --index-db work/dataset_index.sqlite --n-samples 3
```

## Reference Routing

- `references/standard_hdf5_schema.md` for HDF5 hierarchy and required field
  names.
- `references/catalog_normalization.md` for unknown earthquake catalog and
  annotation formats.
- `references/mseedindex_workflow.md` for EarthScope `mseedindex`, waveform
  conversion, miniSEED database creation, and query workflows.

## Guardrails

- Keep raw waveform archives, generated datasets, generated SQLite databases,
  local virtual environments, compiled binaries, and large reference data out
  of git.
- Use the same HDF5 hierarchy for event and continuous datasets.
- Store event picks as label vectors; do not derive waveform windows from
  phase arrivals unless the user explicitly requests it.
- Preserve unmapped catalog fields in `user_defined`.
- Validate script edits with `python -m py_compile scripts/seismicx_dataset.py`.
