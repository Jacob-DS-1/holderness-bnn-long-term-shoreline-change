"""Project configuration: paths, constants and site definitions.

Values only - no functions, no I/O at import time. Modules under holderness/
take these as arguments rather than importing this file, so they stay loopable
over sites and variants.
"""

from pathlib import Path

# --- paths (anchored to the repo, not the working directory) ---
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = REPO_ROOT / 'data' / 'raw'
OUT = REPO_ROOT / 'outputs'
FIGS = REPO_ROOT / 'outputs' / 'figures'

FIG_DPI = 300

# --- site ---
SITE = 'holderness'

# --- provisional OS geometry seed ---
GML_PATH = DATA_RAW / 'TA.gml'
LAYER = 'TidalBoundary'
EPSG = 27700

# Trim anchors (EPSG:27700). Any point near the line works - project() snaps
# to the nearest point on the line.
ANCHOR_SOUTH = (541743, 415838)     # Kilnsea - southern limit of open coast
ANCHOR_NORTH = (518399, 466497)     # Bridlington - northern limit

# Regression checks against the local OS extract
EXPECTED_OS_LENGTH_M = {'mhw': 60207, 'mlw': 61532, 'seed': 59775}

OS_SEED_STEP = 25
COASTSAT_REFERENCE_STEP = 15
BOX_BUFFER = 2000

# --- CoastSat retrieval ---
DATE_RANGE = ['1990-01-01', '2024-12-01']
SAT_LIST = ['L5', 'L7', 'L8', 'L9', 'S2']

# Derived from the trimmed MHW line (see reference notebook), not drawn by hand.
POLYGON = [[[-0.25, 53.60],
            [0.18, 53.60],
            [0.18, 54.10],
            [-0.25, 54.10],
            [-0.25, 53.60]]]

# --- transects ---
TRANSECT_SPACING = 50
TRANSECT_SUBSET_SPACINGS = (100, 200, 500)
TRANSECT_NORMAL_WINDOW = 250       # provisional until the final reference exists
TRANSECT_LANDWARD = 300
TRANSECT_SEAWARD = 300
