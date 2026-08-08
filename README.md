# holderness-bnn-long-term-shoreline-change

Spatial prediction of long-term satellite-derived waterline position change
rates along the Holderness Coast using physical covariates and an approximate
Bayesian neural network.

[`implementation-plan.json`](implementation-plan.json) is the canonical record
of the scientific design. The code implements parts of that plan; it does not
silently replace unresolved pilot decisions with convenient defaults.

## Current status

The cleaned repository currently supports:

- building an explicitly provisional geometry seed from the local OS OpenMap -
  Local tidal boundary;
- building overlapping imagery-availability regions;
- planning or running metadata-only Landsat and Sentinel-2 availability
  queries; and
- preparing a reproducible, editable Landsat pilot candidate pool;
- recording reviewed local pilot sectors and contextual evidence; and
- building exact-time FES2022 and GTSM v3 water-level evidence for the frozen
  110-scene evaluation pool; and
- freezing the approved 14-scene Design 1 retrieval-candidate set.

It does not yet retrieve imagery, accept extraction scenes, extract final
shorelines, construct the mid-record reference shoreline or fit models. The
live Landsat availability query, contextual review, provisional water-level
preparation and date-design decision are complete. Design 1 is approved only
for controlled imagery retrieval followed by local visual QC; it does not
authorise shoreline extraction.

## Repository map

| Path | Purpose |
| --- | --- |
| [`implementation-plan.json`](implementation-plan.json) | Canonical scientific decisions and unresolved pilot choices |
| [`holderness/`](holderness) | Small reusable Python functions |
| [`scripts/`](scripts) | Numbered, readable workflow entry points |
| [`notebooks/`](notebooks) | Visual review and exploratory work, not hidden production logic |
| [`tests/`](tests) | Fast unit, regression and repository-policy checks |
| [`docs/`](docs) | Data-licensing and future reporting documentation |
| `data/` | Local raw and derived data; ignored by Git |
| `outputs/` | Regenerable results; ignored except for its README |

## Set up the environments

Shoreline extraction uses upstream CoastSat pinned to commit
`b9abb0c5902d9b160ba2790d55de41f0d5068497`. Its repository, commit timestamp
and environment are recorded in [`COASTSAT_REVISION`](COASTSAT_REVISION).

Keep the analysis and CoastSat environments separate:

```bash
conda env create -f environment.yml
conda run -n holderness-bnn python -m pip install -e .

conda env create -f environment.coastsat.yml
conda run -n coastsat310 python -m pip install -e .
```

The tested complete solves are recorded in `environment.lock.yml` and
`environment.coastsat.lock.yml`. Check rebuilt environments with the commands
in [`scripts/README.md`](scripts/README.md).

CoastSat is expected at the sibling path `../CoastSat` by default. Pass
`--coastsat-dir /path/to/CoastSat` to a CoastSat-dependent script if your
checkout is elsewhere. The script verifies the commit before importing it.

## Run the supported workflow

Place the OS OpenMap - Local GML at `data/raw/TA.gml`, then build the
provisional geometry and availability regions:

```bash
conda run -n holderness-bnn python scripts/01-build-geometry-seed.py
conda run -n holderness-bnn python scripts/02-build-rois.py
```

Inspect the planned metadata queries without authenticating or downloading
imagery:

```bash
conda run -n coastsat310 python scripts/03-check-image-availability.py \
  --stream landsat --dry-run
conda run -n coastsat310 python scripts/03-check-image-availability.py \
  --stream sentinel --dry-run
```

For a live metadata query, remove `--dry-run` and provide a Google Earth Engine
project through `--gee-project` or the environment variable:

```bash
export HOLDERNESS_GEE_PROJECT=your-google-cloud-project-id
conda run -n coastsat310 python scripts/03-check-image-availability.py \
  --stream landsat
```

Earth Engine query end dates are exclusive, so the configured `2025-01-01` end
includes acquisitions through 31 December 2024. The pinned CoastSat metadata
helper removes scenes with provider scene-wide cloud cover above 95%; the
result is therefore a coarsely filtered candidate catalog, not an unfiltered
Earth Engine inventory. Local coastal cloud and all other acceptance decisions
remain part of later visual QC.

Credentials remain local. After the Landsat scene manifest exists, inspect the
candidate scene pool without writing it:

```bash
conda run -n holderness-bnn python scripts/04-prepare-pilot.py --dry-run
```

See [`scripts/README.md`](scripts/README.md) for outputs and operational notes.
The availability ROIs are retrieval and coverage units, not scientific units
for coast-wide defence or morphology labels. Spatial pilot context is recorded
against short local sectors before sector--scene combinations are frozen.

## Working conventions

- Put reusable calculations in `holderness/` and keep numbered scripts as
  direct entry points.
- Use notebooks for visual inspection and exploratory decisions; move any
  calculation needed for reproduction into `holderness/`.
- Treat generated files as outputs, never as undocumented inputs to an earlier
  stage.
- Preserve scene IDs, retrieval dates, checksums and provider attribution as
  data enter the workflow.

## Licensing and data reuse

Project software and documentation are GPL-3.0-only. Third-party datasets keep
their own terms and are not distributed under the project licence. Before
retrieving or publishing data, read [`LICENSING.md`](LICENSING.md), use the
templates in [`ATTRIBUTION.md`](ATTRIBUTION.md), and complete the relevant
record in
[`docs/data-licence-manifest.json`](docs/data-licence-manifest.json).

The local `TA.gml` is an ignored, undated cartographic product used only as a
provisional chainage and geometry seed. The final 50 m transects will be cast
from the smoothed mid-record satellite reference shoreline, not from this OS
line.
