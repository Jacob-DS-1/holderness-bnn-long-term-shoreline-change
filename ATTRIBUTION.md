# Data attribution

Use only the entries for sources that contributed to a particular output.
Replace every bracketed field from the retrieval and source metadata recorded
in [`docs/data-licence-manifest.json`](docs/data-licence-manifest.json). A
template is not evidence that a source has been cleared for publication.

## Ready-to-use templates

### OS OpenMap - Local

> Contains OS data © Crown copyright and database right [source year].

The source year must come from the product release or download record; do not
infer it from a file timestamp. The local tidal boundary is an undated,
provisional geometry seed and not a shoreline observation.

### USGS Landsat Collection 2

> Landsat Collection 2 Level-1 images courtesy of the U.S. Geological Survey.

Published data should also identify the collection, source scene IDs and
acquisition dates used.

### Copernicus Sentinel-2

> Contains modified Copernicus Sentinel data [acquisition year or years].

Sentinel-2 is a separate post-2015 validation and sensitivity stream, not part
of the primary Landsat record.

### FES2022

> The FES2022 Tide product was funded by CNES, produced by LEGOS, NOVELTIS and CLS and made freely available by AVISO.

Also cite: CNES (2024), *FES2022 (Finite Element Solution) Tidal model,
Version 2024*, <https://doi.org/10.24400/527896/A01-2024.004>. Record the AVISO
licence accepted and retrieval date. Do not redistribute raw FES grids.

### GTSM v3

> Global sea level change time series from 1950 to 2050 derived from reanalysis and high resolution CMIP6 climate projections. Copernicus Climate Change Service, DOI: 10.24381/cds.a6d42d60 (accessed [date]).

Confirm the exact GTSM product and version when it is retrieved; the source
record, rather than the model name alone, determines the applicable citation.

### Copernicus Marine wave reanalysis

For the dissertation or another publication:

> This study has been conducted using E.U. Copernicus Marine Service Information; https://doi.org/10.48670/moi-00060.

For a derived data product:

> Generated using E.U. Copernicus Marine Service Information; https://doi.org/10.48670/moi-00060.

The product is *Atlantic - European North West Shelf - Wave Physics
Reanalysis*, `NWSHELF_REANALYSIS_WAV_004_015`. Include its access date and the
downloaded dataset version.

### Environment Agency time-stamped DTM LiDAR

Use the attribution supplied with the exact downloaded product. The current
catalogue record for the time-stamped DTM tiles states:

> © Environment Agency copyright and/or database right 2020. All rights reserved.

Record each survey date and tile; do not describe LiDAR as independent
validation without identifying the surveys actually reserved for that role.

### Open BGS products

Only use a product whose own metadata explicitly confirms Open Government
Licence coverage. The BGS OpenGeoscience template is:

> Contains British Geological Survey materials ©NERC [year].

The year and any product-specific conditions must come from the selected
dataset record.

## Sources requiring a record-level check

### Hornsea WaveNet WaveRider

WaveNet assigns one of three access categories to each station: OGL, restricted
to non-commercial government and academic use, or view-only. Record Hornsea's
category and owner from its Advanced Information metadata before downloading,
using or publishing any values. There is no safe generic attribution until
that check is complete.

### BODC tide gauges

BODC's standard template is:

> This study uses data from [source, organisation or programme], provided by the British Oceanographic Data Centre and funded by [funding body].

The standard agreement is non-transferable and says data must not be passed to
third parties without prior consent. Preserve the data schedule and check the
chosen gauge's additional restrictions before publishing source data or
detailed derivatives.

### East Riding monitoring surveys

There is no project-wide assumed licence. Save the terms and permission for
every LiDAR or profile epoch separately. Do not publish source files or
detailed derivatives until the relevant epoch is cleared and its required
credit is recorded.

## Software and methods

Publications should cite CoastSat and its relevant papers in addition to
observing the GPL. Use the commit in [`COASTSAT_REVISION`](COASTSAT_REVISION)
to identify the exact software version.
