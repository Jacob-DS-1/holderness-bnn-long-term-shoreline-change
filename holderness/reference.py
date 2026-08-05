"""Reference shoreline construction from OS OpenMap Local TidalBoundary.

Builds MHW, MLW and midline reference shorelines for use as
settings['reference_shoreline'] in CoastSat. All coordinates in EPSG:27700.

Functions take configuration as arguments and never import config, so they can
be called in a loop over boxes or variants.
"""

import pickle
from pathlib import Path

import numpy as np
import geopandas as gpd
from shapely.geometry import LineString, Point
from shapely.ops import linemerge, substring


def load_tidal_boundary(gml_path, layer, epsg):
    """Read GML, normalise CRS, split by classification, clean geometries.

    Returns (mhw, mlw, counts) where counts is keyed by 'mhw' and 'mlw'.
    """

    # Read GML
    gdf = gpd.read_file(gml_path, layer=layer)

    # Normalise CRS
    if gdf.crs is None:
        gdf = gdf.set_crs(f'EPSG:{epsg}')
    elif gdf.crs.to_epsg() != epsg:
        gdf = gdf.to_crs(f'EPSG:{epsg}')

    # Guard against classification differences
    classes = set(gdf['classification'].unique())
    expected = {'High Water Mark', 'Low Water Mark'}
    if not expected <= classes:
        raise ValueError(f'unexpected classifications: {classes}')

    mhw, counts_mhw = clean_geoms(gdf[gdf['classification'] == 'High Water Mark'])
    mlw, counts_mlw = clean_geoms(gdf[gdf['classification'] == 'Low Water Mark'])

    return mhw, mlw, {'mhw': counts_mhw, 'mlw': counts_mlw}


def clean_geoms(g):
    """Filter out invalid, empty, null and non-finite geometries.

    Note this contains a lambda function which calls x.coords which requires
    the layer is LineStrings not MultiLineString.

    Returns (filtered_gdf, counts) where counts records how many were dropped
    for each reason.
    """
    null = g.geometry.isna()
    finite = g.geometry.apply(
        lambda x: False if x is None else np.isfinite(np.asarray(x.coords)).all()
    )
    counts = {
        'n_in': len(g),
        'invalid': int((~g.geometry.is_valid).sum()),
        'empty': int(g.geometry.is_empty.sum()),
        'null': int(null.sum()),
        'non_finite': int((~finite).sum()),
    }
    keep = finite & g.geometry.is_valid & ~g.geometry.is_empty & ~null
    out = g[keep]
    counts['n_out'] = len(out)
    return out, counts


def longest_component(gdf_lines):
    """Merge all segments and return the single longest connected component."""
    merged = linemerge(gdf_lines.geometry.tolist())
    if merged.geom_type == 'LineString':
        return merged
    return max(merged.geoms, key=lambda g: g.length)


def orient_south_north(line):
    """Return the line traversed south to north.

    Assumes a broadly north-south coast, which holds for Holderness (endpoints
    differ by ~50 km in northing and ~9 km in easting).
    """
    if line.coords[0][1] > line.coords[-1][1]:
        return LineString(list(line.coords)[::-1])
    return line


def trim_between(line, p_start, p_end):
    """Cut the line between two anchor points using linear referencing."""
    a = line.project(Point(*p_start))
    b = line.project(Point(*p_end))
    return substring(line, min(a, b), max(a, b))


def build_reference_lines(gdf_lines, anchor_south, anchor_north, min_length=50_000):
    """Merge, orient and trim a set of line features into one reference line.

    Chains longest_component -> orient_south_north -> trim_between. The longest
    component of the OS TidalBoundary features is the open coast plus the Humber
    north bank; trimming between the anchors cuts it back to the open coast.

    Args:
        gdf_lines: GeoDataFrame of LineStrings for one classification.
        anchor_south: (easting, northing) tuple near the southern limit.
        anchor_north: (easting, northing) tuple near the northern limit.
        min_length: float, minimum acceptable length of the merged component in
            metres. Guards against the input having changed upstream.

    Returns:
        comp: LineString, the full merged component before trimming.
        line: LineString, trimmed between the anchors.
    """
    comp = longest_component(gdf_lines)
    if comp.length < min_length:
        raise ValueError(
            f'longest component is {comp.length:.0f} m, expected at least {min_length}'
        )
    comp = orient_south_north(comp)

    line = trim_between(comp, anchor_south, anchor_north)
    if line.geom_type != 'LineString':
        raise ValueError(f'trim produced {line.geom_type}, expected LineString')

    return comp, line


def hairpin_ratio(line, step=10, lag=20):
    """Straight-line / along-line distance over a fixed lag. ~1 is healthy, ->0 is a hairpin."""
    d = np.arange(0, line.length, step)
    pts = np.array([[p.x, p.y] for p in (line.interpolate(x) for x in d)])
    straight = np.linalg.norm(pts[lag:] - pts[:-lag], axis=1)
    return d[:-lag], straight / (step * lag)


