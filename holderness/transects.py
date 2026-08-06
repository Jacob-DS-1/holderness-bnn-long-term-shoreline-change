"""Sample the reference line at fixed alongshore spacing.
Compute a shore-normal direction at each sample.
Extend landward and seaward by chosen distances.
Transects are returned as a dictionary of {name: (2,2) array},
all coordinates in EPSG:27700, transect origins are all landward, cast from midline."""

import numpy as np
import geopandas as gpd
from shapely.geometry import LineString, Point


def sample_origins(line, spacing, skip_ranges=None, pad=0):
    """Sample points at regular intervals along a line, skipping given ranges.

    Args:
        line: LineString to sample along.
        spacing: float, alongshore interval in metres.
        skip_ranges: optional list of (start_m, end_m) tuples to exclude —
            typically hairpin locations from reference.hairpin_locations, where
            the line doubles back and a transect origin would be displaced.
        pad: float, extra margin in metres applied either side of each
            skip range. Should be at least the normal_direction window, so a
            chord cannot reach into a hairpin.

    Returns:
        d_along: (N,) array of retained distances along the line.
        points: list of N shapely Points at those distances.
    """

    # Guard against spacing <=0
    if spacing <= 0:
        raise ValueError(f'spacing must be positive, got {spacing}')

    d_along = np.arange(0, line.length, spacing)

    if skip_ranges:
        keep = np.ones(len(d_along), dtype=bool)
        for start, end in skip_ranges:
            keep &= ~((d_along >= start - pad) & (d_along <= end + pad))
        d_along = d_along[keep]

    points = [line.interpolate(x) for x in d_along]

    return d_along, points


def normal_direction(line, d, window=250):
    """Unit vector normal to the line at distance d, pointing seaward.

    Uses a chord between points `window` metres either side of d rather than
    adjacent vertices: at 15 m vertex spacing the local tangent is dominated by
    digitising noise. A window wide enough to span a hairpin (typically 200-400 m
    on this coast) also prevents spurs from distorting the direction.

    ASSUMES a south-to-north line with the sea to the east, as produced by
    reference.orient_south_north for Holderness. The tangent is rotated 90
    degrees clockwise, which is seaward under those conditions and landward on a
    west-facing coast. Verify empirically against MLW before trusting it.

    Args:
        line: LineString, oriented south to north.
        d: float, distance along the line in metres.
        window: float, half-width of the chord in metres.

    Returns:
        (2,) array, unit vector pointing seaward.

    Raises:
        ValueError: if the chord has zero length (the two points coincide).
    """

    # Take points before and after d
    p_before = line.interpolate(max(d - window, 0))
    p_after  = line.interpolate(min(d + window, line.length))

    # Tangent direction
    tx = p_after.x - p_before.x
    ty = p_after.y - p_before.y

    # Normal: tangent rotated 90 degrees clockwise (seaward for Holderness)
    nx = ty
    ny = -tx

    # Normalise to unit length
    length = np.hypot(nx, ny)
    if length == 0:
        raise ValueError(f'zero-length chord at d={d}: points coincide')
    nx, ny = nx / length, ny / length

    return np.array([nx, ny])


def build_transects(line, spacing=50, landward=120, seaward=250, name_prefix="HOL", window=250, skip_ranges=None, pad=None):
    """Cast shore-normal transects along a reference line.

    Returns:
        transects: dict of {name: (2, 2) array}, origin first then seaward end,
            in the line's CRS. This is the structure CoastSat expects for
            settings and for compute_intersection_QC.
        d_along: (N,) array of distances along the line for each transect,
            in the same order as sorted(transects).
    """

    if pad is None:
        pad = window

    d_along, points = sample_origins(line, spacing, skip_ranges, pad)

    transects = {}

    for i, (d, p) in enumerate(zip(d_along, points)):
        normal = normal_direction(line, d, window)
        centre = np.array([p.x, p.y])
        transects[f'{name_prefix}_{i:04d}'] = np.array([
            centre - landward * normal,
            centre + seaward * normal,
        ])

    return transects, d_along


