"""Central project settings.

Keep scientific settings here so scripts and notebooks use the same values.
Machine-specific paths, credentials and Google Earth Engine project IDs do not
belong in this file. ``get_gee_project`` reads its environment variable only
when called.
"""

import os
from pathlib import Path


# Paths -----------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / 'data'
DATA_RAW = DATA / 'raw'
DATA_INTERIM = DATA / 'interim'
DATA_DERIVED = DATA / 'derived'
OUTPUTS = REPO_ROOT / 'outputs'
FIGURES = OUTPUTS / 'figures'


# Fixed project settings ------------------------------------------------------

SITE = 'holderness'
EPSG = 27700
POSITIVE_CROSS_SHORE_DIRECTION = 'seaward'

LANDSAT_SENSORS = ('L5', 'L7', 'L8', 'L9')
SENTINEL_SENSORS = ('S2',)
LANDSAT_DATES = ('1990-01-01', '2024-12-31')
SENTINEL_DATES = ('2015-01-01', '2024-12-31')

TARGET_MSL_PERIOD = (1991, 2020)
TARGET_VERTICAL_DATUM = 'ODN'

MASTER_TRANSECT_SPACING_M = 50
TRANSECT_SUBSET_SPACINGS_M = (100, 200, 500)
INITIAL_MAX_DIST_REF_M = 250
MAX_DIST_REF_INCREMENT_M = 25
MAX_DIST_REF_BOUNDARY_WARNING_M = 30
TRANSECT_ENDPOINT_MARGIN_M = 50
INITIAL_TRANSECT_LANDWARD_M = 300
INITIAL_TRANSECT_SEAWARD_M = 300

ROI_LENGTH_M = 5_000
ROI_OVERLAP_M = 500
ROI_MAX_AREA_M2 = 25_000_000

COASTSAT_ALONG_DIST_M = 25
COASTSAT_MIN_SHORELINE_POINTS = 3
LANDSAT_MAX_GEOMETRIC_RMSE_M = 10


# Provisional OS geometry seed ------------------------------------------------

OS_TIDAL_BOUNDARY_PATH = DATA_RAW / 'TA.gml'
OS_TIDAL_BOUNDARY_LAYER = 'TidalBoundary'
OS_ANCHOR_SOUTH = (541743, 415838)   # Kilnsea
OS_ANCHOR_NORTH = (518399, 466497)   # Bridlington
OS_SEED_STEP_M = 25

# Regression checks against the local OS extract
EXPECTED_OS_LENGTH_M = {'mhw': 60207, 'mlw': 61532, 'seed': 59775}

# In-memory sampling used only when passing a final reference line to CoastSat
COASTSAT_REFERENCE_STEP_M = 15


# Pinned data products --------------------------------------------------------

LANDSAT_GEE_COLLECTIONS = {
    'L5': 'LANDSAT/LT05/C02/T1_TOA',
    'L7': 'LANDSAT/LE07/C02/T1_TOA',
    'L8': 'LANDSAT/LC08/C02/T1_TOA',
    'L9': 'LANDSAT/LC09/C02/T1_TOA',
}
SENTINEL_GEE_COLLECTIONS = {
    'S2': 'COPERNICUS/S2_HARMONIZED',
}

TIDE_MODEL = 'FES2022'
SEA_LEVEL_AND_SURGE_MODEL = 'GTSM v3'
WAVE_PRODUCT = 'NWSHELF_REANALYSIS_WAV_004_015'
TOPOGRAPHIC_VALIDATION_SOURCE = 'Environment Agency time-stamped LiDAR'


# Pilot settings not yet frozen ----------------------------------------------

PILOT_STATUS = 'not_started'
PILOT_RULES_FROZEN = False

CLASSIFIER_CANDIDATES = ('default', 'dark')
LOW_WATER_FILTER_CANDIDATES = (
    'none',
    'below_local_amsl',
    'below_local_amsl_plus_0.2_m',
    'profile_lower_bound',
)

SELECTED_CLASSIFIER = None
SELECTED_LOW_WATER_FILTER = None

# Candidate inherited from the exploratory geometry work. Recheck this after
# the smoothed mid-record reference line has been constructed.
TRANSECT_NORMAL_WINDOW_M = 250


# Scientific values not yet resolved -----------------------------------------

# Publish the numerical value or alongshore interpolation before extraction is
# frozen. This is not selected from downstream shoreline rates.
TARGET_ELEVATION_ODN_M = None


# Machine-specific settings --------------------------------------------------

GEE_PROJECT_ENV = 'HOLDERNESS_GEE_PROJECT'


def get_gee_project(command_line_value=None):
    """Return a GEE project supplied by CLI or the local environment."""
    if command_line_value:
        return command_line_value

    project = os.environ.get(GEE_PROJECT_ENV)
    if project:
        return project

    raise RuntimeError(
        f'pass --gee-project or set the {GEE_PROJECT_ENV} environment variable'
    )
