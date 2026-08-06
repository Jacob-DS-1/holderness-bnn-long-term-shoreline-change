"""Small conversions between project geometry and CoastSat inputs.

GeoJSON geometry is authoritative. The NumPy arrays and dictionaries returned
here are created in memory only when calling CoastSat.
"""

import numpy as np


def reference_line_to_array(line, spacing=15):
    """Sample a reference LineString into the ``(N, 2)`` array CoastSat uses."""
    if line.geom_type != 'LineString':
        raise ValueError(f'expected LineString, got {line.geom_type}')
    if spacing <= 0:
        raise ValueError(f'spacing must be positive, got {spacing}')

    n_points = max(int(np.ceil(line.length / spacing)) + 1, 2)
    distances = np.linspace(0, line.length, n_points)
    return np.array([[point.x, point.y]
                     for point in (line.interpolate(d) for d in distances)])


def transects_to_dict(transects):
    """Convert the project transect GeoDataFrame to CoastSat's dictionary."""
    required = {'transect_id', 'chainage_m', 'geometry'}
    missing = required.difference(transects.columns)
    if missing:
        raise ValueError(f'missing transect columns: {sorted(missing)}')

    ordered = transects.sort_values('chainage_m')
    return {
        row.transect_id: np.asarray(row.geometry.coords, dtype=float)
        for row in ordered.itertuples()
    }