def check_crossings(transects, neighbours=5):
    """Find transects that intersect their neighbours.

    Where the coast is concave, adjacent normals converge and their transects
    cross. Past the crossing point both sample the same water, so a single
    detected shoreline can register on both and one attributes it to the wrong
    alongshore position.

    Only near neighbours are tested: distant transects cannot cross without the
    coast doubling back, and all-pairs comparison is quadratic.

    Args:
        transects: dict of {name: (2, 2) array}, as returned by
            build_transects. Names must sort into alongshore order.
        neighbours: int, how many following transects each is tested against.

    Returns:
        List of (name_a, name_b) tuples for each intersecting pair. Empty list
        means none cross.
    """
    names = sorted(transects)
    lines = {n: LineString(transects[n]) for n in names}
    crossings = []
    for i, a in enumerate(names):
        for b in names[i + 1: i + 1 + neighbours]:
            if lines[a].intersects(lines[b]):
                crossings.append((a, b))
    return crossings


def classify_defence(d_along, defended, downdrift_m):
    """Label each transect by defence status.

    Drift on this coast is southward, so 'downdrift' means south of a defended
    frontage (lower alongshore distance, since the line runs south to north).
    """
    labels = np.full(len(d_along), 'natural', dtype=object)
    for start, end in defended.values():
        labels[(d_along >= start - downdrift_m) & (d_along < start)] = 'downdrift'
    for start, end in defended.values():
        labels[(d_along >= start) & (d_along <= end)] = 'defended'
    return labels


def transects_to_geojson(transects, path, epsg, labels=None):
    """Write transects to GeoJSON in the format CoastSat's reader expects.

    Sets the CRS explicitly: SDS_tools.transects_from_geojson calls
    gdf.crs.to_epsg(), which raises if the file carries no CRS. CoastSat's own
    transects_to_gdf does not set it.

    Args:
        transects: dict of {name: (2, 2) array}.
        path: output path.
        epsg: int, CRS of the coordinates.
        labels: optional dict of {name: str}, e.g. defence classification.
            Written as an extra 'defence' column. CoastSat's reader ignores
            columns other than 'name' and 'geometry'.
    """
    rows = []
    for k, v in transects.items():
        row = {'name': k, 'geometry': LineString(v)}
        if labels is not None:
            row['defence'] = labels[k]
        rows.append(row)

    gdf = gpd.GeoDataFrame(rows, crs=f'EPSG:{epsg}')
    gdf.to_file(path, driver='GeoJSON')
    return gdf


def transects_from_geojson(path):
    """Read transects written by transects_to_geojson.

    Mirrors SDS_tools.transects_from_geojson so files are interchangeable, but
    lives here because the coastsat package is only installed in the
    coastsat310 environment.
    """
    gdf = gpd.read_file(path)
    return {gdf.loc[i, 'name']: np.array(gdf.loc[i, 'geometry'].coords)
            for i in gdf.index}


def verify_seaward(transects, line_seaward, step=20):
    """Confirm every transect points seaward.

    Steps a short distance from the origin along the transect and checks that
    this moves closer to the seaward reference line. Comparing the two endpoints
    directly does not work: the transect extends well beyond MLW, so the seaward
    end can be further from it than the landward end while still pointing
    correctly.

    An inverted normal would flip every chainage in the analysis while producing
    outputs that look entirely plausible, so this is checked against data rather
    than assumed from the rotation sign.

    Returns list of names that fail; empty list means all correct.
    """
    bad = []
    for name, t in transects.items():
        v = t[1] - t[0]
        v = v / np.hypot(*v)
        d0 = line_seaward.distance(Point(t[0]))
        d1 = line_seaward.distance(Point(t[0] + step * v))
        if d1 >= d0:
            bad.append(name)
    return bad