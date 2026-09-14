# Standard HDF5 Schema

Source: user-supplied `修订版《测震人工智能数据集规范》行业标准-20260831(2).docx`,
draft completed 2026-08-31, sections 5-8 and normative appendices A-D.
The cover still says `DB/T XXXXX-XXXX`; do not call it a published, numbered
industry standard. This supersedes the earlier `数据集标准.docx`.
Executable profile: `seismicx_standard_hdf5_v2`,
`standard_revision="2026-08-31-draft"`. Installation does not need the DOCX.

## Hierarchy (section 6.2, figure 2, appendix E)

```text
/                                      A.1 dataset attributes
  information/                         type="information"
    {station_key}/                     type="station", A.2
  data/                                type="data"
    {sample_key}/                      type="event", D.1 OR D.2
      {station_key}/                    type="station", A.2
        waveform/                      type="waveform"
          {channel_key}/               type="channel", A.3
            0                          type="trace", waveform vector, B.1
            1                          type="trace", waveform vector, B.1
            trace_quality              optional type="trace", full timeline, A.4
        label/                         type="label"
          phase_name                   type="label", string vector
          phase_arrival_time           type="label", string vector
          phase_name_prob              type="label", float vector
          phase_name_snr               type="label", float vector
          polarity_type                type="label", string vector
          polarity_clarity             type="label", string vector
          phase_annotation_method      type="label", string vector
          polarity_annotation_method   type="label", string vector
          user_defined                 type="label", JSON-string vector
```

`information`, `data`, `waveform`, and `label` are fixed group names.
Repeated event/station/channel/trace objects have unique association keys and
fixed type values. Do not insert extra literal event/station/trace containers:
that changes the levels in figure 2. Nested data groups are permitted by
6.2.2; identify ancestors by attributes, not fixed path depth. The writer
uses a single /data group.

Section 7.2.3 says identifiers serve associations, not physical information.
Even when keys resemble dates or network.station.location (suggested in the
appendices), read times, coordinates, network and channel from attributes.
Event keys are UUIDs derived from catalog identifiers; original identifiers
remain in event_id. Never recover origin time from a path.

## Types, missing values and units (section 7.2.2)

Required attributes below must exist. Missing strings are "none"; missing
numbers are float64 NaN. Report these as validation warnings. Do not invent
zero burial depth, manual annotation sources, or physical units. Optional
fields may be absent; empty optional lists are permitted.

Profile choices: UTF-8, case-sensitive fields/values, maximum 65,535 UTF-8
bytes per string/list element, float64 numeric metadata and labels, int64
counts/identifiers, uint64 quality_metric, and preserved waveform dtype.
Unknown integer counts use float64 NaN as a documented exception; zero means
a known zero. These precision/length choices implement section 7.2.2 but are
not exact limits prescribed by the draft. No truncation or rounding is used.

Lists are native HDF5 arrays, not JSON text. JSON is for user_defined
extensions. In JSON files, numeric missing values become null and map back to
NaN. Never emit invalid JSON NaN/Infinity tokens. Do not write duplicate
aliases such as sampling_rate, starttime, lat, lon, or mag.

Coordinates use degrees, positive east/north; station elevation/depth use
metres; source depth/distances/uncertainties use kilometres; timing errors
use seconds; sample_rate uses hertz. Supply verified waveform units via
--unit. Format conversion does not remove instrument response or establish
physical units. Record source units and conversion formulas in provenance.

## A.1: dataset identification

Required: name (string), version (string), license (filename LICENSE),
md5 (checksum filename).

Optional: processing_time (YYYY-MM-DD), agency/author (string lists),
num_stations/num_events (int), annotation_types (string list),
annotation_counts (int list aligned with annotation_types),
description (string), file_size (string including unit).

num_events counts earthquake samples, not continuous windows. Count sample
groups for continuous sample count. Profile extensions include format,
dataset_mode, standard_revision and user_defined processing provenance.

## A.2: stations

Required: type="station", station_id (unique string),
station_longitude_deg, station_latitude_deg, station_elevation_m,
station_depth_m (float).

