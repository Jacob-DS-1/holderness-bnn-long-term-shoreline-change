# Generated outputs

Everything in this directory except this README is generated and ignored by
Git. Outputs are never authoritative inputs to an earlier workflow stage.

The files generated before the implementation plan was adopted have been moved
locally to `outputs/legacy/pre-plan-refactor/`. They include the OS-derived
reference arrays, retrieval polygon, 50 m transects, metadata and diagnostic
figures. These artifacts are retained only for comparison and must not be used
as inputs to the rebuilt workflow.

On a fresh clone the legacy directory will not be present. The active workflow
must regenerate outputs from documented source data and configuration.

Generated files are working material until a release explicitly assigns a
licence. The intended default for original derived shorelines, rate tables and
model outputs is CC BY 4.0, but only after every contributing entry in
`docs/data-licence-manifest.json` is complete and has no unresolved release
blockers. A released bundle must include its licence, provider attributions and
the IDs of the source records used. The licence does not extend to embedded
third-party material.
