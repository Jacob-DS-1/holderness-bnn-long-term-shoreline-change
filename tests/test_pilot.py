"""Focused checks for pilot water levels and shortlist validation."""

import numpy as np
import pandas as pd
import pytest

from holderness import pilot


def valid_shortlist():
    return pd.DataFrame(
        {
            'source_scene_id': ['SCENE_L5', 'SCENE_L7', 'SCENE_L8', 'SCENE_L9'],
            'sensor': ['L5', 'L7', 'L8', 'L9'],
            'primary_geometry_eligible': [True, True, True, True],
            'covered_sector_ids': [
                'CORE_A|CORE_B',
                'CORE_A|CORE_B',
                'CORE_A|CORE_B',
                'CORE_A|CORE_B',
            ],
        }
    )


def required_mission_counts():
    return {'L5': 1, 'L7': 1, 'L8': 1, 'L9': 1}


def test_fes_astronomical_tide_adds_ocean_and_loading_components():
    water_levels = pd.DataFrame(
        {
            'fes_ocean_tide_m': [1.20, -0.40],
            'fes_loading_tide_m': [0.10, 0.05],
        }
    )

    result = pilot.add_fes_astronomical_tide(water_levels)

    assert result['fes_astronomical_tide_m'].to_list() == pytest.approx(
        [1.30, -0.35]
    )
    assert 'fes_astronomical_tide_m' not in water_levels.columns


@pytest.mark.parametrize('invalid_value', [None, np.nan, np.inf, -np.inf, 'bad'])
def test_fes_astronomical_tide_rejects_invalid_components(invalid_value):
    water_levels = pd.DataFrame(
        {
            'fes_ocean_tide_m': [0.0],
            'fes_loading_tide_m': [invalid_value],
        }
    )

    with pytest.raises(ValueError, match='finite numeric values'):
        pilot.add_fes_astronomical_tide(water_levels)


def test_pilot_still_water_anomaly_sums_three_components():
    water_levels = pd.DataFrame(
        {
            'gtsm_msl_anomaly_m': [0.04, -0.03],
            'fes_astronomical_tide_m': [-0.12, 0.18],
            'gtsm_surge_m': [0.03, -0.02],
        }
    )

    result = pilot.add_pilot_still_water_anomaly(water_levels)

    assert result['pilot_still_water_anomaly_m'].to_list() == pytest.approx(
        [-0.05, 0.13]
    )
    assert 'pilot_still_water_anomaly_m' not in water_levels.columns


@pytest.mark.parametrize('invalid_value', [None, np.nan, np.inf, -np.inf, 'bad'])
def test_pilot_still_water_anomaly_rejects_invalid_components(invalid_value):
    water_levels = pd.DataFrame(
        {
            'gtsm_msl_anomaly_m': [invalid_value],
            'fes_astronomical_tide_m': [0.0],
            'gtsm_surge_m': [0.0],
        }
    )

    with pytest.raises(ValueError, match='finite numeric values'):
        pilot.add_pilot_still_water_anomaly(water_levels)


def test_p023_water_bands_use_exact_non_overlapping_boundaries():
    water_levels = pd.DataFrame(
        {
            'pilot_still_water_anomaly_m': [-0.001, 0.0, 0.199999, 0.2],
        }
    )

    result = pilot.add_p023_water_bands(water_levels)

    assert result['water_level_band'].to_list() == [
        'below_local_amsl',
        'local_amsl_to_below_plus_0_2_m',
        'local_amsl_to_below_plus_0_2_m',
        'at_or_above_local_amsl_plus_0_2_m',
    ]
    assert result['passes_local_amsl_filter'].to_list() == [
        False, True, True, True,
    ]
    assert result['passes_local_amsl_plus_0_2_m_filter'].to_list() == [
        False, False, False, True,
    ]


def test_p023_water_bands_reject_non_finite_anomaly():
    water_levels = pd.DataFrame(
        {'pilot_still_water_anomaly_m': [np.nan]}
    )

    with pytest.raises(ValueError, match='finite numeric values'):
        pilot.add_p023_water_bands(water_levels)


def test_metadata_shortlist_validation_returns_summary():
    summary = pilot.validate_metadata_shortlist(
        valid_shortlist(),
        required_core_sector_ids={'CORE_A', 'CORE_B'},
        target_count=4,
        required_mission_counts=required_mission_counts(),
    )

    assert summary == {
        'scene_count': 4,
        'mission_counts': {'L5': 1, 'L7': 1, 'L8': 1, 'L9': 1},
        'required_core_sector_ids': ['CORE_A', 'CORE_B'],
    }


def test_metadata_shortlist_rejects_duplicate_scene_ids():
    shortlist = valid_shortlist()
    shortlist.loc[1, 'source_scene_id'] = 'SCENE_L5'

    with pytest.raises(ValueError, match='duplicate source_scene_id'):
        pilot.validate_metadata_shortlist(
            shortlist, {'CORE_A', 'CORE_B'}, 4, required_mission_counts()
        )


@pytest.mark.parametrize('eligibility', [False, None])
def test_metadata_shortlist_rejects_ineligible_scene(eligibility):
    shortlist = valid_shortlist()
    shortlist['primary_geometry_eligible'] = shortlist[
        'primary_geometry_eligible'
    ].astype('boolean')
    shortlist.loc[0, 'primary_geometry_eligible'] = eligibility

    with pytest.raises(ValueError, match='geometry eligible'):
        pilot.validate_metadata_shortlist(
            shortlist, {'CORE_A', 'CORE_B'}, 4, required_mission_counts()
        )


def test_metadata_shortlist_rejects_missing_core_sector_coverage():
    shortlist = valid_shortlist()
    shortlist.loc[2, 'covered_sector_ids'] = 'CORE_A'

    with pytest.raises(ValueError, match='every required core sector'):
        pilot.validate_metadata_shortlist(
            shortlist, {'CORE_A', 'CORE_B'}, 4, required_mission_counts()
        )


def test_metadata_shortlist_rejects_wrong_target_or_mission_counts():
    shortlist = valid_shortlist()

    with pytest.raises(ValueError, match='expected 5 shortlist rows'):
        pilot.validate_metadata_shortlist(
            shortlist,
            {'CORE_A', 'CORE_B'},
            5,
            {'L5': 2, 'L7': 1, 'L8': 1, 'L9': 1},
        )

    shortlist.loc[3, 'sensor'] = 'L8'
    with pytest.raises(ValueError, match='mission counts'):
        pilot.validate_metadata_shortlist(
            shortlist, {'CORE_A', 'CORE_B'}, 4, required_mission_counts()
        )
