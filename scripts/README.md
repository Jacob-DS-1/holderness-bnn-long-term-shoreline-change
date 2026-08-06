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
`data/derived/availability/`.

After the Landsat manifest exists, prepare an editable pilot candidate pool:

```bash
conda run -n holderness-bnn python scripts/04-prepare-pilot.py --dry-run
```

The resulting pool is preliminary until water-level, defence and morphology
labels have been completed. Imagery retrieval is deliberately not exposed yet;
it will be added only after the pilot inputs and retrieval rules are ready.
