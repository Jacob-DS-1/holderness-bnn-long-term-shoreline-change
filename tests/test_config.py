"""Checks for the small set of canonical project settings."""

import pytest

from holderness import config


def test_primary_and_validation_imagery_are_separate():
    assert config.LANDSAT_SENSORS == ('L5', 'L7', 'L8', 'L9')
    assert config.SENTINEL_SENSORS == ('S2',)
    # Earth Engine end dates are exclusive, so 2025-01-01 includes all of
    # 2024 without adding any 2025 acquisitions.
    assert config.LANDSAT_DATES == ('1990-01-01', '2025-01-01')
    assert config.SENTINEL_DATES == ('2015-01-01', '2025-01-01')
    assert set(config.LANDSAT_SENSORS).isdisjoint(config.SENTINEL_SENSORS)
    assert set(config.LANDSAT_GEE_COLLECTIONS) == set(config.LANDSAT_SENSORS)
    assert set(config.SENTINEL_GEE_COLLECTIONS) == set(config.SENTINEL_SENSORS)


def test_initial_geometry_settings_are_consistent():
    assert config.EPSG == 27700
    assert config.MASTER_TRANSECT_SPACING_M == 2 * config.COASTSAT_ALONG_DIST_M
    assert config.INITIAL_TRANSECT_LANDWARD_M == (
        config.INITIAL_MAX_DIST_REF_M + config.TRANSECT_ENDPOINT_MARGIN_M
    )
    assert config.INITIAL_TRANSECT_SEAWARD_M == (
        config.INITIAL_MAX_DIST_REF_M + config.TRANSECT_ENDPOINT_MARGIN_M
    )
    assert all(
        spacing % config.MASTER_TRANSECT_SPACING_M == 0
        for spacing in config.TRANSECT_SUBSET_SPACINGS_M
    )


def test_unresolved_settings_are_explicit():
    assert config.PILOT_STATUS == 'retrieval_candidates_selected'
    assert config.PILOT_RULES_FROZEN is False
    assert config.SELECTED_CLASSIFIER is None
    assert config.SELECTED_LOW_WATER_FILTER is None
    assert config.TARGET_ELEVATION_ODN_M is None
    assert config.CLASSIFIER_CANDIDATES == ('default', 'dark')


def test_approved_pilot_retrieval_design_is_frozen():
    assert config.PILOT_RETRIEVAL_DESIGN_ID == 1
    assert len(config.PILOT_RETRIEVAL_SCENE_IDS) == 14
    assert len(set(config.PILOT_RETRIEVAL_SCENE_IDS)) == 14
    assert config.PILOT_RETRIEVAL_MANIFEST.name == (
        'pilot-retrieval-manifest.json'
    )

    collection_codes = {
        'L5': '/LT05/',
        'L7': '/LE07/',
        'L8': '/LC08/',
        'L9': '/LC09/',
    }
    mission_counts = {
        mission: sum(
            collection_codes[mission] in scene_id
            for scene_id in config.PILOT_RETRIEVAL_SCENE_IDS
        )
        for mission in config.LANDSAT_SENSORS
    }
    assert mission_counts == {'L5': 3, 'L7': 4, 'L8': 4, 'L9': 3}


def test_pilot_water_level_nodes_are_explicitly_provisional():
    assert config.PILOT_FES_OFFSHORE_DISTANCE_M == 3_000
    assert config.PILOT_GTSM_STATION_IDS == {
        'HOL_PILOT_WITHERNSEA_TRANSITION': 1277,
        'HOL_PILOT_CLIFF_COMPARISON_CANDIDATE': 1275,
        'HOL_PILOT_BARMSTON_OUTLET': 1273,
    }
    assert len(set(config.PILOT_GTSM_STATION_IDS.values())) == 3
    assert 'pilot_only' in config.PILOT_WATER_LEVEL_GEOMETRY_STATUS


def test_gee_project_prefers_command_line_value(monkeypatch):
    monkeypatch.setenv(config.GEE_PROJECT_ENV, 'environment-project')
    assert config.get_gee_project('command-line-project') == 'command-line-project'


def test_gee_project_reads_environment(monkeypatch):
    monkeypatch.setenv(config.GEE_PROJECT_ENV, 'environment-project')
    assert config.get_gee_project() == 'environment-project'


def test_gee_project_is_required(monkeypatch):
    monkeypatch.delenv(config.GEE_PROJECT_ENV, raising=False)
    with pytest.raises(RuntimeError, match=config.GEE_PROJECT_ENV):
        config.get_gee_project()