Optional: station_network, station_station, station_location (strings),
station_channel_list (string list), station_area, station_agency,
station_remark (strings).

A.2 refers to location codes 00-19 and DB/T 86-2021. Preserve actual codes.
A genuinely blank miniSEED location is represented by -- in this profile,
and translated to an empty location when querying mseedindex.
Instrument models, sensor/digitizer IDs, response and epochs belong in
StationXML when provided; other metadata survives in user_defined.
Do not invent response metadata or relocate unknown stations.

## A.3: channels

Required: type="channel", station_channel_id (string matching the station
channel list), num_of_seg (int), start_time (string or float).
Optional: end_time (string or float), continuity_rate (float, 0-1),
orientation (float list [azimuth_deg,dip_deg]), user_defined (JSON string).

Continuity is the union of half-open observed sample intervals divided by
the observed channel span, counting overlaps once. This method is recorded
in user_defined; it makes no availability claim outside the observed span.

## B.1: waveform segments

Required: type="trace", seg_id (int, contiguous from zero in start-time order),
unit (string), sample_rate (float), seg_start_time (string or float).
Optional: seg_end_time (string or float), quality_flag (character),
quality_metric (uint64), quality_metric_description (string).

Each dataset is one uninterrupted 1-D waveform. Gaps/masked/nonfinite values
produce separate segments. Never interpolate or zero-fill missing waveforms
(section 5.3). Retain overlapping records, mark overlaps, and sort IDs after
all files are read. End time is the last sample: start+(npts-1)/rate.
Source file references are stored in user_defined.

End-time attributes are optional; readers derive missing ends from start,
length and sample_rate. Numeric timestamps remain numeric during indexing.
For numeric relative seconds, declare an ISO UTC time_reference inside
user_defined on the trace, channel or an ancestor; the nearest declaration
supplies the reference for index queries. Without it, this profile's reader
interprets numeric timestamps as Unix seconds. Keep channel and segment time
coordinates consistent and document the convention before ingesting data.

Flags: D = unknown QC state; R = raw/no QC; Q = QC applied; M = metadata adjusted
without changing time-series values. Preserve supplied flags. Passing a
schema check does not justify Q.

Bits 0-7: amplifier saturation, acquisition clipping, spike, jump,
missing/filled data, telemetry synchronization error, possible digital
filtering, suspect time flag. Document custom bits. The built-in workflow
marks missing intervals with bit 4; it does not automatically run the other
detectors. Zero bits do not certify those conditions were assessed.

## A.4: optional per-sample quality sequence (section 8.2)

--trace-quality adds one unsegmented trace_quality vector per channel.
Required attributes: type="trace", trace_quality="trace_quality",
sample_rate (float), start_time (string or float).
Optional: end_time (string or float), user_defined (JSON string).

The regular sample grid spans the whole channel including absent waveform
positions. Codes: 1 = missing/discontinuous, 2 = overlap, 3 = calibration
signal. Other codes are user-defined. The built-in detector uses 0 for
observed once with other quality unassessed; it detects codes 1/2, not
calibration signals. Do not infer calibration from instrument gain.

Waveforms remain unfilled. Quality vectors are excluded from num_of_seg and
waveform indexes. The dataloader returns the full timeline and segment offset.
One timeline requires a uniform aligned grid. Mixed rates or unaligned epochs
require explicit partitioning or omission of this optional sequence, not
silent resampling. --max-quality-samples limits allocation (10 million by
default); use shorter samples or explicitly increase it.

## C.1: labels

Each label dataset has type="label". Optional lists: phase_name,
phase_arrival_time, phase_name_prob, phase_name_snr, polarity_type,
polarity_clarity, and {phase,polarity}_annotation_method.
user_defined carries JSON-serialized extensions; the profile stores one JSON
string per pick, aligned with other vectors. Numeric labels are float64;
others use UTF-8. Unlabeled data uses empty vectors.

