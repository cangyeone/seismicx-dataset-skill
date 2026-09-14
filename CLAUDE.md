# SeismicX Dataset Claude Code Context

This repository is a generic agent skill for SeismicX dataset production, not
a Claude-only project. Use `SKILL.md` as the canonical workflow and treat this
file as a short Claude Code entrypoint.

For dataset-making questions, read `references/dataset_questions.md` and answer
in the user's language. Do not start a build or install tools for a how-to
question. Both questions and production requests can use natural language
without an explicit skill name.

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
python scripts/seismicx_dataset.py make-hdf5 event --catalog work/labels.canonical.json --mseed-index-db work/waveform.sqlite --output release/seismicx_event.h5 --license-file DATA_LICENSE --unit counts
```

- For continuous waveform datasets:

```bash
python scripts/seismicx_dataset.py make-hdf5 continuous --waveform-input work/mseed --station-csv stations.csv --output release/seismicx_continuous.h5 --license-file DATA_LICENSE --unit counts --split-interval hour
```

- For reading and smoke testing:

```bash
python scripts/seismicx_dataset.py build-hdf5-index --h5 "release/seismicx_*.h5" --db release/dataset_index.sqlite --reset
python scripts/seismicx_dataset.py example-dataloader --h5 "release/seismicx_*.h5" --index-db release/dataset_index.sqlite --n-samples 3
python scripts/seismicx_dataset.py package-dataset --h5 'release/seismicx_*.h5'
python scripts/seismicx_dataset.py validate-hdf5 --h5 'release/seismicx_*.h5' --release
```

## Reference Routing

- `references/standard_hdf5_schema.md` for HDF5 hierarchy and required field
  names under the 2026-08-31 revision draft, including separate D.1/D.2 samples.
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
- Preserve gaps and overlaps; do not interpolate missing waveforms.
- Supply the data owner's LICENSE, export hierarchical JSON, and finalize
  all sidecars with package-dataset after adding indexes and run notes.
- Require validate-hdf5 --release to succeed before calling output validated.
- Validate script edits with `python -m py_compile scripts/seismicx_dataset.py scripts/seismicx_standard.py`.
