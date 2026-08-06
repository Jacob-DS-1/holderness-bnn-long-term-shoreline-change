"""Checks for the small set of canonical project settings."""

import pytest

from holderness import config


def test_primary_and_validation_imagery_are_separate():
    assert config.LANDSAT_SENSORS == ('L5', 'L7', 'L8', 'L9')
    assert config.SENTINEL_SENSORS == ('S2',)
    assert config.LANDSAT_DATES == ('1990-01-01', '2024-12-31')
    assert config.SENTINEL_DATES == ('2015-01-01', '2024-12-31')
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
    assert config.PILOT_STATUS == 'not_started'
    assert config.PILOT_RULES_FROZEN is False
    assert config.SELECTED_CLASSIFIER is None
    assert config.SELECTED_LOW_WATER_FILTER is None
    assert config.TARGET_ELEVATION_ODN_M is None
    assert config.CLASSIFIER_CANDIDATES == ('default', 'dark')


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
