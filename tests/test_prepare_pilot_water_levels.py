"""Focused checks for the pilot water-level evidence builder."""

from datetime import datetime, timezone
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / 'scripts/05-prepare-pilot-water-levels.py'


def load_script():
    spec = importlib.util.spec_from_file_location(
        'prepare_pilot_water_levels', SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_station_grid_digest_is_exact_and_value_sensitive():
    script = load_script()
    grid = (
        np.array([1273, 1275, 1277]),
        np.array([-0.198, -0.125, 0.007]),
        np.array([54.031, 53.884, 53.752]),
    )

    digest = script.station_grid_sha256(grid)

    assert script.station_grid_sha256(grid) == digest
    changed = tuple(values.copy() for values in grid)
    changed[1][1] += 1e-12
    assert script.station_grid_sha256(changed) != digest


def test_station_grid_comparison_checks_ids_and_coordinates():
    script = load_script()
    expected = (
        np.array([1273, 1275]),
        np.array([-0.198, -0.125]),
        np.array([54.031, 53.884]),
    )

    script.require_same_station_grid(expected, expected, 'matching file')
    changed = tuple(values.copy() for values in expected)
    changed[2][0] += 0.001

    with pytest.raises(ValueError, match='latitudes'):
        script.require_same_station_grid(changed, expected, 'changed file')


def synthetic_annual_msl():
    records = []
    for station_id, sector_id, offset in (
        (1273, 'BARMSTON', 0.000),
        (1275, 'CLIFF', 0.010),
        (1277, 'WITHERNSEA', 0.010),
    ):
        values = {
            year: offset + 0.003 * (year - 1990)
            for year in range(1990, 2025)
        }
        reference_offset = np.mean([
            values[year] for year in range(1991, 2021)
        ])
        for year, value in values.items():
            records.append({
                'gtsm_station_id': station_id,
                'pilot_sector_id': sector_id,
                'year': year,
                'experiment': 'historical' if year <= 2014 else 'future',
                'gtsm_msl_native_m': value,
                'gtsm_msl_reference_offset_m': reference_offset,
                'gtsm_msl_anomaly_m': value - reference_offset,
            })
    return pd.DataFrame(records)


def test_msl_merge_audit_records_unsmoothed_boundary_and_zero_reference():
    script = load_script()
    grid = (
        np.array([1273, 1275, 1277]),
        np.array([-0.198, -0.125, 0.007]),
        np.array([54.031, 53.884, 53.752]),
    )

    audit = script.msl_merge_audit(synthetic_annual_msl(), grid)

    assert audit['status'] == (
        'complete_structural_and_descriptive_checks_no_overlap_test'
    )
    assert audit['human_review_required'] is True
    assert audit['boundary_treatment'] == 'preserved without smoothing or offset'
    assert audit['annual_row_count'] == 105
    assert audit['station_count'] == 3
    assert len(audit['full_station_grid_sha256']) == 64
    assert [row['seam_increment_2014_2015_m'] for row in audit['stations']] == (
        pytest.approx([0.003, 0.003, 0.003])
    )
    assert [row['reference_mean_residual_m'] for row in audit['stations']] == (
        pytest.approx([0.0, 0.0, 0.0], abs=1e-12)
    )


def test_msl_merge_audit_does_not_call_a_large_seam_an_automatic_pass():
    script = load_script()
    annual = synthetic_annual_msl()
    annual.loc[annual['year'].ge(2015), 'gtsm_msl_native_m'] += 1.0
    annual.loc[annual['year'].ge(2015), 'gtsm_msl_anomaly_m'] += 1.0
    grid = (
        np.array([1273, 1275, 1277]),
        np.array([-0.198, -0.125, 0.007]),
        np.array([54.031, 53.884, 53.752]),
    )

    audit = script.msl_merge_audit(annual, grid)

    assert 'pass' not in audit['status']
    assert audit['human_review_required'] is True
    assert audit['seam_diagnostics'][
        'maximum_absolute_2014_2015_increment_m'
    ] == pytest.approx(1.003)


def test_archive_checksum_rejects_tampering(tmp_path):
    script = load_script()
    archive = tmp_path / 'archive.zip'
    archive.write_bytes(b'complete archive')
    expected = script.gtsm.sha256_file(archive)

    assert script.require_archive_checksum(archive, expected) == expected
    archive.write_bytes(b'tampered archive')

    with pytest.raises(ValueError, match='checksum changed'):
        script.require_archive_checksum(archive, expected)


def test_core_sector_rows_reject_duplicate_approved_id():
    script = load_script()
    sector_ids = list(script.config.PILOT_GTSM_STATION_IDS)
    sectors = pd.DataFrame({
        'pilot_sector_id': sector_ids + [sector_ids[0]],
        'role': ['core_candidate'] * 4,
        'chainage_start_m': [0, 100, 200, 300],
        'chainage_end_m': [100, 200, 300, 400],
    })

    with pytest.raises(ValueError, match='must be unique'):
        script.require_core_sector_rows(sectors)


def test_surge_statistics_use_only_valid_rows_and_absolute_percentiles():
    script = load_script()
    samples = pd.DataFrame({
        'pilot_sector_id': ['A', 'A', 'B', 'B', 'B'],
        'gtsm_sample_status': ['valid', 'valid', 'valid', 'valid', 'excluded'],
        'gtsm_surge_m': [-0.2, 0.0, 0.1, 0.3, 99.0],
    })

    statistics = script.surge_statistics(samples)
    overall = statistics['all_candidate_scene_sector_rows']

    assert overall['row_count'] == 4
    assert overall['median_surge_m'] == pytest.approx(0.05)
    assert overall['absolute_median_m'] == pytest.approx(0.15)
    assert overall['absolute_p90_m'] == pytest.approx(0.27)
    assert overall['proportion_absolute_gt_0_1_m'] == pytest.approx(0.5)
    assert statistics['by_sector']['A']['row_count'] == 2
    assert statistics['by_sector']['B']['row_count'] == 2


def test_netcdf_time_is_written_as_explicit_utc():
    script = load_script()

    assert script.format_netcdf_time(datetime(2024, 6, 1, 12, 30)) == (
        '2024-06-01T12:30:00Z'
    )
    assert script.format_netcdf_time(
        datetime(2024, 6, 1, 13, 30, tzinfo=timezone.utc)
    ) == '2024-06-01T13:30:00Z'
