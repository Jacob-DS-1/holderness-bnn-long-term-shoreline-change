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

Create the two isolated environments from the repository root:

```bash
conda env create -f environment.yml
conda run -n holderness-bnn python -m pip install -e .

conda env create -f environment.coastsat.yml
conda run -n coastsat310 python -m pip install -e .
```

The complete tested analysis and CoastSat solves are recorded in
`environment.lock.yml` and `environment.coastsat.lock.yml`. Run the matching
smoke test after rebuilding either environment; see [`scripts/README.md`](scripts/README.md).

## Local settings

The repository does not store credentials, local CoastSat paths or a personal
Google Earth Engine project ID. Supply the project ID to a script with
`--gee-project`, or set it for the current shell:

```bash
export HOLDERNESS_GEE_PROJECT=your-google-cloud-project-id
```

Authentication remains local to each user.

## Licensing and data reuse

Project software and documentation are GPL-3.0-only. Third-party datasets keep
their own terms and are not distributed under the project licence. Before
retrieving or publishing data, read [`LICENSING.md`](LICENSING.md), use the
templates in [`ATTRIBUTION.md`](ATTRIBUTION.md), and complete the relevant
record in
[`docs/data-licence-manifest.json`](docs/data-licence-manifest.json).

The local OS OpenMap - Local `TA.gml` remains an ignored, provisional geometry
seed. It is not a dated shoreline observation and is not included in the
repository.
