# Scripts

This directory will contain readable, numbered entry points for the project
stages. Each script should import reusable functions from `holderness/` and
perform its named task directly.

The pre-refactor image-availability and retrieval scripts are preserved on the
`archive/pre-plan-refactor-2026-08-06` branch. They must not be used because
they mix Landsat and Sentinel-2, use a single full-coast rectangle, change into
a separate CoastSat checkout and write data outside this project.

New acquisition scripts will be added after the ROI-aware availability and
blinded-pilot configuration have been implemented.
