# Dataset Questions and Answers

Use this reference for explanations, planning and troubleshooting. Answer in
the user's language and adapt depth to their question. A how-to question is
not permission to build files or install tools. For exact field requirements,
consult standard_hdf5_schema.md; it summarizes the supplied 2026-08-31 draft.

## How do I make a seismological dataset?

Start with the task: event detection, phase picking, polarity, location,
magnitude, or continuous monitoring. Gather waveform records, station metadata,
and whatever event/pick annotations are available. Choose event windows or
fixed continuous windows. Normalize readable waveforms to miniSEED, create
an EarthScope mseedindex database, map catalog fields into canonical JSON,
write HDF5 with the shared hierarchy, build a dataset index, test the
dataloader, then export and validate the release files.

Explain the workflow before showing commands. A useful Chinese answer begins:
“先确定要做事件型还是连续波形型数据集，再准备波形、台站信息和已有标注。
整理字段和时间单位后，生成 HDF5、JSON、索引及发布校验文件。”
Only ask about task, available files and mode when needed to tailor the answer.
Do not require a sample upload to give an overview.

## Event or continuous?

| Mode | Appropriate input/use | Sampling | Sample metadata |
| --- | --- | --- | --- |
| Event | Catalogued earthquakes, picking/polarity/location examples | Explicit windows around resolved origin time | Draft D.2 |
| Continuous | Long archives, monitoring/detection and unlabeled pretraining | Hour/day/custom fixed windows | Draft D.1 |

Both use the same station/waveform/channel/trace and label hierarchy.
Continuous mode may carry labels without letting picks define its cuts.
Event samples are not automatically P-pick-centered clips. Window size,
sample rate and training splits are scientific choices, not numbers mandated
by this draft.

## What is the minimum input? Can I work without labels?

Need readable waveforms, their network/station/channel/timing identifiers,
and a data-owner-supplied license for a completed release. Station location,
elevation and depth fields must exist, but unknown numerical values can be
NaN and must be disclosed. Continuous data may have empty label vectors.
For origin-window extraction, event data needs a resolved origin/reference
time and matching station codes. Unknown events, coordinates, magnitudes,
or picks must not be fabricated. Unlabeled is not automatically noise.

## Which files should I prepare?

Waveforms in ObsPy-readable formats; station CSV and optional StationXML;
event catalogs and phase/polarity labels in JSON, CSV, TSV or source text;
license terms and available processing/QC notes. The bundled parser does not
read every proprietary format: identify a supported reader or write a narrow
adapter, retaining the original files and mapping assumptions.

## My catalog format is different. Is manual conversion necessary?

The agent can inspect example rows, units, headers, time conventions and
repeated blocks and infer a mapping. Column aliases/mapping JSON handle flat
tables; unfamiliar nested/block grammars need an explicit adapter. Preserve
unknown fields and raw annotation source names in user_defined. Convert metres
to kilometres or local time to UTC only from established evidence. Validate
several records before a full run. Do not promise that --mapping alone parses
any arbitrary text file.

## Why both canonical JSON and release JSON?

Canonical JSON is normalized input: events -> stations -> picks.
Release JSON is exported from the actual HDF5 hierarchy and contains dataset
identification, channel metadata, sample metadata and labels. It is required
for continuous releases; this skill generates it for event releases as well.
Use null for missing numbers in JSON and NaN in HDF5.

## How are gaps, overlaps and poor-quality records handled?

Keep raw values and split at missing/masked/nonfinite samples; do not interpolate
or zero-fill HDF5 waveform data. Preserve overlaps. Sort segment IDs by start
time. Record quality issues through flags and provenance; do not discard a
record solely because it has a quality flag.

Optional trace_quality is a full channel timeline: 1 = missing, 2 = overlap,
3 = calibration. Built-in generation detects gaps/overlaps and uses a documented
custom 0 for an observed sample whose other quality is unassessed. It does not
detect calibration, spikes or clipping. A quality timeline requires one aligned
sampling grid. It is not a waveform segment and must not enter the waveform index.

## What about repeated labels and unknown annotation methods?

Keep every source as a separate aligned vector entry, including reviewed or
reprocessed results. Methods use manual_{person_or_agency} or automatic_{method}.
Unknown source is none with the original value retained. Do not treat an
unknown score as 1, a missing SNR as 0, or label disagreement as grounds to
silently replace one annotation with another.

## How do I split training, validation and test data?

As a scientific recommendation, group related examples by event and/or time
period and station/network, according to intended generalization. Keep
overlapping windows, duplicate waveform records and alternate labels for the
same observation together. Estimate preprocessing statistics using training
data only. Record split keys and seed. The draft permits nested data groups
but does not mandate a train/test ratio or automatic split algorithm; this
CLI does not automatically assign training splits.

## How do I read it with a dataloader?

Build the HDF5 SQLite index, then run example-dataloader (optionally with
--use-torch). SeismicXHDF5Dataset yields one segment with waveform, trace attrs,
station/sample attrs and all station labels. If quality exists, it returns
the full trace_quality timeline plus the segment's offset into it. It does
not automatically align three components, crop station labels to a segment,
resample, pad batches, or create model targets. Model-specific collation must
make those choices explicitly while preserving validity masks.

## What makes a release valid?

HDF5 with required attributes and hierarchy, hierarchical JSON for continuous
data, independent UTF-8 LICENSE, and checksums covering all other released
files. StationXML is optional. This draft mentions both md5sum.txt and
checksums.md5; the tool writes identical manifests under both names and
excludes the manifests themselves from recursive hashing.

Run package-dataset after adding SQLite, StationXML or run notes, then run
validate-hdf5 --release. Errors fail validation; allowed missing metadata is
reported as warnings. A successful structural check does not certify scientific
quality, correctness of all annotations, response metadata, or ownership rights.

## Common problems

| Symptom | What to check |
| --- | --- |
| No waveforms match events | UTC conversion, relative origin offset, NSLC codes, blank location, window and file coverage |
| NaN station coordinates | Supply matching station CSV/StationXML; never use zeros as guessed coordinates |
| Quality timeline rejects a channel | Sampling rates, time-grid alignment, chosen split size and max-quality-samples |
| Checksum fails after building an index | Run package-dataset again after all release files are finalized |
| Magnitude list mismatch | Align types, values and errors without inventing pairings |
| Legacy HDF5 fails validation | Regenerate using the v2 profile; metadata renaming alone is insufficient |
| An instrument response is missing | Preserve counts/unknown units and document it; do not claim calibrated displacement/velocity |

## Natural-language examples

- “如何做一个地震学数据集？需要准备哪些数据？”
- “事件型和连续波形型有什么区别？我应该选哪一种？”
- “规范里 trace_quality、quality_flag 和 quality_metric 有什么区别？”
- “连续数据没有标注也能做吗？JSON 里要包含什么？”
- “How should I prepare an earthquake dataset without leaking events across splits?”
- “Explain why my release failed validation and how to fix the reported fields.”

"Explain how to fix" still asks for guidance. An explicit action request such
as "Please fix these files" leads from explanation into file changes.
