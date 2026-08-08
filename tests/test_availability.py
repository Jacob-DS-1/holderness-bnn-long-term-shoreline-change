"""Tests for metadata-only availability and pilot preparation."""

import json

import pandas as pd
import pytest
from shapely.geometry import LineString

from holderness import availability, config, geometry, pilot


class FakeDownloadModule:
    def __init__(self, images):
        self.images = images
        self.calls = []
        self.sentinel_filter_called = False

    def get_image_info(self, collection, sensor, polygon, dates):
        self.calls.append((collection, sensor, polygon, dates))
        return self.images

    def filter_S2_collection(self, images):
        self.sentinel_filter_called = True
        return images


def one_roi():
    line = LineString([(0, 0), (0, 1000)])
    return geometry.build_rois(
        line, epsg=27700, length=1000, overlap=0, half_width=250
    )


def landsat_image(scene_id='LANDSAT/TEST/SCENE_1', rmse=7.5):
    return {
        'id': scene_id,
        'properties': {
            'system:index': scene_id.rsplit('/', 1)[-1],
            'system:time_start': int(
                pd.Timestamp('2020-12-15T10:30:00Z').timestamp() * 1000
            ),
            'LANDSAT_PRODUCT_ID': 'LC08_TEST_PRODUCT',
            'WRS_PATH': 32,
            'WRS_ROW': 23,
            'CLOUD_COVER': 0,
            'GEOMETRIC_RMSE_MODEL': rmse,
        },
    }


def pilot_scene_row(scene_id, roi_id, sensor='L8'):
    return {
        'stream': 'landsat',
        'roi_id': roi_id,
        'sensor': sensor,
        'source_scene_id': scene_id,
        'source_product_id': f'{scene_id}_PRODUCT',
        'system_index': scene_id,
        'acquisition_time_utc': '2020-06-01T10:30:00Z',
        'acquisition_year': 2020,
        'decade': '2020s',
        'season': 'JJA',
        'meteorological_quarter': '2020-JJA',
        'gee_collection': 'LANDSAT/LC08/C02/T1_TOA',
        'collection_version': 'C02',
        'wrs_path': 202,
        'wrs_row': 22,
        'cloud_cover_pct': 5.0,
        'geometric_rmse_m': 7.5,
        'primary_geometry_eligible': True,
        'geometry_exclusion_reason': '',
        'metadata_retrieved_at_utc': '2026-08-06T12:00:00Z',
    }


def test_dry_query_plan_keeps_imagery_streams_explicit():
    plan = availability.build_query_plan(
        one_roi(),
        stream='landsat',
        sensors=config.LANDSAT_SENSORS,
        dates=config.LANDSAT_DATES,
        collections=config.LANDSAT_GEE_COLLECTIONS,
    )
    assert len(plan) == 4
    assert set(plan.sensor) == {'L5', 'L7', 'L8', 'L9'}
    assert set(plan.stream) == {'landsat'}


def test_scene_manifest_preserves_required_metadata():
    fake = FakeDownloadModule([landsat_image()])
    scenes = availability.query_scene_availability(
        one_roi(),
        stream='landsat',
        sensors=('L8',),
        dates=config.LANDSAT_DATES,
        collections={'L8': config.LANDSAT_GEE_COLLECTIONS['L8']},
        download_module=fake,
        metadata_retrieved_at='2026-08-06T12:00:00Z',
    )
    scene = scenes.iloc[0]

    assert scene.source_scene_id == 'LANDSAT/TEST/SCENE_1'
    assert scene.acquisition_time_utc == '2020-12-15T10:30:00Z'
    assert scene.gee_collection == 'LANDSAT/LC08/C02/T1_TOA'
    assert scene.collection_version == 'C02'
    assert scene.wrs_path == 32
    assert scene.wrs_row == 23
    assert scene.cloud_cover_pct == 0
    assert scene.geometric_rmse_m == 7.5
    assert bool(scene.primary_geometry_eligible) is True
    assert scene.meteorological_quarter == '2021-DJF'
    assert scene.metadata_retrieved_at_utc == '2026-08-06T12:00:00Z'


def test_missing_geometric_rmse_is_not_primary_eligible():
    fake = FakeDownloadModule([landsat_image(rmse=None)])
    scenes = availability.query_scene_availability(
        one_roi(), 'landsat', ('L8',), config.LANDSAT_DATES,
        {'L8': config.LANDSAT_GEE_COLLECTIONS['L8']}, fake,
    )
    assert bool(scenes.iloc[0].primary_geometry_eligible) is False
    assert scenes.iloc[0].geometry_exclusion_reason == 'missing_geometric_rmse'


