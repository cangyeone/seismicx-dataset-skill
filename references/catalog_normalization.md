# Catalog Normalization

Normalize all earthquake catalogs and annotation files to
`seismicx_canonical_labels_v1` before HDF5 writing.

## Canonical JSON

```json
{
  "format": "seismicx_canonical_labels_v1",
  "events": [
    {
      "type": "event",
      "event_id": "ci37220324",
      "source_type": "eq",
      "source_origintime": "2019-07-06T04:13:06.130000Z",
      "time_standard": "UTC",
      "source_longitude_deg": -117.6893,
      "source_latitude_deg": 35.9092,
      "source_depth_km": 8.39,
      "source_magnitude_type": ["lr"],
      "source_magnitude": [3.63],
      "preferred_magnitude_type": "lr",
      "source_agency": "SC",
      "stations": [
        {
          "type": "station",
          "station_id": "CI.CLC.--",
          "station_network": "CI",
          "station_station": "CLC",
          "station_location": "--",
          "station_channel_list": ["BHE", "BHN", "BHZ"],
          "station_longitude_deg": -117.59751,
          "station_latitude_deg": 35.81574,
          "station_elevation_m": 775.0,
          "station_depth_m": 0.0,
          "picks": [
            {
              "type": "label",
              "phase_name": "P",
              "phase_arrival_time": "2019-07-06T04:13:08.824000Z",
              "phase_name_prob": 1.0,
              "phase_name_snr": null,
              "polarity_type": "U",
              "polarity_clarity": "none",
              "phase_annotation_method": "manual_unknown",
              "polarity_annotation_method": "manual_unknown",
              "user_defined": {}
            }
          ]
        }
      ]
    }
  ],
  "metadata": {
    "source_file": "catalog.json",
    "warnings": []
  }
}
```

## Use the model for unknown catalogs

When a catalog format is not already canonical:

1. Inspect headers, field counts, units, repeated blocks, comments, and several
   representative records.
2. Infer event fields, station fields, and pick fields. Prefer standard field
   names from `standard_hdf5_schema.md`.
3. Create a mapping JSON when the built-in aliases are not enough.
4. Preserve unmodeled fields under `user_defined` so information is not lost.
5. Normalize times to ISO 8601 UTC strings where possible. If timezone is
   unknown, keep the original string and record a warning.

## Mapping JSON

`scripts/seismicx_dataset.py normalize-labels --mapping mapping.json` accepts:

```json
{
  "event_id": "evid",
  "source_origintime": "origin_time",
  "source_longitude_deg": "lon",
  "source_latitude_deg": "lat",
  "source_depth_km": "depth",
  "source_magnitude": "mag",
  "source_magnitude_type": "mag_type",
  "station_network": "net",
  "station_station": "sta",
  "station_location": "loc",
  "station_longitude_deg": "station_lon",
  "station_latitude_deg": "station_lat",
  "station_elevation_m": "elev_m",
  "phase_name": "phase",
  "phase_arrival_time": "pick_time",
  "phase_name_prob": "score",
  "phase_name_snr": "snr",
  "polarity_type": "polarity",
  "polarity_clarity": "clarity",
  "phase_annotation_method": "status"
}
```

Values may be a string column name or a list of candidate column names.

## Common aliases

Event:

- `event_id`: `event_id`, `evid`, `ev_id`, `id`, `source_id`, `quake_id`.
- `source_origintime`: `event_time`, `origin_time`, `origintime`, `time`, `ot`.
- `source_longitude_deg`: `longitude`, `lon`, `evlo`.
- `source_latitude_deg`: `latitude`, `lat`, `evla`.
- `source_depth_km`: `depth_km`, `depth`, `evdp`.
- `source_magnitude`: `magnitude`, `mag`, `ml`, `mw`, `mb`, `md`.
- `source_magnitude_type`: `magnitude_type`, `mag_type`, `mtype`.

Station:

- `station_id`: `station_id`, `stid`, `seed_id`.
- `station_network`: `network`, `net`.
- `station_station`: `station`, `sta`.
- `station_location`: `location`, `loc`.
- `station_channel_list`: `channels`, `channel_hint`, `component`.
- `station_longitude_deg`: `station_longitude`, `station_lon`, `stlo`.
- `station_latitude_deg`: `station_latitude`, `station_lat`, `stla`.
- `station_elevation_m`: `elevation`, `elevation_m`, `stel`.

Pick:

- `phase_name`: `phase`, `phase_name`, `type`, `phase_type`.
- `phase_arrival_time`: `pick_time`, `arrival_time`, `phase_time`, `time`.
- `phase_name_prob`: `score`, `probability`, `confidence`, `phase_score`.
- `phase_name_snr`: `snr`, `phase_snr`.
- `polarity_type`: `polarity`, `updown`, `first_motion`.
- `polarity_clarity`: `clarity`, `quality`, `onset`.
- `phase_annotation_method`: `status`, `method`, `picker`, `source`.

## Reference JSON

The source workspace example
`mini_data/data/label/annotations_mini_two_hours.json` is hierarchical:

`years -> days -> events -> stations -> picks`.

The normalizer recognizes this shape and converts it to canonical events. Other
JSON shapes should be mapped by inference or with `mapping.json`.
