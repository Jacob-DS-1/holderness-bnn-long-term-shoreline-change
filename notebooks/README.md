# Notebooks

Notebooks are part of the intended working style for visual review, exploratory
analysis and documented scientific decisions. Reusable calculations should
live in `holderness/` and be called transparently from notebooks.

Temporary working notebooks may be retained under the ignored
`notebooks/exploratory/` directory while a concise decision record is prepared.
Figures intended to support later reporting should be regenerated under the
ignored `outputs/figures/` directory rather than embedded as source material.

The active pilot decision record is split deliberately:

- `01-label-pilot-context.ipynb` records the approved local-sector design and
  the limits of the current defence evidence.
- `02-select-pilot-scenes.ipynb` checks feasibility within the frozen
  water-level evaluation pool and validates the step-05 evidence, but does not
  rank or select dates, freeze a shortlist or authorise imagery retrieval.
- `03-choose-pilot-dates.ipynb` records the approved 14-scene Design 1
  retrieval-candidate set, validates its coverage and LiDAR allocation, and
  writes the ignored `data/derived/pilot/pilot-retrieval-manifest.json`.
  Retrieval candidates still require local visual QC before extraction.

The pre-refactor reference-shoreline and transect notebooks are preserved on
the `archive/pre-plan-refactor-2026-08-06` branch because their outputs and
assumptions predate the canonical implementation plan. Replacement notebooks
will be added as the geometry and pilot workflow are rebuilt. Clear cell
outputs before committing active notebooks.
