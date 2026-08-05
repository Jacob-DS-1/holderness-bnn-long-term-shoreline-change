# Licensing and reuse

This file explains the scope of the repository licence. It does not replace
the legal terms in [`LICENSE`](LICENSE).

## Project-authored software

Unless a file or directory states otherwise, software and software-supporting
documentation authored for the Holderness shoreline-change modelling project
are:

```text
Copyright (C) 2026 Jacob Woodland
SPDX-License-Identifier: GPL-3.0-only
```

This includes the project-authored material under `src/`, `scripts/`,
`workflow_v3/`, `tests/`, `docs/`, the workflow configuration and environment
templates, and the `Makefile`. It is distributed under version 3 only of the
GNU General Public License. There is no warranty; see [`LICENSE`](LICENSE) for
the complete terms.

The licence grants rights only in material for which the relevant copyright
holder can grant those rights. It does not imply endorsement by The University
of Manchester, any data provider, or any other third party.

## CoastSat-derived material

[CoastSat](https://github.com/kvos/CoastSat) is distributed under the GNU
General Public License version 3. Copyright in CoastSat remains with its
respective authors and contributors.

The following tracked material is derived from, modifies, or reproduces parts
of CoastSat and remains under GPL-3.0 terms with its upstream provenance
retained:

- `third_party/coastsat/patches/*.patch`;
- `notebooks/archive/example_jupyter.ipynb`; and
- the corresponding project CoastSat fork identified in
  `COASTSAT_REVISION` and `third_party/coastsat/manifest.json`.

The patch files include both upstream context and project modifications. The
project modifications are licensed under GPL-3.0-only without altering any
upstream copyright. See `third_party/coastsat/README.md` for the pinned fork,
commit, base commit and reconstruction instructions.

## Data and external material

The repository GPL does **not** grant additional rights in:

- raw, external, interim or processed datasets;
- satellite imagery, mapping data, tide grids or environmental archives;
- third-party publications, extracts, screenshots, logos or maps;
- externally owned bibliographic or metadata content; or
- any material carrying its own licence, permission or attribution terms.

Those materials remain governed by their source-specific terms. The
authoritative project record is
`config/external/data_licence_manifest_v3.json`, supplemented by the source
records and permission files referenced there. Inclusion of metadata,
attribution or a derived value in this repository does not relicense the
underlying source.

## Generated reports, figures and the dissertation

The software licence does not automatically license outputs merely because
they were produced by GPL-covered code. Unless a tracked output states a
separate licence, the repository GPL does not grant reuse rights in:

- generated reports, figures and tables under `reports/`;
- a dissertation, manuscript or presentation added later; or
- outputs whose reuse is limited by underlying data or third-party rights.

These outputs may be cited in the normal academic manner. Redistribution or
adaptation requires checking the output's own notice and every relevant source
licence or permission.

## Academic attribution

The GPL governs legal reuse of software; it does not replace scholarly
citation. Publications and derivative research should cite this project,
CoastSat and the relevant datasets and methodological sources.
