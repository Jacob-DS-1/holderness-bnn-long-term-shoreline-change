"""Image-availability queries and manifests.

This module queries metadata only. It never downloads imagery.
"""

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from holderness import coastsat_api, config


SCENE_COLUMNS = [
    'stream',
    'roi_id',
    'sensor',
    'source_scene_id',
    'source_product_id',
    'system_index',
    'acquisition_time_utc',
    'acquisition_year',
    'decade',
    'season',
    'meteorological_quarter',
    'gee_collection',
    'collection_version',
    'wrs_path',
    'wrs_row',
    'cloud_cover_pct',
    'geometric_rmse_m',
    'primary_geometry_eligible',
    'geometry_exclusion_reason',
    'metadata_retrieved_at_utc',
]


def connect_to_earth_engine(project, coastsat_dir):
    """Authenticate through CoastSat and return its download module."""
    coastsat_api.activate_checkout(coastsat_dir)
    try:
        from coastsat import SDS_download
    except ImportError as error:
        raise RuntimeError(
            'CoastSat is not installed; run this in the pinned CoastSat environment'
        ) from error

    SDS_download.authenticate_and_initialize(project)
    return SDS_download


def build_query_plan(rois, stream, sensors, dates, collections):
    """Describe the metadata queries without connecting to Earth Engine."""
    records = []
    for roi_id in rois['roi_id']:
        for sensor in sensors:
            records.append({
                'stream': stream,
                'roi_id': roi_id,
                'sensor': sensor,
                'gee_collection': collections[sensor],
                'date_start': dates[0],
                'date_end': dates[1],
            })
    return pd.DataFrame(records)


def _coastsat_polygon(shape):
    if shape.geom_type == 'MultiPolygon':
        shape = max(shape.geoms, key=lambda part: part.area)
    if shape.geom_type != 'Polygon':
        raise ValueError(f'ROI geometry is {shape.geom_type}, expected Polygon')
    return [[[float(x), float(y)] for x, y in shape.exterior.coords]]


def _first(properties, *names):
    for name in names:
        value = properties.get(name)
        if value is not None:
            return value
    return None


def _as_float(value):
    if value is None:
        return None
    return float(value)


def _collection_version(collection):
    for part in collection.split('/'):
        if len(part) == 3 and part.startswith('C') and part[1:].isdigit():
            return part
    return collection.rsplit('/', 1)[-1]


def _season_fields(acquisition_time):
    timestamp = pd.Timestamp(acquisition_time)
    month = timestamp.month
    if month in (12, 1, 2):
        season = 'DJF'
        meteorological_year = timestamp.year + (month == 12)
    elif month in (3, 4, 5):
        season = 'MAM'
        meteorological_year = timestamp.year
    elif month in (6, 7, 8):
        season = 'JJA'
        meteorological_year = timestamp.year
    else:
        season = 'SON'
        meteorological_year = timestamp.year

    return {
        'acquisition_year': timestamp.year,
        'decade': f'{timestamp.year // 10 * 10}s',
        'season': season,
        'meteorological_quarter': f'{meteorological_year}-{season}',
    }


def _scene_record(image, stream, roi_id, sensor, collection,
                  metadata_retrieved_at, max_geometric_rmse):
    properties = image.get('properties', {})
    milliseconds = properties.get('system:time_start')
    if milliseconds is None:
        raise ValueError(f'image {image.get("id")} has no system:time_start')

    acquisition_time = datetime.fromtimestamp(
        milliseconds / 1000, tz=timezone.utc
    ).isoformat().replace('+00:00', 'Z')

    source_scene_id = image.get('id') or properties.get('system:index')
    if not source_scene_id:
        raise ValueError('image has no source scene identifier')

    product_id = _first(
        properties, 'LANDSAT_PRODUCT_ID', 'PRODUCT_ID', 'system:index'
    )
    cloud_cover = _as_float(_first(
        properties, 'CLOUD_COVER', 'CLOUDY_PIXEL_PERCENTAGE'
    ))
    geometric_rmse = _as_float(properties.get('GEOMETRIC_RMSE_MODEL'))
    geometry_eligible = (
        stream == 'landsat'
        and geometric_rmse is not None
        and geometric_rmse <= max_geometric_rmse
    )
    if stream != 'landsat':
        geometry_exclusion_reason = 'not_applicable_to_validation_stream'
    elif geometric_rmse is None:
        geometry_exclusion_reason = 'missing_geometric_rmse'
    elif geometric_rmse > max_geometric_rmse:
        geometry_exclusion_reason = 'geometric_rmse_above_limit'
    else:
        geometry_exclusion_reason = ''

    record = {
        'stream': stream,
        'roi_id': roi_id,
        'sensor': sensor,
        'source_scene_id': source_scene_id,
        'source_product_id': product_id,
        'system_index': properties.get('system:index'),
        'acquisition_time_utc': acquisition_time,
        'gee_collection': collection,
        'collection_version': _collection_version(collection),
        'wrs_path': properties.get('WRS_PATH'),
        'wrs_row': properties.get('WRS_ROW'),
        'cloud_cover_pct': cloud_cover,
        'geometric_rmse_m': geometric_rmse,
        'primary_geometry_eligible': geometry_eligible,
        'geometry_exclusion_reason': geometry_exclusion_reason,
        'metadata_retrieved_at_utc': metadata_retrieved_at,
    }
    record.update(_season_fields(acquisition_time))
    return record


