# holderness-bnn-long-term-shoreline-change
Spatial prediction of long-term satellite-derived waterline position change rates along the Holderness Coast using physical covariates and an approximate Bayesian neural network

## CoastSat dependency

Shoreline extraction uses upstream CoastSat pinned to commit
`b9abb0c5902d9b160ba2790d55de41f0d5068497`. The repository URL, commit
timestamp and extraction environment are recorded in [`COASTSAT_REVISION`](COASTSAT_REVISION).

Verify a sibling checkout with:

```bash
git -C ../CoastSat rev-parse HEAD
```
