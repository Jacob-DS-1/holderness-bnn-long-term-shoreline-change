# holderness-bnn-long-term-shoreline-change

Spatial prediction of long-term satellite-derived waterline position change
rates along the Holderness Coast using physical covariates and an approximate
Bayesian neural network.

## CoastSat dependency

Shoreline extraction uses upstream CoastSat pinned to commit
`b9abb0c5902d9b160ba2790d55de41f0d5068497`. The repository URL, commit
timestamp and extraction environment are recorded in [`COASTSAT_REVISION`](COASTSAT_REVISION).

Verify a sibling checkout with:

```bash
git -C ../CoastSat rev-parse HEAD
```

## Local settings

The repository does not store credentials, local CoastSat paths or a personal
Google Earth Engine project ID. Supply the project ID to a script with
`--gee-project`, or set it for the current shell:

```bash
export HOLDERNESS_GEE_PROJECT=your-google-cloud-project-id
```

Authentication remains local to each user.
