# Scripts

These are readable, numbered entry points. Reusable calculations live in
`holderness/`; each script performs its named task directly and can be run from
any working directory after this project has been installed with `pip install
-e .` in the relevant environment.

Check a newly built environment before starting work:

```bash
conda run -n holderness-bnn python scripts/check-environment.py analysis
conda run -n holderness-bnn python -m pip check
conda run -n holderness-bnn python -m pytest

conda run -n coastsat310 python scripts/check-environment.py coastsat
conda run -n coastsat310 python -m pip check
```

After downloading and decompressing the licensed FES2022b non-extrapolated
ocean and load grids, validate the ignored machine-local YAML and PyFES
integration:

```bash
conda run -n holderness-bnn python scripts/check-fes2022.py
```

This reads 34 ocean and 34 loading constituents and makes one bounded local
smoke prediction without downloading or writing anything. Its fixed offshore
point and date test the installation only; they are not final water-level
sampling choices or scientific validation.

After approving the water-blind pilot evaluation pool, preview its fixed GTSM
v3 request from the repository root:

```bash
conda run -n holderness-bnn python scripts/download-gtsm-pilot.py \
  --output-dir /path/to/large/local/gtsm-directory \
  --dry-run
```

Remove `--dry-run` to retrieve the required 10-minute surge months. The output
directory is deliberately explicit because the global monthly station files
are large and remain local. Existing valid archives are checked and skipped;
an invalid or partial archive stops the script instead of being overwritten.

Preview the separate fixed annual mean-sea-level request against the same
external directory:

```bash
conda run -n holderness-bnn python scripts/download-gtsm-annual-msl.py \
  --output-dir /path/to/large/local/gtsm-directory \
  --dry-run
```

This request consists of exactly two archives: the CDS `historical` experiment
at version `v1` for 1990--2014 and the CDS `future` experiment at version `v1`
for 2015--2024. Both use the GTSM v3.0 hydrodynamic model; model version and CDS
experiment-file version are recorded separately. Remove `--dry-run` to
validate and promote a complete matching `.zip.partial`, skip a valid final
archive, or download a missing archive. Invalid partials or final archives
stop the script and no final archive is overwritten.

The source annual mean sea level is referenced to 1986--2005. Recentring each
selected-station series to 1991--2020 is a later documented transformation;
the raw values remain unchanged. The script writes a separate retrieval plan
and download ledger under `data/derived/pilot/` and does not alter the frozen
10-minute surge manifest.

From the repository root, build the provisional OS seed and availability ROIs:

```bash
conda run -n holderness-bnn python scripts/01-build-geometry-seed.py
conda run -n holderness-bnn python scripts/02-build-rois.py
```

Preview the separate Landsat or Sentinel-2 metadata queries without connecting
to Earth Engine:

```bash
conda run -n coastsat310 python scripts/03-check-image-availability.py \
  --stream landsat --dry-run
conda run -n coastsat310 python scripts/03-check-image-availability.py \
  --stream sentinel --dry-run
```

Remove `--dry-run` to authenticate and query metadata. This script never
downloads imagery. It writes scene, quarterly and summary manifests under
`data/derived/availability/`. It expects CoastSat at `../CoastSat`, verifies
the commit in `COASTSAT_REVISION`, and accepts `--coastsat-dir` when the
checkout is elsewhere. The configured `2025-01-01` query end is exclusive and
therefore includes all of 2024. The pinned CoastSat metadata helper omits
scenes above 95% provider scene-wide cloud cover; local coastal cloud still
requires later visual QC.

After the Landsat manifest exists, prepare an editable pilot candidate pool:

```bash
conda run -n holderness-bnn python scripts/04-prepare-pilot.py --dry-run
```

The resulting table is a preliminary scene-metadata pool. Water level is a
scene-specific label; defence and morphology are properties of local pilot
sectors and must not be copied across an entire approximately 5 km availability
ROI. The approved Design 1 pairs the reviewed core sectors with 14 selected
scene dates. Imagery retrieval is deliberately not exposed by this script;
the next stage is a separate controlled retrieval followed by local visual QC.
Coastal-regime availability counts required by implementation-plan item P026
remain pending until defensible local regime sectors exist; an availability
ROI is not silently treated as a coastal regime.

After the frozen water-level evaluation pool, both GTSM download ledgers and
the local FES2022 configuration exist, validate the approved provisional nodes
without writing evidence:

```bash
conda run -n holderness-bnn python scripts/05-prepare-pilot-water-levels.py \
  --gtsm-dir /path/to/large/local/gtsm-directory \
  --dry-run
```

Remove `--dry-run` to checksum-validate all 94 surge archives and both annual
MSL archives, interpolate surge at each exact scene UTC under the strict
two-sided finite-bracket rule, evaluate FES ocean and loading tide, recenter
annual MSL from its native 1986--2005 reference to 1991--2020, and combine the
three still-water components. The script writes ignored evidence under
`data/derived/pilot/` and the annual-MSL boundary figure under
`outputs/figures/`.

The three FES points and GTSM stations are pilot-only selections derived from
the undated OS geometry seed. They must be recalculated after the
satellite-derived reference shoreline exists. The resulting anomalies are not
an ODN conversion and do not include a wave term. The completed evidence feeds
the approved Design 1 date choice, but this script does not download imagery
or begin shoreline extraction.
