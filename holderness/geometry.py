"""Geometry preparation for the Holderness shoreline workflow.

The OS OpenMap Local tidal boundary is used only to build a provisional
geometry seed. It is not a dated shoreline observation and must not be used as
the final reference line. Final transects will be cast from a smoothed
mid-record satellite-derived reference line after the pilot.

All distances are metres in EPSG:27700 unless stated otherwise.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely import get_coordinates
from shapely.geometry import LineString, Point
from shapely.ops import linemerge, substring


MHW_CLASS = 'High Water Mark'
MLW_CLASS = 'Low Water Mark'


def _has_finite_coordinates(shape):
    if shape is None or shape.is_empty:
        return False
    coordinates = get_coordinates(shape)
    return coordinates.size > 0 and np.isfinite(coordinates).all()


def clean_geometries(frame):
    """Remove null, empty, invalid and non-finite geometries."""
    null = frame.geometry.isna()
    empty = frame.geometry.is_empty
    valid = frame.geometry.is_valid
    finite = frame.geometry.apply(_has_finite_coordinates)

    counts = {
        'n_in': len(frame),
        'invalid': int((~valid).sum()),
        'empty': int(empty.sum()),
        'null': int(null.sum()),
        'non_finite': int((~finite).sum()),
    }
    cleaned = frame[valid & ~empty & ~null & finite].copy()
    counts['n_out'] = len(cleaned)
    return cleaned, counts


def load_os_tidal_boundaries(gml_path, layer, epsg):
    """Load and clean the OS high- and low-water boundary features."""
    frame = gpd.read_file(gml_path, layer=layer)

    if frame.crs is None:
        frame = frame.set_crs(epsg=epsg)
    elif frame.crs.to_epsg() != epsg:
        frame = frame.to_crs(epsg=epsg)

    if 'classification' not in frame.columns:
        raise ValueError('OS tidal boundary has no classification column')

    classes = set(frame['classification'].dropna().unique())
    expected = {MHW_CLASS, MLW_CLASS}
    if not expected.issubset(classes):
        raise ValueError(f'unexpected classifications: {classes}')

    boundaries = {}
    counts = {}
    for name, classification in [('mhw', MHW_CLASS), ('mlw', MLW_CLASS)]:
        selected = frame[frame['classification'] == classification]
        boundaries[name], counts[name] = clean_geometries(selected)

    return boundaries, counts


def longest_component(lines):
    """Merge line features and return the longest connected component."""
    if len(lines) == 0:
        raise ValueError('no line features supplied')

    merged = linemerge(lines.geometry.tolist())
    if merged.geom_type == 'LineString':
        return merged
    return max(merged.geoms, key=lambda shape: shape.length)


def orient_south_to_north(line):
    """Return a Holderness coastal line ordered from south to north."""
    if line.coords[0][1] > line.coords[-1][1]:
        return LineString(list(line.coords)[::-1])
    return line


def trim_between(line, start, end):
    """Trim a line between two points using distance along the line."""
    start_distance = line.project(Point(*start))
    end_distance = line.project(Point(*end))
    return substring(line, min(start_distance, end_distance),
                     max(start_distance, end_distance))


def build_boundary_line(lines, anchor_south, anchor_north,
                        min_component_length=50_000):
    """Merge, orient and trim one OS tidal-boundary classification."""
    component = orient_south_to_north(longest_component(lines))
    if component.length < min_component_length:
        raise ValueError(
            f'longest component is {component.length:.0f} m, '
            f'expected at least {min_component_length}'
        )

    line = trim_between(component, anchor_south, anchor_north)
    if line.geom_type != 'LineString':
        raise ValueError(f'trim produced {line.geom_type}, expected LineString')
    return line


def hairpin_ratio(line, step=10, lag=20):
    """Return straight-line / along-line distance for detecting narrow spurs."""
    if step <= 0 or lag <= 0:
        raise ValueError('step and lag must be positive')

    distances = np.arange(0, line.length, step)
    if len(distances) <= lag:
        raise ValueError('line is too short for the requested step and lag')

    points = np.array([
        [point.x, point.y]
        for point in (line.interpolate(distance) for distance in distances)
    ])
    straight = np.linalg.norm(points[lag:] - points[:-lag], axis=1)
    return distances[:-lag], straight / (step * lag)


def hairpin_ranges(line, threshold=0.5, gap=5, step=10, lag=20):
    """Return along-line ranges containing OS drainage and outfall spurs."""
    distances, ratios = hairpin_ratio(line, step=step, lag=lag)
    flagged = np.where(ratios < threshold)[0]
    if len(flagged) == 0:
        return []

    groups = np.split(flagged, np.where(np.diff(flagged) > gap)[0] + 1)
    return [(float(distances[group[0]]), float(distances[group[-1]]))
            for group in groups]


def build_os_seed(mhw_line, mlw_line, step=25):
    """Build a provisional line midway between the OS MHW and MLW lines.

    Returns the seed LineString, MHW chainages and measured intertidal widths.
    The result is a geometry aid only, not the final analysis reference line.
    """
    if step <= 0:
        raise ValueError(f'step must be positive, got {step}')

    chainages = np.arange(0, mhw_line.length, step)
    mhw_points = [mhw_line.interpolate(distance) for distance in chainages]
    mlw_points = [
        mlw_line.interpolate(mlw_line.project(point)) for point in mhw_points
    ]

    mhw_xy = np.array([[point.x, point.y] for point in mhw_points])
    mlw_xy = np.array([[point.x, point.y] for point in mlw_points])
    widths = np.linalg.norm(mlw_xy - mhw_xy, axis=1)
    seed = LineString((mhw_xy + mlw_xy) / 2)
    return seed, chainages, widths


def seed_geodataframe(seed, epsg, site='holderness'):
    """Wrap an OS seed line with metadata that clearly marks it provisional."""
    return gpd.GeoDataFrame([{
        'geometry_id': f'{site}_os_seed',
        'role': 'provisional_geometry_seed',
        'source': 'OS OpenMap Local TidalBoundary',
        'provisional': True,
        'geometry': seed,
    }], crs=f'EPSG:{epsg}')


def sample_chainages(line, spacing, exclude_ranges=None, pad=0):
    """Sample fixed chainages, optionally omitting specified ranges."""
    if spacing <= 0:
        raise ValueError(f'spacing must be positive, got {spacing}')

    chainages = np.arange(0, line.length, spacing, dtype=float)
    if exclude_ranges:
        keep = np.ones(len(chainages), dtype=bool)
        for start, end in exclude_ranges:
            keep &= ~((chainages >= start - pad) & (chainages <= end + pad))
        chainages = chainages[keep]
    return chainages


def seaward_normal(line, chainage, window=250):
    """Return the eastward normal for a south-to-north Holderness line."""
    if window <= 0:
        raise ValueError(f'window must be positive, got {window}')

    before = line.interpolate(max(chainage - window, 0))
    after = line.interpolate(min(chainage + window, line.length))
    tangent = np.array([after.x - before.x, after.y - before.y])
    normal = np.array([tangent[1], -tangent[0]])
    length = np.linalg.norm(normal)
    if length == 0:
        raise ValueError(f'zero-length chord at chainage {chainage}')
    return normal / length


def transect_id(chainage, prefix='HOL'):
    """Create a permanent transect identifier from integer-metre chainage."""
    rounded = round(chainage)
    if not np.isclose(chainage, rounded, atol=1e-6):
        raise ValueError('transect identifiers require whole-metre chainage')
    return f'{prefix}_{int(rounded):05d}'


def build_transects(reference_line, epsg, spacing=50, landward=300,
                    seaward=300, window=250, prefix='HOL',
                    exclude_ranges=None, exclude_pad=0):
    """Cast fixed shore-normal transects from a final reference line.

    The first coordinate is landward and the last is seaward. IDs are based on
    chainage, so omitting a transect never renumbers those that follow it.
    """
    if landward <= 0 or seaward <= 0:
        raise ValueError('landward and seaward extents must be positive')

    records = []
    chainages = sample_chainages(reference_line, spacing, exclude_ranges,
                                 exclude_pad)
    for chainage in chainages:
        centre_point = reference_line.interpolate(chainage)
        centre = np.array([centre_point.x, centre_point.y])
        normal = seaward_normal(reference_line, chainage, window)
        records.append({
            'transect_id': transect_id(chainage, prefix),
            'chainage_m': float(chainage),
            'geometry': LineString([
                centre - landward * normal,
                centre + seaward * normal,
            ]),
        })

    return gpd.GeoDataFrame(records, geometry='geometry', crs=f'EPSG:{epsg}')


def subset_transects(transects, spacing, origin=0):
    """Select a deterministic chainage-aligned subset of master transects."""
    if spacing <= 0:
        raise ValueError(f'spacing must be positive, got {spacing}')
    if 'chainage_m' not in transects.columns:
        raise ValueError('transects have no chainage_m column')

    remainder = np.mod(transects['chainage_m'].to_numpy() - origin, spacing)
    keep = np.isclose(remainder, 0, atol=1e-6)
    subset = transects.loc[keep].copy()
    return subset.sort_values('chainage_m').reset_index(drop=True)


def find_crossings(transects, neighbours=5):
    """Return IDs of nearby transect pairs whose geometries intersect."""
    ordered = transects.sort_values('chainage_m').reset_index(drop=True)
    crossings = []
    for i, first in ordered.iterrows():
        following = ordered.iloc[i + 1:i + 1 + neighbours]
        for second in following.itertuples():
            if first.geometry.intersects(second.geometry):
                crossings.append((first.transect_id, second.transect_id))
    return crossings


def verify_seaward(transects, seaward_line, step=20):
    """Return IDs whose stored direction does not move toward a seaward line."""
    failures = []
    for row in transects.itertuples():
        coordinates = np.asarray(row.geometry.coords)
        direction = coordinates[-1] - coordinates[0]
        direction = direction / np.linalg.norm(direction)
        start = coordinates[0]
        if seaward_line.distance(Point(start + step * direction)) >= \
                seaward_line.distance(Point(start)):
            failures.append(row.transect_id)
    return failures


def write_geojson(frame, path):
    """Write project geometry to GeoJSON with its CRS and attributes."""
    if frame.crs is None:
        raise ValueError('geometry has no CRS')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path, driver='GeoJSON', index=False)


def read_geojson(path):
    """Read project geometry from GeoJSON."""
    return gpd.read_file(path)
