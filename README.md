![SeismicX Dataset](logo.png)

# SeismicX Dataset Skill

SeismicX Dataset Skill helps an AI coding agent build standardized
seismological AI datasets from waveform files, miniSEED archives, earthquake
catalogs, phase-pick annotations, and continuous waveform directories.

It is designed for OpenCode, Codex, Claude Code, and other agents that can read
Markdown instructions and run local scripts.

## Install In Any Agent Tool

This repository is an agent skill. You can install it through any coding agent
that can download a GitHub repository and register or copy a skill directory.

In OpenCode, Codex, Claude Code, or another agent tool, you can type:

```text
Please download https://github.com/cangyeone/seismicx-dataset-skill and install it as an agent skill for making seismological datasets.
```

If your tool needs a more explicit instruction, type:

```text
Please download cangyeone/seismicx-dataset-skill from GitHub, install it as an agent-readable skill, and make it available for future seismic dataset-building tasks. Use SKILL.md, AGENTS.md, or CLAUDE.md depending on what this tool supports.
```

After installation, the skill name is:

```text
$seismicx-dataset
```

The repository also includes `AGENTS.md` for OpenCode-style agents,
`CLAUDE.md` for Claude Code, and `SKILL.md` for Codex-style skill loading.

## Use In Any Agent Tool

Put your waveform files, station metadata, catalogs, or annotation files in the
current project directory. Then ask your agent in plain language.

General request:

```text
Please make a seismological dataset from the data in the current directory.
```

Another good general request:

```text
Please inspect the current directory and build a standardized SeismicX HDF5 dataset from the available waveform, station, catalog, and label files.
```

For an earthquake-event dataset, type:

```text
Please build an event-style earthquake dataset from the waveform files and earthquake catalog in the current directory.
```

For a continuous waveform dataset, type:

```text
Please build a continuous seismological waveform dataset from the data in the current directory and split it by hour.
```

For an unknown catalog or label format, type:

```text
Please inspect the catalog format in the current directory, infer the fields, convert the labels to canonical JSON, and build the dataset.
```

For waveform conversion and miniSEED indexing only, type:

```text
Please convert the waveform files in the current directory to miniSEED and build a searchable mseedindex SQLite database.
```

Explicit invocation is optional. If your agent supports skill names and you
want to force this skill, prefix the request with:

```text
Use $seismicx-dataset.
```

## What The Agent Will Do

When you ask an agent to use this skill, it should:

1. Inspect the current directory and identify waveform files, station metadata,
   catalogs, annotation files, and existing indexes.
2. Ask whether you want an event-style dataset or a continuous waveform dataset
   if the directory does not make that clear.
3. Convert waveform files to miniSEED when needed.
4. Build an EarthScope `mseedindex` SQLite database for miniSEED waveform
   search and reading.
5. Infer and normalize earthquake catalogs or phase-pick labels into canonical
   JSON.
6. Write a standardized SeismicX HDF5 dataset.
7. Build a SQLite index for the generated HDF5 dataset.
8. Run a small dataloader smoke test so the dataset can be read back.

## What This Skill Can Build

### Event-Style Earthquake Dataset

Use this when you have earthquake catalogs, events, picks, or labels.

The dataset stores:

- Event metadata.
- Station metadata.
- Waveform windows around each event when waveform data is available.
- Phase picks and annotation information as labels.
- A unified HDF5 hierarchy following the SeismicX dataset standard.

### Continuous Waveform Dataset

Use this when you have long waveform archives and want model-ready continuous
waveform samples.

The dataset stores:

- Continuous waveform segments split by hour, day, or a custom time interval.
- Station and channel metadata.
- Empty label groups, so the continuous dataset has the same structure as the
  event dataset.
- A SQLite index and dataloader-compatible access path.

## Expected Input Files

The skill can work with different project layouts. Common inputs include:

- Waveform files: miniSEED, MSEED, SAC, SEED, GCF, SEGY, SU, and other
  ObsPy-readable formats.
- Station metadata: CSV files with network, station, location, latitude,
  longitude, and elevation.
