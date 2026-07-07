# mseedindex Workflow

This skill bundles EarthScope `mseedindex` source under `assets/mseedindex`.
The helper script can clone it again if the directory is missing and can build
it on the current user environment.

## Build

```bash
python scripts/seismicx_dataset.py install-mseedindex
```

The script tries `make`, then `gmake`. It respects `CC`, `CFLAGS`, and
`LDFLAGS`. PostgreSQL support is not required for SQLite indexing.

## Convert arbitrary waveform formats to miniSEED

ObsPy reads many seismic formats. Convert first:

```bash
python scripts/seismicx_dataset.py convert-waveforms \
  --input raw_waveforms \
  --output-dir mseed \
  --recursive
```

Use `--obspy-format FORMAT` only when ObsPy cannot infer the format.

## Build a miniSEED SQLite index

```bash
python scripts/seismicx_dataset.py index-mseed \
  --input mseed \
  --db waveform.sqlite \
  --reset
```

Internally this runs:

```bash
assets/mseedindex/mseedindex -sqlite waveform.sqlite @file-list.txt
```

Use `--keep-paths` to pass `-kp` when paths should be stored as provided.

## Query and read from a miniSEED index

```bash
python scripts/seismicx_dataset.py query-mseed \
  --db waveform.sqlite \
  --network BK \
  --station BDM \
  --location 00 \
  --channel 'BH*' \
  --starttime 2019-07-06T04:00:00 \
  --endtime 2019-07-06T04:01:00 \
  --output out.mseed
```

The query command uses the `tsindex` table created by EarthScope mseedindex,
then reads matching files with ObsPy and trims the returned stream.

## Dataset production order

1. Convert raw waveforms to miniSEED.
2. Build the mseedindex SQLite database.
3. Normalize labels to canonical JSON.
4. Build event or continuous HDF5.
5. Build the HDF5 dataset index.
6. Validate with the dataloader example.