def hairpin_locations(line, thresh=0.5, gap=5, **kw):
    """Locate hairpin spurs along a line.

    OS traces up and back along drain and outfall channels crossing the
    foreshore, producing narrow spurs typically 200-400 m long and under 20 m
    wide. These are genuine mapped geometry, not merge artefacts.

    Runs hairpin_ratio and groups contiguous runs of low-ratio samples into
    discrete features. Samples separated by fewer than `gap` indices are treated
    as one hairpin, so a single spur isn't reported as several.

    Not fixed here, deliberately: Douglas-Peucker preserves them (a hairpin tip
    is an extreme point) and moving-average smoothing displaces the line by
    >100 m before removing them. They are harmless as a buffer centre, mildly
    untidy in the midline, and problematic only for shore-normal transects,
    where they are handled instead.

    Args:
        line: LineString to inspect.
        thresh: float, ratio below which a sample is flagged. 0.5 catches the
            spurs on Holderness without flagging normal coastal curvature.
        gap: int, maximum index separation for flagged samples to be grouped
            into one hairpin.
        **kw: forwarded to hairpin_ratio (step, lag).

    Returns:
        List of (start_m, end_m) tuples giving each hairpin's extent as
        distance along the line. Empty list if none found.
    """

    d, r = hairpin_ratio(line, **kw)
    idx = np.where(r < thresh)[0]
    if len(idx) == 0:
        return []
    groups = np.split(idx, np.where(np.diff(idx) > gap)[0] + 1)
    return [(float(d[g[0]]), float(d[g[-1]])) for g in groups if len(g)]


def separation_profile(line_mhw, line_mlw, step):
    """Measure intertidal width along the MHW line.

    Samples `line_mhw` at regular intervals and measures the distance from each
    sample to the nearest point on `line_mlw`. This is the horizontal width of
    the intertidal zone, used to size the tidal component of `max_dist_ref` and
    as an independent cross-check on beach slopes from SDS_slope.

    Note this is nearest-point distance, not shore-normal width; the two differ
    slightly where the coast curves. Nearest-point is the conservative choice
    for sizing a buffer.

    Both lines must be in the same projected CRS (EPSG:27700 here) and oriented
    the same way along the coast.

    Args:
        line_mhw: LineString, mean high water, already trimmed to the reach.
        line_mlw: LineString, mean low water, covering the same reach.
        step: float, alongshore sampling interval in metres.

    Returns:
        d_along: (N,) array of distances along line_mhw, from 0 in steps of
            `step`. The final sample falls short of the line end by up to `step`.
        pts_mhw: list of N shapely Points, the sample locations. Returned so
            build_midline can reuse them rather than resampling.
        sep: (N,) array of distances to the nearest point on line_mlw, in metres.
    """

    # Guard against step <=0
    if step <= 0:
        raise ValueError(f'step must be positive, got {step}')

    d_along = np.arange(0, line_mhw.length, step)
    pts_mhw = [line_mhw.interpolate(x) for x in d_along]
    sep = np.array([line_mlw.distance(p) for p in pts_mhw])

    return d_along, pts_mhw, sep


def build_midline(pts_mhw, line_mlw):
    """Construct a reference line midway between MHW and MLW.

    For each MHW sample, finds the nearest point on line_mlw and takes the
    midpoint of the pair. Pairing via nearest-point projection rather than
    matching vertices directly, because the two lines have very different
    vertex densities (MLW is more crenulate, following bar and runnel
    morphology).

    Centring the reference on the tidal envelope rather than on MHW lets a
    tighter max_dist_ref cover the same range of waterline positions.

    Args:
        pts_mhw: list of N shapely Points sampled along MHW, from
            separation_profile.
        line_mlw: LineString, mean low water over the same reach.

    Returns:
        line_midline: LineString through the N midpoints.
        ratio: (N,) array of (distance from midline to MHW) / (separation / 2).
            Should be ~1.0 everywhere; departures indicate bad pairing, usually
            where the coast curves sharply.
    """
    pts_mlw = [line_mlw.interpolate(line_mlw.project(p)) for p in pts_mhw]

    a = np.array([[p.x, p.y] for p in pts_mhw])
    b = np.array([[p.x, p.y] for p in pts_mlw])
    mid = (a + b) / 2

    sep = np.linalg.norm(b - a, axis=1)
    # Guard against division by zero
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = np.where(sep > 0, np.linalg.norm(mid - a, axis=1) / (sep / 2), np.nan)

    return LineString(mid), ratio


def densify(line, step):
    """Resample a line to approximately even vertex spacing.

    CoastSat builds a distance buffer around the reference shoreline, so vertex
    spacing must be well below the intended max_dist_ref or the buffer edge
    becomes faceted. A target of 10-20 m suits a buffer of ~100-250 m.

    Uses linspace rather than arange so the final vertex lands exactly on the
    line end and spacing stays uniform; arange would leave a short remainder
    segment. Actual spacing is therefore slightly below `step`.

    Note this resamples along the existing line, so it interpolates between
    vertices but never smooths or removes them.

    Args:
        line: LineString to resample.
        step: float, target vertex spacing in metres.

    Returns:
        (N, 2) array of coordinates in the line's CRS, suitable for use
        directly as settings['reference_shoreline'].
    """

    n = max(int(np.ceil(line.length / step)) + 1, 2)
    d = np.linspace(0, line.length, n)
    return np.array([[p.x, p.y] for p in (line.interpolate(x) for x in d)])


def save_reference(arr, path):
    """Write a reference shoreline array to disk.

    Args:
        arr: (N, 2) array of coordinates in EPSG:27700.
        path: Path to write to.
    """
    arr = np.asarray(arr)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(f'expected (N, 2) array, got {arr.shape}')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'wb') as f:
        pickle.dump(arr, f)


def load_reference(path):
    """Read a reference shoreline array written by save_reference.

    Returns an (N, 2) array in EPSG:27700, suitable for use directly as
    settings['reference_shoreline'].
    """
    with open(path, 'rb') as f:
        arr = pickle.load(f)
    arr = np.asarray(arr)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(f'{path} does not contain an (N, 2) array: {arr.shape}')
    return arr