def query_scene_availability(rois, stream, sensors, dates, collections,
                             download_module, max_geometric_rmse=10,
                             metadata_retrieved_at=None):
    """Query scene metadata for each ROI and return one manifest table."""
    required = {'roi_id', 'geometry'}
    missing = required.difference(rois.columns)
    if missing:
        raise ValueError(f'missing ROI columns: {sorted(missing)}')
    if rois.crs is None:
        raise ValueError('ROIs have no CRS')

    metadata_retrieved_at = metadata_retrieved_at or datetime.now(
        timezone.utc
    ).isoformat().replace('+00:00', 'Z')

    records = []
    rois_wgs84 = rois.to_crs(epsg=4326)
    for roi in rois_wgs84.itertuples():
        polygon = _coastsat_polygon(roi.geometry)
        for sensor in sensors:
            collection = collections[sensor]
            images = download_module.get_image_info(
                collection, sensor, polygon, list(dates)
            )
            if sensor == 'S2':
                images = download_module.filter_S2_collection(images)

            for image in images:
                records.append(_scene_record(
                    image,
                    stream=stream,
                    roi_id=roi.roi_id,
                    sensor=sensor,
                    collection=collection,
                    metadata_retrieved_at=metadata_retrieved_at,
                    max_geometric_rmse=max_geometric_rmse,
                ))

    scenes = pd.DataFrame(records, columns=SCENE_COLUMNS)
    if scenes.empty:
        return scenes
    return scenes.sort_values(
        ['roi_id', 'acquisition_time_utc', 'sensor', 'source_scene_id']
    ).reset_index(drop=True)


def quarterly_availability(scenes):
    """Count candidate scenes by ROI, mission and meteorological quarter."""
    columns = [
        'stream', 'roi_id', 'sensor', 'decade', 'season',
        'meteorological_quarter', 'scene_count', 'unique_scene_count',
        'geometry_eligible_count',
    ]
    if scenes.empty:
        return pd.DataFrame(columns=columns)

    grouped = scenes.groupby([
        'stream', 'roi_id', 'sensor', 'decade', 'season',
        'meteorological_quarter',
    ], dropna=False)
    counts = grouped.agg(
        scene_count=('source_scene_id', 'size'),
        unique_scene_count=('source_scene_id', 'nunique'),
        geometry_eligible_count=('primary_geometry_eligible', 'sum'),
    )
    return counts.reset_index().sort_values(
        ['roi_id', 'meteorological_quarter', 'sensor']
    ).reset_index(drop=True)


def _coverage_summary(scenes):
    """Return compact temporal coverage statistics for one scene table."""
    if scenes.empty:
        return {
            'roi_scene_rows': 0,
            'unique_scene_ids': 0,
            'distinct_acquisition_years': 0,
            'populated_meteorological_quarters': 0,
            'first_acquisition_time_utc': None,
            'last_acquisition_time_utc': None,
        }

    times = pd.to_datetime(
        scenes['acquisition_time_utc'], utc=True, format='mixed'
    )
    return {
        'roi_scene_rows': len(scenes),
        'unique_scene_ids': int(scenes['source_scene_id'].nunique()),
        'distinct_acquisition_years': int(
            scenes['acquisition_year'].nunique()
        ),
        'populated_meteorological_quarters': int(
            scenes['meteorological_quarter'].nunique()
        ),
        'first_acquisition_time_utc': times.min().isoformat().replace(
            '+00:00', 'Z'
        ),
        'last_acquisition_time_utc': times.max().isoformat().replace(
            '+00:00', 'Z'
        ),
    }


def _grouped_coverage(scenes, column):
    """Summarise all and geometrically eligible scenes by one dimension."""
    result = {}
    for value, group in scenes.groupby(column, sort=True):
        eligible = group[group['primary_geometry_eligible']]
        result[str(value)] = {
            'all_candidates': _coverage_summary(group),
            'primary_geometry_eligible': _coverage_summary(eligible),
        }
    return result


def write_availability_manifests(scenes, output_dir, stream):
    """Write scene, quarterly and summary availability files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scene_path = output_dir / f'{stream}-scene-availability.csv'
    quarter_path = output_dir / f'{stream}-quarterly-availability.csv'
    summary_path = output_dir / f'{stream}-availability-summary.json'

    quarters = quarterly_availability(scenes)
    scenes.to_csv(scene_path, index=False)
    quarters.to_csv(quarter_path, index=False)

    eligible = scenes[scenes['primary_geometry_eligible']]
    summary = {
        'stream': stream,
        'scene_rows': len(scenes),
        'unique_scene_ids': int(scenes['source_scene_id'].nunique()),
        'primary_geometry_eligible_scene_rows': len(eligible),
        'primary_geometry_eligible_unique_scene_ids': int(
            eligible['source_scene_id'].nunique()
        ),
        'roi_count': int(scenes['roi_id'].nunique()),
        'sensors': sorted(scenes['sensor'].dropna().unique().tolist()),
        'retrieval_timestamps_utc': sorted(
            scenes['metadata_retrieved_at_utc'].dropna().unique().tolist()
        ),
        'catalog_prefilter': {
            'field': 'provider scene-wide cloud cover percentage',
            'maximum_inclusive': (
                config.COASTSAT_AVAILABILITY_MAX_CLOUD_COVER_PCT
            ),
            'applied_by': 'pinned CoastSat SDS_download.get_image_info',
        },
        'primary_geometry_rule': {
            'field': 'GEOMETRIC_RMSE_MODEL',
            'maximum_inclusive_m': config.LANDSAT_MAX_GEOMETRIC_RMSE_M,
            'missing_values_eligible': False,
        },
        'coverage': {
            'all_candidates': _coverage_summary(scenes),
            'primary_geometry_eligible': _coverage_summary(eligible),
            'by_sensor': _grouped_coverage(scenes, 'sensor'),
            'by_roi': _grouped_coverage(scenes, 'roi_id'),
        },
        'scene_manifest': scene_path.name,
        'quarterly_manifest': quarter_path.name,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + '\n')
    return scene_path, quarter_path, summary_path