Keep equal vector lengths and all annotation sources. Reviews and reprocessing
must not overwrite originals (sections 5.4/8.3).
Methods are manual_{person_or_agency} or automatic_{method}. Unknown methods
are none, with raw values retained for model-assisted mapping.
Probabilities are in [0,1]; missing probabilities/SNR are NaN.

## D.1: continuous samples

Required: type="event", event_id (unique string).
Optional: event_remark (string).

Use the event hierarchy without a fictitious earthquake origin, magnitude,
or location. The profile stores observed window bounds and UTC convention
in user_defined. Root dataset_mode selects D.1. Optional --catalog labels
are assigned to existing windows; picks never determine waveform cuts.

## D.2: earthquake samples

Required strings: type="event", event_id, source_type, source_origintime,
time_standard.
Required floats: source_longitude_deg, source_latitude_deg, source_depth_km.
Required lists: source_magnitude_type (string), source_magnitude (float).

Optional floats: source_origintime_err, source_origintime_ref,
max_azimuthal_gap_deg, station_azimuth_uniformity, min_epicentral_dist_km,
max_epicentral_dist_km, horizontal_uncertainty_major_km,
horizontal_uncertainty_minor_km, horizontal_uncertainty_azimuth,
vertical_uncertainty_km, residual_mean_sec, location_rms_sec.

Optional integers: num_phases_used, num_stations_used. These count observations
actually used in location, not the total picks/stations in the dataset.

Optional strings: preferred_magnitude_type, source_area, source_agency,
location_method, velocity_model_id, event_status, updated_time, event_remark.

Optional float lists: source_magnitude_error, source_moment,
source_fault_plane, source_fault_plane_err.

Magnitude types, values and errors align; preferred type belongs to the list.
Moment tensor order is [Mrr,Mtt,Mff,Mrt,Mrf,Mtf] or a 3x3 matrix. Fault planes
are [strike,dip,rake] or two such vectors; errors match their shape.
Event status examples: automatic/manual/rejected/merged.

Use explicit UTC Z. Convert known offsets; do not relabel GPS/TAI or unknown
timezones as UTC. Extraction requires resolved UTC. A finite
source_origintime_ref adds relative seconds to source_origintime before
applying the window. Center event windows on that origin, not on picks,
unless the user requests and documents a different sampling scheme.

## Release files (sections 6.1, 6.3-6.5)

Use a dedicated release directory. Required: HDF5, a UTF-8 data-owner-supplied
LICENSE, and checksums. Continuous releases also require hierarchical UTF-8
JSON. This writer exports JSON for both modes directly from HDF5:
each node has attributes and children; label leaves include values;
waveform/quality leaves contain only shape, dtype and attributes.
Canonical input JSON is not this release JSON.

The draft uses checksums.md5 in 6.5 and md5sum.txt in A.1. Emit identical
manifests under both names; root md5 references md5sum.txt.
Lines are <MD5><two spaces><relative filename>. Exclude both manifests to
avoid recursive self-checksumming. Include all other release files:
JSON, LICENSE, SQLite, StationXML and run notes when present.

After adding/changing artifacts, run package-dataset to refresh file_size,
JSON and checksums, then validate-hdf5 --release.
Do not assign the skill's software license to a user's data without their
instruction. The CLI accepts --license-file, --license-text, or an existing
release-directory LICENSE; it does not invent rights.

## Validation and limitations

validate-hdf5 checks hierarchy/types, required attributes, list alignment,
precision, segment order/timing, finite waveforms, quality metadata,
counts, label methods, coordinate and probability ranges.
--release additionally compares JSON with HDF5 and verifies every checksum
and LICENSE. Errors return nonzero status; permitted missing values produce
warnings.

This is not scientific review, proof of license rights, response validation,
or certification of all externally referenced standards. Record provenance,
unit/time mappings, unresolved metadata, processing/quality methods, and test
results in run notes. Quality flags alone must not cause data deletion (8.1).

Legacy v1 used JSON-text lists, aliases and synthetic continuous origins.
Regenerate from retained sources; changing a version attribute is not a
migration. Basic legacy dataloader reading remains available, but v1 files
do not pass this profile's validator.
