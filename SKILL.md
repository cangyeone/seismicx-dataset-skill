---
name: seismicx-dataset
description: Build and validate seismological AI datasets, or answer questions about how to create, organize, label, quality-mark, and read earthquake or continuous waveform datasets. Use for waveform conversion, EarthScope mseedindex, catalog normalization, standardized HDF5 and JSON releases, dataset SQLite indexes, dataloaders, and dataset-making guidance in OpenCode, Claude Code, or Codex.
---

# SeismicX Dataset

Produce datasets and explain dataset-making using the 2026-08-31 revision draft
of the seismological AI dataset specification. Its cover still says
DB/T XXXXX-XXXX; do not describe it as a published, numbered industry standard.

## Questions or execution

For questions such as "How do I make a seismic dataset?", "如何做地震数据集？",
"Which mode should I choose?", or "What does trace_quality mean?", answer
directly using [references/dataset_questions.md](references/dataset_questions.md)
and the relevant technical reference. Reply in the user's language.
Do not build, install dependencies, or modify files just because the user
asks how. Explicit skill invocation is optional for questions and actions.

When the user asks to make, convert, validate, or fix a dataset, execute that
workflow. For a mixed request, explain the relevant choice and perform the
requested work. Infer mode and parameters when supported by the inputs;
ask only about missing decisions that materially affect the result.
Distinguish draft requirements, this profile's implementation choices, and
scientific recommendations.

## First steps for production

1. Inspect waveform paths, catalogs, station metadata, indexes and intended
   use. Select event or continuous mode with the user when it is unclear.
2. Read [references/standard_hdf5_schema.md](references/standard_hdf5_schema.md)
   before writing HDF5 or adapting any field.
3. Read [references/catalog_normalization.md](references/catalog_normalization.md)
   for unfamiliar catalogs/labels. Use the model to infer fields, units, time
   standards and repeated blocks; preserve unknown information in user_defined.
4. Read [references/mseedindex_workflow.md](references/mseedindex_workflow.md)
   before waveform conversion, compilation, indexing or indexed reading.
5. Establish verified units, time conventions, sampling windows/splits and the
   data owner's license. Use a dedicated release directory separate from
   intermediate miniSEED/catalog files. Do not assign the skill's software
   license to a user's data or assume an unknown timezone is UTC.
6. Use scripts/seismicx_dataset.py for deterministic work. Check subcommand
   --help when parameters are uncertain.

## Waveforms and labels

```bash
python scripts/seismicx_dataset.py check-deps
python scripts/seismicx_dataset.py install-mseedindex
python scripts/seismicx_dataset.py convert-waveforms --input RAW_DIR --output-dir work/mseed --strict
python scripts/seismicx_dataset.py index-mseed --input work/mseed --db work/waveform.sqlite --reset
python scripts/seismicx_dataset.py normalize-labels --input CATALOG --output work/labels.canonical.json
```

For ambiguous catalogs inspect representative records, produce an explicit
mapping or a source-specific adapter, then normalize again. A column mapping
does not parse arbitrary block grammars or convert units automatically.
Use seismicx_canonical_labels_v1 as input interchange. The source workspace
mini_data/data/label/annotations_mini_two_hours.json is a reference for
years/days/events/stations/picks, not the only accepted catalog shape.

## Event dataset

```bash
python scripts/seismicx_dataset.py make-hdf5 event \
  --catalog work/labels.canonical.json \
  --mseed-index-db work/waveform.sqlite \
  --output release/event/seismicx_event.h5 \
  --license-file DATA_LICENSE --unit counts \
  --event-window-before 60 --event-window-after 180
```

Replace counts with verified physical units. Extract from the resolved UTC
source_origintime plus source_origintime_ref when present, using explicit
windows. Do not derive waveform cuts from pick arrivals unless the user
requests and documents a different sampling scheme. Picks remain labels.
Optional --station-csv supplements missing station metadata.

## Continuous dataset

```bash
python scripts/seismicx_dataset.py make-hdf5 continuous \
  --waveform-input work/mseed --station-csv stations.csv \
  --output release/continuous/seismicx_continuous.h5 \
  --license-file DATA_LICENSE --unit counts --split-interval hour
```

Use hour, day, custom, or single. Optional --catalog attaches labels to existing
windows without changing waveform cuts. Both modes support --trace-quality
for an optional full-channel quality timeline; see the schema reference for
alignment and memory limits. No calibration detector is included.

## HDF5 invariants

- Fixed groups: information, data, waveform, label. Repeated layers use
  type=event/station/channel/trace. Use one hierarchy for both modes.
- Event sample attributes follow D.2; continuous sample attributes follow D.1.
  Continuous windows must not acquire fictitious earthquake origins or magnitudes.
- Read physical information from attributes, not path names or identifiers.
- Use unique standard English field names without duplicate aliases.
  Standard lists are native HDF5 arrays, numeric metadata/labels are float64,
  counts are int64, and quality_metric is uint64.
- Required missing strings are "none"; missing numbers are NaN. JSON represents
  missing numbers as null. Do not invent metadata to silence warnings.
- Missing waveforms are separate uninterrupted segments, never interpolated
  or zero-filled. Keep overlapping original records; sort seg_id from zero.
- Optional trace_quality is unsegmented and excluded from waveform counts/indexes.
- Preserve every annotation source and review result as aligned label vectors.
  Use manual_{person_or_agency} or automatic_{method}; unknown method is none.
- Quality identification must not modify original data or automatically delete
  records. Passing schema validation is not scientific quality control.
- Export hierarchical JSON directly from HDF5 for both modes; it is mandatory
  for continuous releases. Include LICENSE and checksums for all release files.

## Read, package and validate

```bash
python scripts/seismicx_dataset.py build-hdf5-index --h5 'release/event/*.h5' --db release/event/dataset_index.sqlite --reset
python scripts/seismicx_dataset.py example-dataloader --h5 'release/event/*.h5' --index-db release/event/dataset_index.sqlite --n-samples 3
python scripts/seismicx_dataset.py package-dataset --h5 'release/event/*.h5'
python scripts/seismicx_dataset.py validate-hdf5 --h5 'release/event/*.h5' --release
```

Replace paths for continuous releases. Copy supplied StationXML after checking
station/channel IDs and epochs against HDF5. Add run notes before the final
package-dataset call, so checksums cover notes, SQLite and optional StationXML.

Require release validation to succeed. Separate errors from permitted
missing-value warnings; never call failed output compliant. Report source
paths, dependencies, mappings and unit/time assumptions, sampling windows,
split intervals, quality methods and validation results.

For script edits run:

```bash
python -m py_compile scripts/seismicx_dataset.py scripts/seismicx_standard.py
python scripts/seismicx_dataset.py install-mseedindex --no-build
python -m pytest -q tests/test_standard.py
```

For skill edits also run the local skill-creator quick_validate.py when
available. No production commands or dependency setup are needed for Q&A.
