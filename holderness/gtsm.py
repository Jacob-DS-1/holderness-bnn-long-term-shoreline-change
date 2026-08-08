"""Helpers for the frozen pilot GTSM v3 retrieval."""

import hashlib
import json
import os
from operator import index
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd


DATASET_ID = 'sis-water-level-change-timeseries-cmip6'
EXPERIMENT = 'reanalysis'
VARIABLE = 'storm_surge_residual'
TEMPORAL_AGGREGATION = '10_min'
VERSION = 'v3'

# The hydrodynamic model is GTSM v3.0, while the CDS historical and future
# experiment files that carry annual mean sea level are catalogue version v1.
# Keep these names separate from the reanalysis-surge constants above.
ANNUAL_MSL_MODEL_VERSION = 'GTSM v3.0'
ANNUAL_MSL_CDS_VERSION = 'v1'
ANNUAL_MSL_VARIABLE = 'mean_sea_level'
ANNUAL_MSL_TEMPORAL_AGGREGATION = 'annual'
ANNUAL_MSL_SOURCE_REFERENCE_PERIOD = '1986-2005'
ANNUAL_MSL_TARGET_REFERENCE_PERIOD = '1991-2020'
ANNUAL_MSL_RANGES = (
    ('historical', 1990, 2014),
    ('future', 2015, 2024),
)


def select_water_level_evaluation_pool(scene_catalog, candidate_scene_ids):
    """Select the pre-water-level candidate intersection used by the pilot."""
    required = {
        'source_scene_id',
        'primary_geometry_eligible',
        'covers_all_required_sectors',
    }
    missing = required.difference(scene_catalog.columns)
    if missing:
        raise ValueError(f'missing scene-catalog columns: {sorted(missing)}')
    if scene_catalog['source_scene_id'].duplicated().any():
        raise ValueError('scene_catalog must contain one row per source scene')

    candidate_scene_ids = {
        str(value).strip() for value in candidate_scene_ids
        if str(value).strip()
    }
    if not candidate_scene_ids:
        raise ValueError('candidate_scene_ids must not be empty')

    eligible = (
        scene_catalog['source_scene_id'].isin(candidate_scene_ids)
        & scene_catalog['primary_geometry_eligible'].eq(True)
        & scene_catalog['covers_all_required_sectors'].eq(True)
    )
    result = scene_catalog.loc[eligible].copy()
    if result.empty:
        raise ValueError('water-level evaluation pool is empty')

    return result.sort_values(
        ['acquisition_time_utc', 'sensor', 'source_scene_id']
    ).reset_index(drop=True)


def retrieval_months(evaluation_pool):
    """Return one deterministic row per year-month in an evaluation pool."""
    required = {'source_scene_id', 'acquisition_time_utc'}
    missing = required.difference(evaluation_pool.columns)
    if missing:
        raise ValueError(f'missing evaluation-pool columns: {sorted(missing)}')
    if evaluation_pool['source_scene_id'].duplicated().any():
        raise ValueError('evaluation_pool must contain one row per source scene')

    times = pd.to_datetime(
        evaluation_pool['acquisition_time_utc'], format='mixed',
        utc=True, errors='coerce',
    )
    if times.isna().any():
        scene_ids = evaluation_pool.loc[
            times.isna(), 'source_scene_id'
        ].tolist()
        raise ValueError(f'invalid acquisition times for scenes: {scene_ids[:5]}')

    dated = evaluation_pool[['source_scene_id']].copy()
    dated['year'] = times.dt.year.astype(int)
    dated['month'] = times.dt.month.astype(int)
    result = (
        dated.groupby(['year', 'month'], sort=True)['source_scene_id']
        .agg(
            scene_count='size',
            source_scene_ids=lambda values: '|'.join(sorted(values)),
        )
        .reset_index()
    )
    return result