- Earthquake catalogs: JSON, JSONL, CSV, TSV, or text phase catalogs.
- Annotation files: files similar to
  `mini_data/data/label/annotations_mini_two_hours.json`.
- Existing miniSEED indexes or HDF5 dataset indexes.

If the catalog format is not standard, the agent should inspect examples,
infer the meaning of the fields, and preserve unmapped information in
`user_defined`.

## Output Files

A typical run produces:

- `labels.canonical.json`: normalized event and pick labels.
- `waveform.sqlite`: EarthScope `mseedindex` database for miniSEED files.
- `seismicx_event.h5` or `seismicx_continuous.h5`: standardized HDF5 dataset.
- `dataset_index.sqlite`: SQLite index for the HDF5 waveform datasets.
- `LICENSE` and `md5sum.txt`: dataset sidecar files.

## Dataset Standard

Both dataset types use the same HDF5 structure:

```text
/
  information/
  data/
    {sample_id}/
      {station_id}/
        waveform/
          {channel}/
            {segment_id}
        label/
```

The skill uses standard field names such as:

- `source_origintime`
- `source_longitude_deg`
- `source_latitude_deg`
- `source_depth_km`
- `source_magnitude`
- `seg_start_time`
- `sample_rate`

Missing strings are stored as `"none"`. Missing numeric values are stored as
`NaN`.

## Advanced Command-Line Use

Most users should ask their agent in plain language. The examples below are for
debugging or manual runs.

Check dependencies and build the bundled EarthScope `mseedindex` tool:

```bash
python scripts/seismicx_dataset.py check-deps
python scripts/seismicx_dataset.py install-mseedindex
```

Convert waveforms and build a miniSEED index:

```bash
python scripts/seismicx_dataset.py convert-waveforms --input <raw_waveforms> --output-dir work/mseed
python scripts/seismicx_dataset.py index-mseed --input work/mseed --db work/waveform.sqlite --reset
```

Normalize labels:

```bash
python scripts/seismicx_dataset.py normalize-labels --input <catalog_or_annotations> --output work/labels.canonical.json
```

Build an event dataset:

```bash
python scripts/seismicx_dataset.py make-hdf5 event --catalog work/labels.canonical.json --mseed-index-db work/waveform.sqlite --output work/seismicx_event.h5
```

Build a continuous dataset:

```bash
python scripts/seismicx_dataset.py make-hdf5 continuous --waveform-input work/mseed --station-csv stations.csv --output work/seismicx_continuous.h5 --split-interval hour
```

Index and test the generated HDF5 dataset:

```bash
python scripts/seismicx_dataset.py build-hdf5-index --h5 "work/seismicx_*.h5" --db work/dataset_index.sqlite --reset
python scripts/seismicx_dataset.py example-dataloader --h5 "work/seismicx_*.h5" --index-db work/dataset_index.sqlite --n-samples 3
```

## Repository Layout

```text
SKILL.md                  Main skill instructions
AGENTS.md                 OpenCode and generic agent entrypoint
CLAUDE.md                 Claude Code entrypoint
agents/openai.yaml        Skill UI metadata
scripts/seismicx_dataset.py
references/               Detailed schema and workflow notes
assets/mseedindex/        Bundled EarthScope mseedindex source
assets/stations_template.csv
assets/label_mapping_template.json
README.md
LICENSE
```

Large waveform archives, generated datasets, generated SQLite databases,
compiled binaries, local virtual environments, and local reference datasets
should not be committed to this repository.

## Related Tools

- [EarthScope mseedindex](https://github.com/EarthScope/mseedindex)
- [ObsPy](https://github.com/obspy/obspy)
- [seismological-ai-tools](https://github.com/cangyeone/seismological-ai-tools)
- [SeismicX Catalog Skill](https://github.com/cangyeone/seismicx-catalog-skill)

## Maintainers

- Xin Liu: xinliu_geo@outlook.com
- Yuqi Cai: caiyuqiming@foxmail.com
- Ziye Yu: yuziye@hotmail.com
