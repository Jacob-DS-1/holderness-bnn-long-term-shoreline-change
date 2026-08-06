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

# --- reference shoreline source ---
GML_PATH = DATA_RAW / 'TA.gml'
LAYER = 'TidalBoundary'
EPSG = 27700

# Trim anchors (EPSG:27700). Any point near the line works - project() snaps
# to the nearest point on the line.
ANCHOR_SOUTH = (541743, 415838)     # Kilnsea - southern limit of open coast
ANCHOR_NORTH = (518399, 466497)     # Bridlington - northern limit

# Regression check against a known-good run
EXPECT_LENGTH_M = {'mhw': 60207, 'mlw': 61532}
EXPECT_TOL = 0.02

SAMPLE_STEP = 25        # alongshore sampling interval for separation and midline
DENSIFY_STEP = 15       # final vertex spacing of saved reference shorelines
BOX_BUFFER = 2000       # buffer around shoreline for the retrieval polygon

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
TRANSECT_WINDOW = 250
# ---
# NOT YET FULLY RESOLVED, require empirical comparison between reference shorelines
# and extracted shorelines to attempt to determine when OS OpenMap data was collected
# before these extents can be finally chosen
TRANSECT_LANDWARD = 300
TRANSECT_SEAWARD = 400
# ---
TRANSECT_END_TRIM = 500     # drop transects within this distance of the northern end

# Defended frontages, alongshore distance from Kilnsea (m). NOT YET FULLY RESOLVED.
# Positions from the OS NamedPlace layer; extents to be refined from the
# Shoreline Management Plan or by inspecting defence structures in the OS data.
DEFENDED = {
    'easington':   (4600, 5700),
    'withernsea':  (14200, 16200),
    'mappleton':   (34400, 35300),
    'hornsea':     (36900, 38500),
    'skipsea':     (47000, 47700),
    'ulrome':      (48800, 49400),
    'bridlington': (58000, 59800),
}
DOWNDRIFT_M = 2000   # Nicholls: terminal groyne effect extends 1-2 km downdrift