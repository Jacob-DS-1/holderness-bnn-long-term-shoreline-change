"""Focused checks for the frozen GTSM pilot retrieval."""

import importlib.util
from pathlib import Path
import sys
from zipfile import ZIP_STORED, ZipFile

import numpy as np
import pandas as pd
import pytest

from holderness import gtsm


REPO_ROOT = Path(__file__).resolve().parents[1]
ANNUAL_SCRIPT_PATH = REPO_ROOT / 'scripts/download-gtsm-annual-msl.py'
HDF_PAYLOAD = b'\x89HDF\r\n\x1a\nnetcdf-placeholder'


def load_annual_script():
    spec = importlib.util.spec_from_file_location(
        'download_gtsm_annual_msl', ANNUAL_SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_annual_archive(path, experiment, payload=HDF_PAYLOAD):
    with ZipFile(path, 'w', compression=ZIP_STORED) as archive:
        for member in gtsm.expected_annual_msl_members(experiment):
            archive.writestr(member, payload + member.encode('ascii'))


def test_select_water_level_pool_uses_only_predeclared_eligible_scenes():
    catalog = pd.DataFrame({
        'source_scene_id': ['KEEP', 'NOT_SEEDED', 'BAD_GEOMETRY', 'BAD_COVERAGE'],
        'acquisition_time_utc': [
            '2024-06-20T10:56:59Z',
            '2024-06-21T10:56:59Z',
            '2024-06-22T10:56:59Z',
            '2024-06-23T10:56:59Z',
        ],
        'sensor': ['L8', 'L8', 'L8', 'L8'],
        'primary_geometry_eligible': [True, True, False, True],
        'covers_all_required_sectors': [True, True, True, False],
    })

    result = gtsm.select_water_level_evaluation_pool(
        catalog, {'KEEP', 'BAD_GEOMETRY', 'BAD_COVERAGE'}
    )

    assert result['source_scene_id'].to_list() == ['KEEP']


def test_retrieval_months_are_sorted_and_keep_scene_provenance():
    pool = pd.DataFrame({
        'source_scene_id': ['SCENE_B', 'SCENE_A', 'SCENE_C'],
        'acquisition_time_utc': [
            '2024-06-20T10:56:59.429Z',
            '2024-06-04T10:56:59Z',
            '1990-01-01T10:56:59Z',
        ],
    })

    result = gtsm.retrieval_months(pool)

    assert result[['year', 'month', 'scene_count']].to_dict('records') == [
        {'year': 1990, 'month': 1, 'scene_count': 1},
        {'year': 2024, 'month': 6, 'scene_count': 2},
    ]
    assert result.iloc[1].source_scene_ids == 'SCENE_A|SCENE_B'


def test_identity_hash_is_order_invariant_and_detects_utc_change():
    pool = pd.DataFrame({
        'source_scene_id': ['B', 'A'],
        'acquisition_time_utc': [
            '2024-02-01T00:00:00Z', '2024-01-01T00:00:00Z',
        ],
    })
    original = gtsm.evaluation_pool_sha256(pool)

    assert gtsm.evaluation_pool_sha256(pool.iloc[::-1]) == original
    changed = pool.copy()
    changed.loc[1, 'acquisition_time_utc'] = '2024-01-01T00:00:01Z'
    assert gtsm.evaluation_pool_sha256(changed) != original


def test_retrieval_request_is_fixed_to_approved_product():
    assert gtsm.retrieval_request(2024, 6) == {
        'variable': ['storm_surge_residual'],
        'experiment': 'reanalysis',
        'temporal_aggregation': ['10_min'],
        'year': ['2024'],
        'month': ['06'],
        'version': ['v3'],
    }


@pytest.mark.parametrize(
    ('year', 'month'),
    [
        (1949, 1), (2025, 1), (2024, 0), (2024, 13),
        (2024, True), (2024, 1.5),
    ],
)
def test_retrieval_request_rejects_out_of_range_dates(year, month):
    with pytest.raises(ValueError):
        gtsm.retrieval_request(year, month)


def test_annual_msl_plan_freezes_two_versioned_requests_and_all_study_years():
    plan = gtsm.annual_msl_retrieval_plan()

    assert [item['experiment'] for item in plan] == ['historical', 'future']
    assert [(item['start_year'], item['end_year']) for item in plan] == [
        (1990, 2014), (2015, 2024),
    ]
    assert sum(item['year_count'] for item in plan) == 35
    years = [
        int(year)
        for item in plan
        for year in item['request']['year']
    ]
    assert years == list(range(1990, 2025))

    for item in plan:
        request = item['request']
        assert request['variable'] == ['mean_sea_level']
        assert request['experiment'] == item['experiment']
        assert request['temporal_aggregation'] == ['annual']
        assert request['version'] == ['v1']
        assert 'model' not in request
        assert 'month' not in request


def test_annual_msl_filenames_and_observed_members_are_exact():
    assert gtsm.annual_msl_archive_filename('historical') == (
        'gtsm-v3-historical-annual-msl-v1-1990-2014.zip'
    )
    assert gtsm.annual_msl_archive_filename('future') == (
        'gtsm-v3-future-annual-msl-v1-2015-2024.zip'
    )
    historical = gtsm.expected_annual_msl_members('historical')
    future = gtsm.expected_annual_msl_members('future')
    assert len(historical) == 25
    assert historical[0] == 'historical_msl_1990_01_v1.nc'
    assert historical[-1] == 'historical_msl_2014_01_v1.nc'
    assert len(future) == 10
    assert future[0] == 'future_msl_2015_01_v1.nc'
    assert future[-1] == 'future_msl_2024_01_v1.nc'


def test_annual_msl_plan_digest_is_deterministic_and_value_sensitive():
    plan = gtsm.annual_msl_retrieval_plan()
    digest = gtsm.annual_msl_plan_sha256(plan)

    assert gtsm.annual_msl_plan_sha256() == digest
    changed = gtsm.annual_msl_retrieval_plan()
    changed[1]['request']['year'][-1] = '2025'
    assert gtsm.annual_msl_plan_sha256(changed) != digest


def test_annual_msl_rejects_unapproved_experiment():
    with pytest.raises(ValueError, match='historical.*future'):
        gtsm.annual_msl_request('reanalysis')


def test_station_positions_use_coordinate_values_not_array_positions():
    station_ids = np.array([1277, 42, 1273, 1275])

    assert gtsm.station_positions(station_ids, [1275, 1277, 1273]) == [
        3, 0, 2,
    ]


def test_station_positions_reject_missing_or_duplicate_required_station():
    with pytest.raises(ValueError, match='expected one GTSM station 1275'):
        gtsm.station_positions(np.array([1273, 1277]), [1275])
    with pytest.raises(ValueError, match='required.*unique'):
        gtsm.station_positions(np.array([1273, 1277]), [1273, 1273])


def test_strict_linear_bracket_preserves_subminute_scene_time():
    lower, upper, weight = gtsm.strict_linear_bracket(
        [0.0, 600.0, 1200.0], 749.831
    )

    assert (lower, upper) == (1, 2)
    assert weight == pytest.approx(0.24971833333333335)


@pytest.mark.parametrize('target', [0.0, 600.0, 1200.0, -1.0, 1201.0])
def test_strict_linear_bracket_requires_two_distinct_surrounding_values(target):
    with pytest.raises(ValueError, match='strict|outside'):
        gtsm.strict_linear_bracket([0.0, 600.0, 1200.0], target)


def test_interpolate_finite_bracket_applies_one_weight_to_all_stations():
    result = gtsm.interpolate_finite_bracket(
        np.array([0.0, 1.0, -1.0]),
        np.array([1.0, 3.0, 1.0]),
        0.25,
    )

    assert result == pytest.approx([0.25, 1.5, -0.5])


@pytest.mark.parametrize(
    ('lower', 'upper'),
    [([np.nan, 0.0], [1.0, 1.0]), ([0.0, 0.0], [1.0, np.nan])],
)
def test_interpolate_finite_bracket_returns_none_for_any_missing_endpoint(
        lower, upper):
    assert gtsm.interpolate_finite_bracket(lower, upper, 0.5) is None


def test_recenter_annual_msl_preserves_native_values_and_zeroes_reference():
    rows = []
    for station_id, adjustment in ((1273, 0.0), (1275, 0.01)):
        for year in range(1991, 2022):
            rows.append({
                'gtsm_station_id': station_id,
                'year': year,
                'gtsm_msl_native_m': adjustment + 0.001 * (year - 1991),
            })
    source = pd.DataFrame(rows)

    result = gtsm.recenter_annual_msl(source)

    assert result['gtsm_msl_native_m'].equals(source['gtsm_msl_native_m'])
    reference = result.loc[result['year'].between(1991, 2020)]
    assert reference.groupby('gtsm_station_id')[
        'gtsm_msl_anomaly_m'
    ].mean().to_numpy() == pytest.approx([0.0, 0.0], abs=1e-12)
    offsets = result.groupby('gtsm_station_id')[
        'gtsm_msl_reference_offset_m'
    ].first()
    assert offsets.loc[1275] - offsets.loc[1273] == pytest.approx(0.01)


def test_recenter_annual_msl_requires_complete_reference_period():
    source = pd.DataFrame({
        'gtsm_station_id': [1273] * 29,
        'year': list(range(1991, 2020)),
        'gtsm_msl_native_m': np.arange(29, dtype=float),
    })

    with pytest.raises(ValueError, match='complete reference period'):
        gtsm.recenter_annual_msl(source)


def test_validate_archive_checks_member_name_and_crc(tmp_path):
    path = tmp_path / gtsm.archive_filename(2024, 6)
    member = gtsm.expected_member_name(2024, 6)
    with ZipFile(path, 'w') as archive:
        archive.writestr(member, b'\x89HDF\r\n\x1a\nnetcdf-placeholder')

    result = gtsm.validate_archive(path, 2024, 6)

    assert result['archive_filename'] == path.name
    assert result['netcdf_member'] == member
    assert result['netcdf_bytes'] == len(
        b'\x89HDF\r\n\x1a\nnetcdf-placeholder'
    )


def test_validate_archive_rejects_unexpected_member(tmp_path):
    path = tmp_path / 'wrong.zip'
    with ZipFile(path, 'w') as archive:
        archive.writestr('wrong.nc', b'netcdf-placeholder')

    with pytest.raises(ValueError, match='members do not match'):
        gtsm.validate_archive(path, 2024, 6)


def test_validate_archive_rejects_non_netcdf_member(tmp_path):
    path = tmp_path / gtsm.archive_filename(2024, 6)
    with ZipFile(path, 'w') as archive:
        archive.writestr(
            gtsm.expected_member_name(2024, 6), b'not-netcdf'
        )

    with pytest.raises(ValueError, match='not a NetCDF-4'):
        gtsm.validate_archive(path, 2024, 6)


def test_validate_annual_msl_archive_checks_exact_members_hdf_and_crc(tmp_path):
    path = tmp_path / gtsm.annual_msl_archive_filename('future')
    write_annual_archive(path, 'future')

    result = gtsm.validate_annual_msl_archive(path, 'future')

    assert result['archive_filename'] == path.name
    assert result['netcdf_member_count'] == 10
    assert result['netcdf_members'].split('|') == list(
        gtsm.expected_annual_msl_members('future')
    )
    assert result['netcdf_bytes'] > 0


def test_validate_annual_msl_archive_rejects_missing_or_extra_member(tmp_path):
    path = tmp_path / 'annual.zip'
    members = gtsm.expected_annual_msl_members('future')
    with ZipFile(path, 'w') as archive:
        for member in members[:-1]:
            archive.writestr(member, HDF_PAYLOAD)

    with pytest.raises(ValueError, match='fixed future annual-MSL member plan'):
        gtsm.validate_annual_msl_archive(path, 'future')

    with ZipFile(path, 'w') as archive:
        for member in members:
            archive.writestr(member, HDF_PAYLOAD)
        archive.writestr('unexpected.nc', HDF_PAYLOAD)

    with pytest.raises(ValueError, match='fixed future annual-MSL member plan'):
        gtsm.validate_annual_msl_archive(path, 'future')


def test_validate_annual_msl_archive_rejects_non_hdf_member(tmp_path):
    path = tmp_path / 'annual.zip'
    members = gtsm.expected_annual_msl_members('future')
    with ZipFile(path, 'w') as archive:
        for position, member in enumerate(members):
            payload = b'not-netcdf' if position == 4 else HDF_PAYLOAD
            archive.writestr(member, payload)

    with pytest.raises(ValueError, match='not a NetCDF-4/HDF5'):
        gtsm.validate_annual_msl_archive(path, 'future')


def test_validate_annual_msl_archive_rejects_crc_corruption(tmp_path):
    path = tmp_path / 'annual.zip'
    write_annual_archive(path, 'future')
    content = bytearray(path.read_bytes())
    marker = HDF_PAYLOAD + gtsm.expected_annual_msl_members('future')[0].encode(
        'ascii'
    )
    position = content.index(marker)
    content[position + len(HDF_PAYLOAD)] ^= 1
    path.write_bytes(content)

    with pytest.raises(ValueError, match='CRC|valid ZIP'):
        gtsm.validate_annual_msl_archive(path, 'future')


def test_publish_without_overwrite_promotes_partial_exclusively(tmp_path):
    partial = tmp_path / 'archive.zip.partial'
    target = tmp_path / 'archive.zip'
    partial.write_bytes(b'validated archive')

    gtsm.publish_without_overwrite(partial, target)

    assert target.read_bytes() == b'validated archive'
    assert not partial.exists()


def test_publish_without_overwrite_preserves_existing_target(tmp_path):
    partial = tmp_path / 'archive.zip.partial'
    target = tmp_path / 'archive.zip'
    partial.write_bytes(b'new')
    target.write_bytes(b'existing')

    with pytest.raises(FileExistsError, match='refusing to overwrite'):
        gtsm.publish_without_overwrite(partial, target)

    assert target.read_bytes() == b'existing'
    assert partial.read_bytes() == b'new'


def test_external_output_guard_rejects_repo_and_same_device(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    child = repo / 'data'
    child.mkdir()
    peer = tmp_path / 'peer'
    peer.mkdir()

    with pytest.raises(ValueError, match='outside the repository'):
        gtsm.require_external_output_directory(child, repo)
    with pytest.raises(ValueError, match='different mounted device'):
        gtsm.require_external_output_directory(peer, repo)


def test_annual_msl_dry_run_does_not_create_client_or_write(
        tmp_path, monkeypatch):
    script = load_annual_script()
    output_dir = tmp_path / 'external'
    output_dir.mkdir()
    manifest_dir = tmp_path / 'manifests'
    monkeypatch.setattr(
        gtsm, 'require_external_output_directory',
        lambda output_dir, repo_root: Path(output_dir).resolve(),
    )
    monkeypatch.setattr(
        script, 'cds_client',
        lambda: pytest.fail('dry run must not create a CDS client'),
    )
    monkeypatch.setattr(sys, 'argv', [
        str(ANNUAL_SCRIPT_PATH),
        '--output-dir', str(output_dir),
        '--manifest-dir', str(manifest_dir),
        '--dry-run',
    ])

    script.main()

    assert not manifest_dir.exists()
    assert list(output_dir.iterdir()) == []


def test_annual_msl_partial_is_promotable_only_after_full_validation(tmp_path):
    script = load_annual_script()
    target = tmp_path / gtsm.annual_msl_archive_filename('future')
    partial = target.with_suffix(target.suffix + '.partial')
    write_annual_archive(partial, 'future')

    assert script.inspect_archive_state(
        target, partial, 'future'
    ) == 'promote_valid_partial'

    partial.write_bytes(b'invalid partial')
    with pytest.raises(ValueError, match='valid ZIP'):
        script.inspect_archive_state(target, partial, 'future')


def test_annual_msl_lock_is_exclusive_and_removed(tmp_path):
    script = load_annual_script()
    lock_path = tmp_path / script.LOCK_FILENAME

    with script.download_lock(tmp_path):
        assert lock_path.is_file()
        with pytest.raises(RuntimeError, match='lock already exists'):
            with script.download_lock(tmp_path):
                pass

    assert not lock_path.exists()


def test_annual_manifest_rejects_changed_archive_identity(tmp_path):
    script = load_annual_script()
    plan = gtsm.annual_msl_retrieval_plan()
    path = tmp_path / script.DOWNLOAD_MANIFEST_FILENAME
    pd.DataFrame([{
        'experiment': 'historical',
        'start_year': 1990,
        'end_year': 2014,
        'archive_filename': 'wrong.zip',
        'sha256': '0' * 64,
    }]).to_csv(path, index=False)

    with pytest.raises(ValueError, match='identity changed'):
        script.load_prior_records(path, plan)
