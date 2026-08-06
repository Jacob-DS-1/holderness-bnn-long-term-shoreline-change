# Licensing and reuse

This file explains which licences apply to the different parts of the
project. Provider terms remain authoritative; the project records its current
interpretation in [`docs/data-licence-manifest.json`](docs/data-licence-manifest.json).

## Project software and documentation

Unless a file says otherwise, project-authored software and supporting
documentation in this repository are:

```text
Copyright (C) 2026 Jacob Woodland
SPDX-License-Identifier: GPL-3.0-only
```

This includes `holderness/`, `scripts/`, `tests/`, `docs/`, the notebook and
output guidance, configuration, environment files and implementation plan.
The complete licence is in [`LICENSE`](LICENSE). It grants rights only in
material for which the project copyright holder can grant them.

## CoastSat

Shoreline extraction uses, but does not vendor, a sibling checkout of
[CoastSat](https://github.com/kvos/CoastSat). CoastSat is licensed under GNU
GPL v3 and remains copyright its authors and contributors. The exact upstream
commit and environment are recorded in [`COASTSAT_REVISION`](COASTSAT_REVISION).

All project code is currently GPL-3.0-only, including the CoastSat adapters in
`holderness/coastsat_api.py` and extraction-related scripts. There is no
separately licensed downstream-analysis package yet. If one is introduced,
its boundary and licence must be explicit rather than inferred from where it
is imported.

## Third-party data

The repository GPL does not relicense satellite imagery, OS mapping, tide or
surge grids, wave reanalysis, LiDAR, monitoring surveys, geological data or
other external inputs. These remain subject to their source-specific terms.

Raw data are ignored by Git and each reproducer must obtain them from the
provider. This includes the local `data/raw/TA.gml`: it is OS OpenMap - Local
OpenData used only as a provisional chainage and geometry seed. It is not a
dated shoreline observation and is not distributed by this repository.

Before using or publishing material from a source:

1. complete its version, retrieval date, checksum, coverage and transformation
   history in the data licence manifest;
2. resolve every publication blocker listed there; and
3. copy the applicable wording from [`ATTRIBUTION.md`](ATTRIBUTION.md) into the
   output, replacing all placeholders from the retrieval record.

In particular, raw FES grids must not be redistributed. East Riding survey
epochs, the Hornsea WaveNet station and BODC tide-gauge records are not cleared
for publication until their exact record-level terms have been checked.

## Derived data and other outputs

The intended default for original, publishable derived shorelines, rate tables
and model outputs is [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
CC0 may instead be chosen deliberately for an output whose complete rights
review permits it. Either choice applies only to the project-authored material
and cannot remove inherited attribution, licence or redistribution conditions.

An output is not licensed merely because GPL-covered code produced it. Each
released data bundle must state its licence, include the required provider
attributions, identify its manifest records and contain no source material
that cannot be redistributed. Until that release record exists, generated
outputs should be treated as unpublished working material.

Dissertations, papers, presentations and figures are not covered by the
derived-data default unless they carry their own explicit notice.

## Credentials and restricted files

Google Earth Engine credentials, OAuth tokens, service-account keys and other
secrets must remain outside Git. Restricted model grids, proprietary basemap
pixels, premium geospatial data and unnecessary raw satellite files must not
be committed.

The GPL governs reuse of software; it does not replace scholarly citation.
Research outputs should also cite the project, CoastSat, methods and datasets
used.
