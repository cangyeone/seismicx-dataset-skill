# Standard HDF5 Schema

This skill follows the dataset standard in `data set standard.docx` from the
source workspace. Use these names exactly.

## File set

A released dataset should contain:

- HDF5 file: required.
- JSON metadata and labels derived from HDF5 attributes: required for
  continuous waveform datasets and recommended for event datasets.
- `LICENSE`: required.
- `md5sum.txt` or `checksums.md5`: required.
- StationXML: optional when instrument response is available.

## Required HDF5 hierarchy

Use the same hierarchy for both event and continuous datasets:

```text
/
  information/                         type="information"
    {station_id}/                      type="station"
  data/                                type="data"
    {sample_id}/                       type="event"
      {station_id}/                    type="station"
        waveform/                      type="waveform"
          {channel}/                   type="channel"
            {seg_id}                   type="trace", waveform vector
        label/                         type="label"
          phase_name                   type="label", 1-D string vector
          phase_arrival_time           type="label", 1-D string vector
          phase_name_prob              type="label", 1-D float vector
          phase_name_snr               type="label", 1-D float vector
          polarity_type                type="label", 1-D string vector
          polarity_clarity             type="label", 1-D string vector
          phase_annotation_method      type="label", 1-D string vector
          polarity_annotation_method   type="label", 1-D string vector
          user_defined                 type="label", 1-D JSON string vector
```

For continuous samples, set the sample group's `type` to `event` because the
standard uses `event` as the sample-layer type value. Also set
`source_type="cont"` and use the window start as `source_origintime`.

## Root dataset attributes

Use these root attributes:

`name`, `version`, `license`, `md5`, `processing_time`, `agency`, `author`,
`num_stations`, `num_events`, `annotation_types`, `annotation_counts`,
`description`, `file_size`.

Lists may be stored as JSON strings in HDF5 attributes when native HDF5 string
arrays would be fragile.

## Station attributes

Station groups under both `/information` and sample groups use:

`type="station"`, `station_id`, `station_network`, `station_station`,
`station_location`, `station_channel_list`, `station_longitude_deg`,
`station_latitude_deg`, `station_elevation_m`, `station_depth_m`,
`station_area`, `station_agency`, `station_remark`.

`station_id` should be `network.station.location`. Use `--` for empty location
codes unless the user specifies another empty-location value.

## Channel attributes

Channel groups use:

`type="channel"`, `station_channel_id`, `num_of_seg`, `start_time`,
`end_time`, `continuity_rate`, `orientation`, `user_defined`.

## Trace attributes

Waveform datasets use:

`type="trace"`, `seg_id`, `unit`, `sample_rate`, `seg_start_time`,
`seg_end_time`, `quality_flag`, `quality_metric`,
`quality_metric_description`.

Quality flag values follow the standard:

- `D`: unknown quality control state.
- `R`: raw waveform without quality control.
- `Q`: quality-controlled waveform.
- `M`: data center adjusted metadata while time-series values are unchanged.

Quality metric bits follow the standard where possible:

- bit 0: amplifier saturation.
- bit 1: data acquisition clipping.
- bit 2: spike.
- bit 3: jump.
- bit 4: missing or filled data.
- bit 5: telemetry sync error.
- bit 6: possible digital filtering.
- bit 7: time flag may be problematic.

## Event sample attributes

Event or sample groups use:

`type="event"`, `event_id`, `source_type`, `source_origintime`,
`source_origintime_err`, `source_origintime_ref`, `time_standard`,
`source_longitude_deg`, `source_latitude_deg`, `source_depth_km`,
`source_magnitude_type`, `source_magnitude`, `source_magnitude_error`,
`preferred_magnitude_type`, `source_area`, `source_agency`,
`location_method`, `velocity_model_id`, `num_phases_used`,
`num_stations_used`, `max_azimuthal_gap_deg`,
`station_azimuth_uniformity`, `min_epicentral_dist_km`,
`max_epicentral_dist_km`, `horizontal_uncertainty_major_km`,
`horizontal_uncertainty_minor_km`, `horizontal_uncertainty_azimuth`,
`vertical_uncertainty_km`, `residual_mean_sec`, `location_rms_sec`,
`event_status`, `updated_time`, `source_moment`, `source_fault_plane`,
`source_fault_plane_err`, `event_remark`.

For missing strings use `"none"`. For missing numbers use `NaN`.

## Label attributes and datasets

Label fields use:

`type="label"`, `phase_name`, `phase_arrival_time`, `phase_name_prob`,
`phase_name_snr`, `polarity_type`, `polarity_clarity`,
`phase_annotation_method`, `polarity_annotation_method`, `user_defined`.

Use `manual_{agency}` or `automatic_{method}` for annotation method values.
Store multiple annotation sources as vectors rather than overwriting previous
labels.