def test_quarterly_and_summary_manifests(tmp_path):
    fake = FakeDownloadModule([
        landsat_image('LANDSAT/TEST/SCENE_1'),
        landsat_image('LANDSAT/TEST/SCENE_2'),
    ])
    scenes = availability.query_scene_availability(
        one_roi(), 'landsat', ('L8',), config.LANDSAT_DATES,
        {'L8': config.LANDSAT_GEE_COLLECTIONS['L8']}, fake,
    )
    scene_path, quarter_path, summary_path = \
        availability.write_availability_manifests(scenes, tmp_path, 'landsat')

    quarters = pd.read_csv(quarter_path)
    summary = json.loads(summary_path.read_text())
    assert scene_path.exists()
    assert quarters.iloc[0].scene_count == 2
    assert quarters.iloc[0].unique_scene_count == 2
    assert summary['unique_scene_ids'] == 2
    assert summary['primary_geometry_eligible_unique_scene_ids'] == 2
    assert summary['catalog_prefilter']['maximum_inclusive'] == 95
    sensor_coverage = summary['coverage']['by_sensor']['L8']
    assert sensor_coverage['all_candidates']['unique_scene_ids'] == 2
    assert sensor_coverage['primary_geometry_eligible'][
        'populated_meteorological_quarters'
    ] == 1
    roi_coverage = summary['coverage']['by_roi']['HOL_ROI_01']
    assert roi_coverage['all_candidates']['first_acquisition_time_utc'] == (
        '2020-12-15T10:30:00Z'
    )


def test_pilot_pool_is_reproducible_and_excludes_ineligible_scenes():
    scenes = pd.DataFrame([
        {
            'stream': 'landsat', 'roi_id': 'HOL_ROI_01', 'sensor': 'L8',
            'source_scene_id': 'A', 'acquisition_time_utc': '2020-06-01T00:00:00Z',
            'decade': '2020s', 'season': 'JJA',
            'primary_geometry_eligible': True,
        },
        {
            'stream': 'landsat', 'roi_id': 'HOL_ROI_01', 'sensor': 'L8',
            'source_scene_id': 'B', 'acquisition_time_utc': '2020-07-01T00:00:00Z',
            'decade': '2020s', 'season': 'JJA',
            'primary_geometry_eligible': True,
        },
        {
            'stream': 'landsat', 'roi_id': 'HOL_ROI_01', 'sensor': 'L8',
            'source_scene_id': 'C', 'acquisition_time_utc': '2020-08-01T00:00:00Z',
            'decade': '2020s', 'season': 'JJA',
            'primary_geometry_eligible': False,
        },
    ])

    first = pilot.select_candidate_pool(scenes, per_stratum=1, seed=42)
    second = pilot.select_candidate_pool(scenes, per_stratum=1, seed=42)
    assert list(first.source_scene_id) == list(second.source_scene_id)
    assert 'C' not in set(first.source_scene_id)
    assert pilot.PENDING_SCENE_LABEL_COLUMNS == ('water_level_band',)
    assert first['water_level_band'].eq('').all()
    assert set(first['pilot_status']) == {pilot.SCENE_CANDIDATE_POOL_STATUS}
    roi_context_fields = {
        'defence_status',
        'coastal_regime',
        'morphology_notes',
    }
    assert roi_context_fields.isdisjoint(first.columns)


def test_scene_catalog_collapses_roi_rows_and_attaches_sector_coverage():
    scenes = pd.DataFrame([
        pilot_scene_row('A', 'HOL_ROI_02'),
        pilot_scene_row('A', 'HOL_ROI_01'),
        pilot_scene_row('B', 'HOL_ROI_01'),
    ])
    sectors = pd.DataFrame([
        {
            'pilot_sector_id': 'CORE',
            'role': 'core_candidate',
            'intersecting_roi_ids': 'HOL_ROI_01|HOL_ROI_02',
        },
        {
            'pilot_sector_id': 'BACKUP',
            'role': 'backup_candidate',
            'intersecting_roi_ids': 'HOL_ROI_02',
        },
    ])

    catalog = pilot.collapse_scene_coverage(scenes)
    covered = pilot.add_sector_coverage(catalog, sectors)
    scene_a = covered.set_index('source_scene_id').loc['A']
    scene_b = covered.set_index('source_scene_id').loc['B']

    assert len(catalog) == 2
    assert scene_a.covered_roi_ids == 'HOL_ROI_01|HOL_ROI_02'
    assert scene_a.covered_roi_count == 2
    assert scene_a.covered_sector_ids == 'CORE|BACKUP'
    assert bool(scene_a.covers_all_required_sectors) is True
    assert bool(scene_b.covers_all_required_sectors) is False


def test_scene_catalog_rejects_inconsistent_metadata_across_rois():
    scenes = pd.DataFrame([
        pilot_scene_row('A', 'HOL_ROI_01', sensor='L8'),
        pilot_scene_row('A', 'HOL_ROI_02', sensor='L9'),
    ])

    with pytest.raises(ValueError, match='inconsistent metadata'):
        pilot.collapse_scene_coverage(scenes)