def evaluation_pool_sha256(evaluation_pool):
    """Hash sorted scene IDs and original UTC strings for pool identity."""
    required = {'source_scene_id', 'acquisition_time_utc'}
    missing = required.difference(evaluation_pool.columns)
    if missing:
        raise ValueError(f'missing evaluation-pool columns: {sorted(missing)}')
    ordered = evaluation_pool.sort_values('source_scene_id')
    payload = ''.join(
        f'{row.source_scene_id}\t{row.acquisition_time_utc}\n'
        for row in ordered.itertuples(index=False)
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def month_plan_sha256(months):
    """Hash the exact sorted month-to-scene retrieval plan."""
    required = {'year', 'month', 'scene_count', 'source_scene_ids'}
    missing = required.difference(months.columns)
    if missing:
        raise ValueError(f'missing month-plan columns: {sorted(missing)}')
    ordered = months.sort_values(['year', 'month'])
    payload = ''.join(
        f'{int(row.year):04d}-{int(row.month):02d}\t'
        f'{int(row.scene_count)}\t{row.source_scene_ids}\n'
        for row in ordered.itertuples(index=False)
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _annual_msl_range(experiment):
    """Return the fixed year range for one annual-MSL experiment."""
    matches = [
        (start_year, end_year)
        for name, start_year, end_year in ANNUAL_MSL_RANGES
        if name == experiment
    ]
    if len(matches) != 1:
        choices = [name for name, _, _ in ANNUAL_MSL_RANGES]
        raise ValueError(
            f'annual-MSL experiment must be one of {choices}: {experiment!r}'
        )
    return matches[0]


def annual_msl_request(experiment):
    """Build one of the two fixed CDS annual mean-sea-level requests."""
    start_year, end_year = _annual_msl_range(experiment)
    return {
        'variable': [ANNUAL_MSL_VARIABLE],
        'experiment': experiment,
        'temporal_aggregation': [ANNUAL_MSL_TEMPORAL_AGGREGATION],
        'year': [str(year) for year in range(start_year, end_year + 1)],
        'version': [ANNUAL_MSL_CDS_VERSION],
    }


def annual_msl_archive_filename(experiment):
    """Return the fixed local filename for one annual-MSL archive."""
    start_year, end_year = _annual_msl_range(experiment)
    return (
        f'gtsm-v3-{experiment}-annual-msl-v1-'
        f'{start_year:04d}-{end_year:04d}.zip'
    )


def expected_annual_msl_members(experiment):
    """Return the exact annual NetCDF members observed in the CDS ZIP."""
    start_year, end_year = _annual_msl_range(experiment)
    return tuple(
        f'{experiment}_msl_{year:04d}_01_v1.nc'
        for year in range(start_year, end_year + 1)
    )


def annual_msl_retrieval_plan():
    """Return the complete immutable-in-code two-archive retrieval plan."""
    plan = []
    for experiment, start_year, end_year in ANNUAL_MSL_RANGES:
        plan.append({
            'experiment': experiment,
            'start_year': start_year,
            'end_year': end_year,
            'year_count': end_year - start_year + 1,
            'archive_filename': annual_msl_archive_filename(experiment),
            'expected_members': list(
                expected_annual_msl_members(experiment)
            ),
            'request': annual_msl_request(experiment),
        })
    return plan


def annual_msl_plan_sha256(plan=None):
    """Hash the canonical JSON representation of the annual-MSL plan."""
    if plan is None:
        plan = annual_msl_retrieval_plan()
    payload = json.dumps(
        plan, sort_keys=True, separators=(',', ':'), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def station_positions(station_ids, required_station_ids):
    """Locate unique station IDs without assuming ID equals array position."""
    station_ids = np.asarray(station_ids)
    required_station_ids = tuple(required_station_ids)
    if station_ids.ndim != 1:
        raise ValueError('GTSM station IDs must be one-dimensional')
    if len(set(required_station_ids)) != len(required_station_ids):
        raise ValueError('required GTSM station IDs must be unique')

    positions = []
    for station_id in required_station_ids:
        matches = np.flatnonzero(station_ids == station_id)
        if len(matches) != 1:
            raise ValueError(
                f'expected one GTSM station {station_id}, found {len(matches)}'
            )
        positions.append(int(matches[0]))
    return positions


def strict_linear_bracket(time_values, target, expected_interval=600):
    """Return adjacent indices and weight for a strict regular-time bracket."""
    time_values = np.asarray(time_values, dtype=float)
    try:
        target = float(target)
        expected_interval = float(expected_interval)
    except (TypeError, ValueError) as error:
        raise ValueError('GTSM bracket inputs must be numeric') from error
    if time_values.ndim != 1 or len(time_values) < 2:
        raise ValueError('GTSM time coordinate must contain at least two values')
    if not np.isfinite(time_values).all() or not np.isfinite(target):
        raise ValueError('GTSM bracket inputs must be finite')
    if expected_interval <= 0 or not np.isfinite(expected_interval):
        raise ValueError('expected GTSM interval must be positive and finite')
    differences = np.diff(time_values)
    if not np.all(differences == expected_interval):
        raise ValueError(
            f'GTSM time coordinate is not regular at {expected_interval:g}'
        )

    upper = int(np.searchsorted(time_values, target, side='right'))
    lower = upper - 1
    if not (0 <= lower < upper < len(time_values)):
        raise ValueError('scene UTC is outside the GTSM time coordinate')
    if not time_values[lower] < target < time_values[upper]:
        raise ValueError('scene UTC does not have a strict two-sided bracket')
    weight = (
        (target - time_values[lower])
        / (time_values[upper] - time_values[lower])
    )
    return lower, upper, weight


def interpolate_finite_bracket(lower_values, upper_values, weight):
    """Interpolate only when both endpoints are finite at every station."""
    lower_values = np.asarray(lower_values, dtype=float)
    upper_values = np.asarray(upper_values, dtype=float)
    try:
        weight = float(weight)
    except (TypeError, ValueError) as error:
        raise ValueError('GTSM interpolation weight must be numeric') from error
    if lower_values.shape != upper_values.shape:
        raise ValueError('GTSM bracket endpoint shapes must match')
    if not 0 < weight < 1 or not np.isfinite(weight):
        raise ValueError('GTSM interpolation weight must be strictly between 0 and 1')
    if not (
        np.isfinite(lower_values).all()
        and np.isfinite(upper_values).all()
    ):
        return None
    return lower_values + weight * (upper_values - lower_values)


def recenter_annual_msl(
        annual_values, reference_start=1991, reference_end=2020):
    """Recenter finite station annual MSL while retaining source values."""
    required = {'gtsm_station_id', 'year', 'gtsm_msl_native_m'}
    missing = required.difference(annual_values.columns)
    if missing:
        raise ValueError(f'missing annual-MSL columns: {sorted(missing)}')
    if annual_values.duplicated(['gtsm_station_id', 'year']).any():
        raise ValueError('annual MSL must have one row per station and year')
    if reference_end < reference_start:
        raise ValueError('annual-MSL reference period is reversed')

    result = annual_values.copy()
    result['year'] = pd.to_numeric(result['year'], errors='coerce')
    result['gtsm_msl_native_m'] = pd.to_numeric(
        result['gtsm_msl_native_m'], errors='coerce'
    )
    if not np.isfinite(
        result[['year', 'gtsm_msl_native_m']].to_numpy(dtype=float)
    ).all():
        raise ValueError('annual-MSL years and source values must be finite')
    if not np.equal(result['year'], np.floor(result['year'])).all():
        raise ValueError('annual-MSL years must be integers')
    result['year'] = result['year'].astype(int)

    expected_years = set(range(reference_start, reference_end + 1))
    reference = result.loc[
        result['year'].between(reference_start, reference_end)
    ]
    years_by_station = reference.groupby('gtsm_station_id')['year'].agg(set)
    all_stations = set(result['gtsm_station_id'])
    if set(years_by_station.index) != all_stations or not years_by_station.map(
            lambda years: years == expected_years).all():
        raise ValueError(
            'every GTSM station must contain the complete reference period'
        )

    offsets = reference.groupby('gtsm_station_id')[
        'gtsm_msl_native_m'
    ].mean()
    result['gtsm_msl_reference_offset_m'] = result[
        'gtsm_station_id'
    ].map(offsets)
    result['gtsm_msl_anomaly_m'] = (
        result['gtsm_msl_native_m']
        - result['gtsm_msl_reference_offset_m']
    )
    residuals = result.loc[
        result['year'].between(reference_start, reference_end)
    ].groupby('gtsm_station_id')['gtsm_msl_anomaly_m'].mean()
    if not np.allclose(residuals, 0.0, rtol=0, atol=1e-12):
        raise ValueError('annual-MSL recentering did not produce a zero mean')
    return result


def retrieval_request(year, month):
    """Build the fixed CDS request for one pilot surge month."""
    if isinstance(year, bool) or isinstance(month, bool):
        raise ValueError('year and month must be integers')
    try:
        year = index(year)
        month = index(month)
    except TypeError as error:
        raise ValueError('year and month must be integers') from error
    if not 1950 <= year <= 2024:
        raise ValueError('GTSM reanalysis year must be from 1950 to 2024')
    if not 1 <= month <= 12:
        raise ValueError('month must be from 1 to 12')

    return {
        'variable': [VARIABLE],
        'experiment': EXPERIMENT,
        'temporal_aggregation': [TEMPORAL_AGGREGATION],
        'year': [f'{year:04d}'],
        'month': [f'{month:02d}'],
        'version': [VERSION],
    }


def archive_filename(year, month):
    """Return the stable local archive name for one requested month."""
    return (
        'gtsm-v3-reanalysis-surge-10-min-'
        f'{int(year):04d}-{int(month):02d}.zip'
    )


def expected_member_name(year, month):
    """Return the expected CDS NetCDF member name for one month."""
    return f'reanalysis_surge_10min_{int(year):04d}_{int(month):02d}_v3.nc'


def validate_archive(path, year, month):
    """Validate a downloaded monthly ZIP without extracting it."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    try:
        with ZipFile(path) as archive:
            members = [
                info for info in archive.infolist() if not info.is_dir()
            ]
            expected = expected_member_name(year, month)
            if [info.filename for info in members] != [expected]:
                raise ValueError(
                    f'{path.name} members do not match {expected!r}'
                )
            if members[0].file_size <= 0:
                raise ValueError(f'{path.name} contains an empty NetCDF')
            with archive.open(members[0]) as netcdf:
                if netcdf.read(8) != b'\x89HDF\r\n\x1a\n':
                    raise ValueError(
                        f'{path.name} member is not a NetCDF-4/HDF5 file'
                    )
            failed_member = archive.testzip()
            if failed_member is not None:
                raise ValueError(
                    f'{path.name} failed CRC validation at {failed_member}'
                )
    except BadZipFile as error:
        raise ValueError(f'{path.name} is not a valid ZIP archive') from error

    return {
        'archive_filename': path.name,
        'archive_bytes': path.stat().st_size,
        'netcdf_member': expected,
        'netcdf_bytes': members[0].file_size,
    }


def validate_annual_msl_archive(path, experiment):
    """Validate one fixed annual-MSL ZIP without extracting it."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    expected = expected_annual_msl_members(experiment)
    try:
        with ZipFile(path) as archive:
            members = [
                info for info in archive.infolist() if not info.is_dir()
            ]
            member_names = tuple(info.filename for info in members)
            if member_names != expected:
                raise ValueError(
                    f'{path.name} members do not match the fixed '
                    f'{experiment} annual-MSL member plan'
                )
            for member in members:
                if member.file_size <= 0:
                    raise ValueError(
                        f'{path.name} contains an empty NetCDF: '
                        f'{member.filename}'
                    )
                with archive.open(member) as netcdf:
                    if netcdf.read(8) != b'\x89HDF\r\n\x1a\n':
                        raise ValueError(
                            f'{path.name} member is not a NetCDF-4/HDF5 '
                            f'file: {member.filename}'
                        )
            failed_member = archive.testzip()
            if failed_member is not None:
                raise ValueError(
                    f'{path.name} failed CRC validation at {failed_member}'
                )
    except BadZipFile as error:
        raise ValueError(f'{path.name} is not a valid ZIP archive') from error

    return {
        'archive_filename': path.name,
        'archive_bytes': path.stat().st_size,
        'netcdf_member_count': len(members),
        'netcdf_members': '|'.join(expected),
        'netcdf_bytes': sum(member.file_size for member in members),
    }


def require_external_output_directory(output_dir, repo_root):
    """Require an existing output directory on a different mounted device."""
    output_dir = Path(output_dir).expanduser().resolve(strict=True)
    if not output_dir.is_dir():
        raise ValueError(f'GTSM output path is not a directory: {output_dir}')
    repo_root = Path(repo_root).resolve(strict=True)
    if output_dir == repo_root or repo_root in output_dir.parents:
        raise ValueError('GTSM output directory must be outside the repository')
    if output_dir.stat().st_dev == repo_root.stat().st_dev:
        raise ValueError(
            'GTSM output directory must be on a different mounted device'
        )
    return output_dir


def publish_without_overwrite(partial, target):
    """Publish a validated same-device partial without replacing a target."""
    partial = Path(partial)
    target = Path(target)
    if not partial.is_file():
        raise FileNotFoundError(partial)
    try:
        os.link(partial, target)
    except FileExistsError as error:
        raise FileExistsError(
            f'refusing to overwrite existing target: {target}'
        ) from error
    partial.unlink()


def sha256_file(path, chunk_size=1024 * 1024):
    """Return the SHA-256 digest of a local file."""
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(chunk_size), b''):
            digest.update(chunk)
    return digest.hexdigest()
