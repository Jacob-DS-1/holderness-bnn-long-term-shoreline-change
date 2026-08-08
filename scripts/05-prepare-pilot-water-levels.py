#!/usr/bin/env python
"""Build exact-time FES and GTSM evidence for the frozen pilot pool."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile

import geopandas as gpd
from netCDF4 import Dataset, date2num, num2date
import numpy as np
import pandas as pd
from pyproj import Geod, Transformer
import pyfes

from holderness import config, fes, gtsm, pilot
from holderness.geometry import seaward_normal


EXPECTED_SCENE_COUNT = 110
EXPECTED_SCENE_POOL_SHA256 = (
    '0e27aee5f5570349d454b1422b5fd7e2492f1e119b658db9825dc22b8d483ad9'
)
EXPECTED_SURGE_MONTH_COUNT = 94
EXPECTED_ANNUAL_ARCHIVE_COUNT = 2
EXPECTED_ARCHIVE_MANIFEST_SHA256 = (
    'aba2f2fe613736b2ead8498f3884d666267e05ebb7bd233bf581f4cc850e8b4b'
)
GTSM_SURGE_PRODUCT = 'GTSM v3.0; reanalysis CDS v3; 10-minute surge'
GTSM_MSL_PRODUCT = 'GTSM v3.0; historical/future CDS v1; annual MSL'
FES_PRODUCT = 'FES2022b Version 2024; ocean tide plus loading tide'
VERTICAL_REFERENCE_STATUS = (
    'components expressed relative to 1991-2020 local MSL; '
    'not converted to ODN'
)


def read_station_grid(dataset):
    """Return one validated decoded GTSM station grid."""
    required = {
        'stations', 'station_x_coordinate', 'station_y_coordinate',
    }
    missing = required.difference(dataset.variables)
    if missing:
        raise ValueError(f'GTSM file is missing grid variables: {sorted(missing)}')

    station_ids = np.asarray(dataset.variables['stations'][:])
    longitudes = np.asarray(dataset.variables['station_x_coordinate'][:])
    latitudes = np.asarray(dataset.variables['station_y_coordinate'][:])
    if not (
        station_ids.ndim == longitudes.ndim == latitudes.ndim == 1
        and len(station_ids) == len(longitudes) == len(latitudes)
    ):
        raise ValueError('GTSM station grid arrays have inconsistent shapes')
    if len(np.unique(station_ids)) != len(station_ids):
        raise ValueError('GTSM station IDs are not unique')
    if not (
        np.isfinite(longitudes).all() and np.isfinite(latitudes).all()
    ):
        raise ValueError('GTSM station coordinates must be finite')
    return station_ids, longitudes, latitudes


def station_grid_sha256(grid):
    """Hash decoded station IDs and coordinates in their supplied order."""
    station_ids, longitudes, latitudes = grid
    digest = hashlib.sha256()
    for name, values, dtype in (
        ('station_id', station_ids, '<i8'),
        ('longitude', longitudes, '<f8'),
        ('latitude', latitudes, '<f8'),
    ):
        canonical = np.asarray(values, dtype=dtype)
        digest.update(name.encode('ascii') + b'\0')
        digest.update(np.asarray(canonical.shape, dtype='<i8').tobytes())
        digest.update(canonical.tobytes())
    return digest.hexdigest()


def require_same_station_grid(actual, expected, label):
    """Require exact decoded station IDs and coordinates."""
    names = ('station IDs', 'longitudes', 'latitudes')
    for name, actual_values, expected_values in zip(names, actual, expected):
        if not np.array_equal(actual_values, expected_values):
            raise ValueError(f'{label} changed GTSM {name}')


def read_zip_member(path, member_name):
    """Read one exact ZIP member; ZipFile verifies its CRC while reading."""
    with ZipFile(path) as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        names = [info.filename for info in members]
        if member_name not in names:
            raise ValueError(f'{path.name} has no member {member_name}')
        return archive.read(member_name)


def load_reference_grid(gtsm_dir, annual_manifest):
    """Load the small first annual file as the canonical station grid."""
    historical = annual_manifest.loc[
        annual_manifest['experiment'].eq('historical')
    ]
    if len(historical) != 1:
        raise ValueError('annual-MSL manifest must contain one historical row')
    row = historical.iloc[0]
    path = gtsm_dir / row['archive_filename']
    gtsm.validate_annual_msl_archive(path, 'historical')
    member = str(row['netcdf_members']).split('|')[0]
    payload = read_zip_member(path, member)
    with Dataset('annual-msl-grid.nc', memory=payload) as dataset:
        return tuple(values.copy() for values in read_station_grid(dataset))


def require_core_sector_rows(sectors):
    """Return exactly one row for each approved core pilot sector."""
    required_columns = {
        'pilot_sector_id', 'role', 'chainage_start_m', 'chainage_end_m',
    }
    missing = required_columns.difference(sectors.columns)
    if missing:
        raise ValueError(f'pilot sectors are missing columns: {sorted(missing)}')
    core = sectors.loc[sectors['role'].eq('core_candidate')].copy()
    if core['pilot_sector_id'].duplicated().any():
        raise ValueError('core pilot-sector IDs must be unique')
    expected_sector_ids = set(config.PILOT_GTSM_STATION_IDS)
    if set(core['pilot_sector_id']) != expected_sector_ids:
        raise ValueError('core pilot sectors do not match approved GTSM mapping')
    return core


def build_sampling_nodes(seed_path, sectors_path, station_grid):
    """Reproduce the approved pilot-only FES points and GTSM stations."""
    seed_frame = gpd.read_file(seed_path)
    if len(seed_frame) != 1 or seed_frame.geometry.iloc[0].geom_type != 'LineString':
        raise ValueError('provisional geometry seed must contain one LineString')
    if seed_frame.crs is None or seed_frame.crs.to_epsg() != config.EPSG:
        raise ValueError(f'geometry seed must use EPSG:{config.EPSG}')
    seed = seed_frame.geometry.iloc[0]

    sectors = pd.read_csv(sectors_path)
    sectors = require_core_sector_rows(sectors)

    station_ids, station_lons, station_lats = station_grid
    transformer = Transformer.from_crs(config.EPSG, 4326, always_xy=True)
    geod = Geod(ellps='WGS84')
    records = []

    for sector in sectors.sort_values('chainage_start_m').itertuples(index=False):
        chainage = (
            float(sector.chainage_start_m) + float(sector.chainage_end_m)
        ) / 2
        if not 0 <= chainage <= seed.length:
            raise ValueError(f'{sector.pilot_sector_id} midpoint is outside seed')
        midpoint = seed.interpolate(chainage)
        normal = seaward_normal(
            seed, chainage, window=config.TRANSECT_NORMAL_WINDOW_M
        )
        midpoint_xy = np.asarray(midpoint.coords[0], dtype=float)
        fes_xy = midpoint_xy + config.PILOT_FES_OFFSHORE_DISTANCE_M * normal
        midpoint_lon, midpoint_lat = transformer.transform(*midpoint_xy)
        fes_lon, fes_lat = transformer.transform(*fes_xy)

        _, _, distances = geod.inv(
            np.full(len(station_lons), midpoint_lon),
            np.full(len(station_lats), midpoint_lat),
            station_lons,
            station_lats,
        )
        nearest_position = int(np.argmin(distances))
        nearest_station_id = int(station_ids[nearest_position])
        expected_station_id = config.PILOT_GTSM_STATION_IDS[
            sector.pilot_sector_id
        ]
        if nearest_station_id != expected_station_id:
            raise ValueError(
                f'{sector.pilot_sector_id} nearest station changed from '
                f'{expected_station_id} to {nearest_station_id}'
            )

        records.append({
            'pilot_sector_id': sector.pilot_sector_id,
            'chainage_midpoint_m': chainage,
            'seed_midpoint_easting_m': midpoint.x,
            'seed_midpoint_northing_m': midpoint.y,
            'seed_midpoint_longitude_deg': midpoint_lon,
            'seed_midpoint_latitude_deg': midpoint_lat,
            'fes_node_id': f'{sector.pilot_sector_id}_OS_SEED_3KM_SEAWARD',
            'fes_node_easting_m': float(fes_xy[0]),
            'fes_node_northing_m': float(fes_xy[1]),
            'fes_node_longitude_deg': fes_lon,
            'fes_node_latitude_deg': fes_lat,
            'fes_node_distance_m': float(config.PILOT_FES_OFFSHORE_DISTANCE_M),
            'fes_selection_method': (
                '3 km along provisional OS-seed seaward normal from '
                'core-sector midpoint'
            ),
            'gtsm_station_id': nearest_station_id,
            'gtsm_station_longitude_deg': float(
                station_lons[nearest_position]
            ),
            'gtsm_station_latitude_deg': float(
                station_lats[nearest_position]
            ),
            'gtsm_station_distance_m': float(distances[nearest_position]),
            'gtsm_selection_method': (
                'nearest distributed GTSM station to provisional '
                'core-sector midpoint'
            ),
            'geometry_status': config.PILOT_WATER_LEVEL_GEOMETRY_STATUS,
        })

    return pd.DataFrame(records).sort_values(
        'chainage_midpoint_m'
    ).reset_index(drop=True)


def require_archive_checksum(path, expected_sha256):
    """Require a local archive to match its recorded SHA-256 digest."""
    expected_sha256 = str(expected_sha256)
    if len(expected_sha256) != 64 or any(
            character not in '0123456789abcdef'
            for character in expected_sha256):
        raise ValueError(f'invalid archive checksum: {path.name}')
    actual_sha256 = gtsm.sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(f'archive checksum changed: {path.name}')
    return actual_sha256


def validate_download_ledgers(gtsm_dir, surge_path, annual_path):
    """Validate fixed ledger identities and every local archive checksum."""
    surge = pd.read_csv(surge_path)
    annual = pd.read_csv(annual_path)
    if len(surge) != EXPECTED_SURGE_MONTH_COUNT:
        raise ValueError(f'expected 94 surge ledger rows, found {len(surge)}')
    if surge.duplicated(['year', 'month']).any():
        raise ValueError('surge ledger contains duplicate months')
    if len(annual) != EXPECTED_ANNUAL_ARCHIVE_COUNT:
        raise ValueError(f'expected two annual ledger rows, found {len(annual)}')
    if set(annual['experiment']) != {'historical', 'future'}:
        raise ValueError('annual ledger experiments are incomplete')

    allowed_statuses = {'downloaded', 'existing_valid', 'promoted_valid_partial'}
    if not set(surge['status']).issubset(allowed_statuses):
        raise ValueError('surge ledger contains an unvalidated status')
    if not set(annual['status']).issubset(allowed_statuses):
        raise ValueError('annual-MSL ledger contains an unvalidated status')

    for row in surge.itertuples(index=False):
        expected_archive = gtsm.archive_filename(int(row.year), int(row.month))
        expected_member = gtsm.expected_member_name(
            int(row.year), int(row.month)
        )
        if row.archive_filename != expected_archive:
            raise ValueError(f'unexpected surge archive: {row.archive_filename}')
        if row.netcdf_member != expected_member:
            raise ValueError(f'unexpected surge member: {row.netcdf_member}')

    expected_plan_sha256 = gtsm.annual_msl_plan_sha256()
    for row in annual.itertuples(index=False):
        if row.archive_filename != gtsm.annual_msl_archive_filename(
                row.experiment):
            raise ValueError(
                f'unexpected annual-MSL archive: {row.archive_filename}'
            )
        expected_members = '|'.join(
            gtsm.expected_annual_msl_members(row.experiment)
        )
        if row.netcdf_members != expected_members:
            raise ValueError(
                f'unexpected annual-MSL members: {row.archive_filename}'
            )
        if row.retrieval_plan_sha256 != expected_plan_sha256:
            raise ValueError('annual-MSL retrieval-plan checksum changed')

    rows = [
        row for table in (surge, annual)
        for row in table.itertuples(index=False)
    ]
    for number, row in enumerate(rows, start=1):
        path = gtsm_dir / row.archive_filename
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size != int(row.archive_bytes):
            raise ValueError(f'archive size changed: {path.name}')
        require_archive_checksum(path, row.sha256)
        if number % 10 == 0 or number == len(rows):
            print(f'validated GTSM archive checksums: {number}/{len(rows)}')

    checksum_manifest = ''.join(
        f'{row.sha256}  {row.archive_filename}\n'
        for row in sorted(rows, key=lambda item: item.archive_filename)
    )
    combined_sha256 = hashlib.sha256(
        checksum_manifest.encode('utf-8')
    ).hexdigest()
    if combined_sha256 != EXPECTED_ARCHIVE_MANIFEST_SHA256:
        raise ValueError('combined 96-archive checksum manifest changed')
    return surge, annual


def extract_annual_msl(gtsm_dir, annual_manifest, nodes, reference_grid):
    """Read, merge and recenter the 35 annual MSL files at three stations."""
    node_by_station = nodes.set_index('gtsm_station_id')
    station_ids = tuple(node_by_station.index.astype(int))
    station_positions = gtsm.station_positions(reference_grid[0], station_ids)
    records = []

    for specification in gtsm.annual_msl_retrieval_plan():
        experiment = specification['experiment']
        row = annual_manifest.loc[
            annual_manifest['experiment'].eq(experiment)
        ].iloc[0]
        path = gtsm_dir / row['archive_filename']
        gtsm.validate_annual_msl_archive(path, experiment)
        expected_years = range(
            specification['start_year'], specification['end_year'] + 1
        )
        with ZipFile(path) as archive:
            for year, member in zip(
                expected_years, specification['expected_members']
            ):
                payload = archive.read(member)
                with Dataset('annual-msl.nc', memory=payload) as dataset:
                    required = {'time', 'mean_sea_level'}
                    missing = required.difference(dataset.variables)
                    if missing:
                        raise ValueError(
                            f'{member} is missing variables: {sorted(missing)}'
                        )
                    require_same_station_grid(
                        read_station_grid(dataset), reference_grid, member
                    )
                    variable = dataset.variables['mean_sea_level']
                    if variable.units != 'm':
                        raise ValueError(f'{member} mean sea level is not metres')
                    if '1986 to 2005' not in getattr(dataset, 'source', ''):
                        raise ValueError(
                            f'{member} does not document the native '
                            '1986-2005 reference period'
                        )
                    time = dataset.variables['time']
                    dates = num2date(
                        time[:], units=time.units,
                        calendar=getattr(time, 'calendar', 'standard'),
                        only_use_cftime_datetimes=False,
                    )
                    if len(dates) != 1 or int(dates[0].year) != year:
                        raise ValueError(f'{member} has an unexpected annual time')
                    values = np.ma.filled(
                        np.ma.asarray(variable[:]).squeeze(), np.nan
                    ).astype(float)
                    if values.shape != reference_grid[0].shape:
                        raise ValueError(f'{member} has an unexpected MSL shape')

                    for station_id, position in zip(
                        station_ids, station_positions
                    ):
                        value = float(values[position])
                        if not np.isfinite(value):
                            raise ValueError(
                                f'{member} has missing MSL at station '
                                f'{station_id}'
                            )
                        node = node_by_station.loc[station_id]
                        records.append({
                            'pilot_sector_id': node['pilot_sector_id'],
                            'gtsm_station_id': station_id,
                            'gtsm_station_longitude_deg': (
                                node['gtsm_station_longitude_deg']
                            ),
                            'gtsm_station_latitude_deg': (
                                node['gtsm_station_latitude_deg']
                            ),
                            'year': year,
                            'experiment': experiment,
                            'gtsm_msl_native_m': value,
                            'gtsm_msl_native_reference_period': (
                                gtsm.ANNUAL_MSL_SOURCE_REFERENCE_PERIOD
                            ),
                            'gtsm_msl_model_version': (
                                gtsm.ANNUAL_MSL_MODEL_VERSION
                            ),
                            'gtsm_msl_cds_version': (
                                gtsm.ANNUAL_MSL_CDS_VERSION
                            ),
                            'archive_filename': path.name,
                            'archive_sha256': row['sha256'],
                            'netcdf_member': member,
                        })

    annual = pd.DataFrame(records)
    # The station lookup above is keyed by station ID; attach the sector name
    # explicitly to avoid treating an integer index as a sector identifier.
    sector_by_station = nodes.set_index('gtsm_station_id')['pilot_sector_id']
    annual['pilot_sector_id'] = annual['gtsm_station_id'].map(
        sector_by_station
    )
    annual = gtsm.recenter_annual_msl(annual)
    if len(annual) != 35 * len(nodes):
        raise ValueError('annual-MSL extraction did not produce 105 rows')
    return annual.sort_values(
        ['pilot_sector_id', 'year']
    ).reset_index(drop=True)


def msl_merge_audit(annual, reference_grid):
    """Return structural, seam and recentering evidence without seam shifting."""
    required = {
        'gtsm_station_id', 'pilot_sector_id', 'year', 'experiment',
        'gtsm_msl_native_m', 'gtsm_msl_reference_offset_m',
        'gtsm_msl_anomaly_m',
    }
    missing = required.difference(annual.columns)
    if missing:
        raise ValueError(f'annual-MSL audit is missing columns: {sorted(missing)}')
    if annual.duplicated(['gtsm_station_id', 'year']).any():
        raise ValueError('annual-MSL audit has duplicate station-year rows')
    expected_station_ids = set(config.PILOT_GTSM_STATION_IDS.values())
    if set(annual['gtsm_station_id']) != expected_station_ids:
        raise ValueError('annual-MSL audit stations changed')
    expected_years = set(range(1990, 2025))
    years_by_station = annual.groupby('gtsm_station_id')['year'].agg(set)
    if not years_by_station.map(lambda years: years == expected_years).all():
        raise ValueError('annual-MSL audit requires 1990-2024 at every station')
    expected_experiment = np.where(
        annual['year'].astype(int) <= 2014, 'historical', 'future'
    )
    if not np.array_equal(annual['experiment'].to_numpy(), expected_experiment):
        raise ValueError('annual-MSL experiments do not meet at 2014-2015')
    numeric = annual[[
        'gtsm_msl_native_m', 'gtsm_msl_reference_offset_m',
        'gtsm_msl_anomaly_m',
    ]].apply(pd.to_numeric, errors='coerce')
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError('annual-MSL audit values must be finite')

    station_records = []
    for station_id, series in annual.groupby('gtsm_station_id', sort=True):
        values = series.set_index('year')['gtsm_msl_native_m']
        anomalies = series.set_index('year')['gtsm_msl_anomaly_m']
        station_records.append({
            'gtsm_station_id': int(station_id),
            'pilot_sector_id': series['pilot_sector_id'].iloc[0],
            'reference_offset_1991_2020_m': float(
                series['gtsm_msl_reference_offset_m'].iloc[0]
            ),
            'reference_mean_residual_m': float(
                anomalies.loc[1991:2020].mean()
            ),
            'msl_2013_m': float(values.loc[2013]),
            'msl_2014_m': float(values.loc[2014]),
            'msl_2015_m': float(values.loc[2015]),
            'msl_2016_m': float(values.loc[2016]),
            'increment_2013_2014_m': float(
                values.loc[2014] - values.loc[2013]
            ),
            'seam_increment_2014_2015_m': float(
                values.loc[2015] - values.loc[2014]
            ),
            'increment_2015_2016_m': float(
                values.loc[2016] - values.loc[2015]
            ),
        })

    native_by_station = annual.pivot(
        index='year', columns='gtsm_station_id', values='gtsm_msl_native_m'
    ).sort_index(axis=1)
    station_ids = list(native_by_station.columns)
    contrast_changes = []
    for first_position, first_station in enumerate(station_ids):
        for second_station in station_ids[first_position + 1:]:
            contrast_2014 = (
                native_by_station.loc[2014, first_station]
                - native_by_station.loc[2014, second_station]
            )
            contrast_2015 = (
                native_by_station.loc[2015, first_station]
                - native_by_station.loc[2015, second_station]
            )
            contrast_changes.append(abs(contrast_2015 - contrast_2014))

    seam_increments = [
        abs(record['seam_increment_2014_2015_m'])
        for record in station_records
    ]
    neighbour_increments = [
        abs(record[key])
        for record in station_records
        for key in ('increment_2013_2014_m', 'increment_2015_2016_m')
    ]
    return {
        'schema_version': 1,
        'status': 'complete_structural_and_descriptive_checks_no_overlap_test',
        'year_coverage': '1990-2024',
        'annual_row_count': len(annual),
        'station_count': annual['gtsm_station_id'].nunique(),
        'full_station_grid_count': len(reference_grid[0]),
        'full_station_grid_sha256': station_grid_sha256(reference_grid),
        'source_reference_period': gtsm.ANNUAL_MSL_SOURCE_REFERENCE_PERIOD,
        'derived_reference_period': gtsm.ANNUAL_MSL_TARGET_REFERENCE_PERIOD,
        'recenter_formula': (
            'native annual MSL minus the station arithmetic mean for '
            '1991-2020'
        ),
        'odn_status': 'not an ODN conversion',
        'experiment_boundary': 'historical through 2014; future from 2015',
        'boundary_treatment': 'preserved without smoothing or offset',
        'overlap_limitation': (
            'the two experiments do not overlap, so a branch bias cannot be '
            'estimated directly'
        ),
        'human_review_required': True,
        'seam_diagnostics': {
            'maximum_absolute_2014_2015_increment_m': float(
                max(seam_increments)
            ),
            'maximum_absolute_adjacent_increment_m': float(
                max(neighbour_increments)
            ),
            'maximum_station_contrast_change_2014_2015_m': float(
                max(contrast_changes)
            ),
            'interpretation_boundary': (
                'descriptive evidence only; no automated pass threshold is '
                'used because the experiments do not overlap'
            ),
        },
        'source_limitation': (
            'product metadata describe 1950-2016 as observation-constrained '
            'and 2016-2060 as an RCP8.5 ensemble mean'
        ),
        'stations': station_records,
    }


def format_netcdf_time(value):
    """Format a decoded naive model time explicitly as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace('+00:00', 'Z')


def extract_surges(
        gtsm_dir, surge_manifest, scenes, nodes, reference_grid):
    """Interpolate exact-time surge using the approved finite bracket rule."""
    scene_times = pd.to_datetime(
        scenes['acquisition_time_utc'], format='mixed', utc=True,
        errors='raise',
    )
    scenes = scenes.copy()
    scenes['year'] = scene_times.dt.year
    scenes['month'] = scene_times.dt.month
    scenes['scene_utc'] = scene_times
    manifest_by_month = {
        (int(row.year), int(row.month)): row
        for row in surge_manifest.itertuples(index=False)
    }
    node_by_station = nodes.set_index('gtsm_station_id')
    station_ids = tuple(node_by_station.index.astype(int))
    positions = gtsm.station_positions(reference_grid[0], station_ids)
    records = []
    scene_status = {}

    groups = scenes.groupby(['year', 'month'], sort=True)
    for group_number, ((year, month), monthly_scenes) in enumerate(
        groups, start=1
    ):
        if (year, month) not in manifest_by_month:
            raise ValueError(f'no surge archive for {year:04d}-{month:02d}')
        ledger = manifest_by_month[(year, month)]
        path = gtsm_dir / ledger.archive_filename
        payload = read_zip_member(path, ledger.netcdf_member)
        with Dataset('surge.nc', memory=payload) as dataset:
            required = {'time', 'surge'}
            missing = required.difference(dataset.variables)
            if missing:
                raise ValueError(
                    f'{path.name} is missing variables: {sorted(missing)}'
                )
            require_same_station_grid(
                read_station_grid(dataset), reference_grid, path.name
            )
            surge = dataset.variables['surge']
            if surge.units != 'm':
                raise ValueError(f'{path.name} surge is not in metres')
            time = dataset.variables['time']
            numeric_time = np.asarray(time[:], dtype=float)
            calendar = getattr(time, 'calendar', 'standard')

            for scene in monthly_scenes.itertuples(index=False):
                target_datetime = scene.scene_utc.to_pydatetime().replace(
                    tzinfo=None
                )
                target = float(date2num(
                    target_datetime, units=time.units, calendar=calendar
                ))
                lower, upper, weight = gtsm.strict_linear_bracket(
                    numeric_time, target, expected_interval=600
                )
                endpoint_values = np.ma.filled(
                    np.ma.asarray(surge[lower:upper + 1, positions]), np.nan
                ).astype(float)
                if endpoint_values.shape != (2, len(station_ids)):
                    raise ValueError(
                        f'{scene.source_scene_id} has unexpected surge slice '
                        f'{endpoint_values.shape}'
                    )
                interpolated = gtsm.interpolate_finite_bracket(
                    endpoint_values[0], endpoint_values[1], weight
                )
                valid = interpolated is not None
                status = (
                    'valid' if valid else 'excluded_missing_gtsm_bracket'
                )
                scene_status[scene.source_scene_id] = status
                bracket_dates = num2date(
                    numeric_time[[lower, upper]], units=time.units,
                    calendar=calendar, only_use_cftime_datetimes=False,
                )

                for station_number, station_id in enumerate(station_ids):
                    node = node_by_station.loc[station_id]
                    records.append({
                        'source_scene_id': scene.source_scene_id,
                        'acquisition_time_utc': scene.acquisition_time_utc,
                        'acquisition_year': int(year),
                        'pilot_sector_id': node['pilot_sector_id'],
                        'gtsm_station_id': station_id,
                        'gtsm_station_longitude_deg': (
                            node['gtsm_station_longitude_deg']
                        ),
                        'gtsm_station_latitude_deg': (
                            node['gtsm_station_latitude_deg']
                        ),
                        'gtsm_station_distance_m': (
                            node['gtsm_station_distance_m']
                        ),
                        'gtsm_lower_time_utc': format_netcdf_time(
                            bracket_dates[0]
                        ),
                        'gtsm_upper_time_utc': format_netcdf_time(
                            bracket_dates[1]
                        ),
                        'gtsm_interpolation_weight': weight,
                        'gtsm_lower_surge_m': endpoint_values[
                            0, station_number
                        ],
                        'gtsm_upper_surge_m': endpoint_values[
                            1, station_number
                        ],
                        'gtsm_surge_m': (
                            interpolated[station_number]
                            if valid else np.nan
                        ),
                        'gtsm_sample_status': status,
                        'gtsm_missing_data_rule': (
                            'both surrounding 10-minute values finite at '
                            'every required station; otherwise exclude scene'
                        ),
                        'gtsm_surge_product_version': GTSM_SURGE_PRODUCT,
                        'gtsm_surge_archive_filename': path.name,
                        'gtsm_surge_archive_sha256': ledger.sha256,
                        'gtsm_surge_netcdf_member': ledger.netcdf_member,
                    })
        if group_number % 10 == 0 or group_number == len(groups):
            print(f'processed surge months: {group_number}/{len(groups)}')

    samples = pd.DataFrame(records).sort_values(
        ['acquisition_time_utc', 'pilot_sector_id']
    ).reset_index(drop=True)
    if len(samples) != len(scenes) * len(nodes):
        raise ValueError('surge extraction did not produce 330 evidence rows')
    return samples, scene_status


def evaluate_fes(samples, nodes, fes_config):
    """Evaluate ocean and loading tide in one small model subset per sector."""
    result = samples.copy()
    node_by_sector = nodes.set_index('pilot_sector_id')
    result['fes_ocean_tide_m'] = np.nan
    result['fes_loading_tide_m'] = np.nan
    result['fes_ocean_flag'] = pd.Series(index=result.index, dtype='Int64')
    result['fes_loading_flag'] = pd.Series(index=result.index, dtype='Int64')

    for sector_id, indices in result.groupby('pilot_sector_id').groups.items():
        node = node_by_sector.loc[sector_id]
        frame = result.loc[indices]
        dates = pd.to_datetime(
            frame['acquisition_time_utc'], format='mixed', utc=True,
            errors='raise',
        ).dt.tz_localize(None).to_numpy(dtype='datetime64[ns]')
        longitudes = np.full(
            len(frame), node['fes_node_longitude_deg'], dtype=float
        )
        latitudes = np.full(
            len(frame), node['fes_node_latitude_deg'], dtype=float
        )
        bbox = (
            float(longitudes[0] - 0.05), float(latitudes[0] - 0.05),
            float(longitudes[0] + 0.05), float(latitudes[0] + 0.05),
        )
        loaded = pyfes.config.load(str(fes_config), bbox=bbox)

        for component, model_name, value_column, flag_column in (
            ('ocean', 'tide', 'fes_ocean_tide_m', 'fes_ocean_flag'),
            ('loading', 'radial', 'fes_loading_tide_m', 'fes_loading_flag'),
        ):
            short_cm, long_cm, flags = pyfes.evaluate_tide(
                loaded.models[model_name], dates, longitudes, latitudes
            )
            heights = np.array([
                fes.component_height_metres(short, long)
                for short, long in zip(short_cm, long_cm)
            ])
            for flag in flags:
                fes.require_interpolated_flag(flag, component)
            result.loc[indices, value_column] = heights
            result.loc[indices, flag_column] = np.asarray(flags, dtype=int)

    result['fes_astronomical_tide_m'] = (
        result['fes_ocean_tide_m'] + result['fes_loading_tide_m']
    )
    for column in (
        'fes_node_id', 'fes_node_longitude_deg', 'fes_node_latitude_deg',
        'fes_node_distance_m',
    ):
        result[column] = result['pilot_sector_id'].map(
            node_by_sector[column]
        )
    result['fes_product_version'] = FES_PRODUCT
    return result


def combine_water_levels(surge_samples, annual, nodes, fes_config):
    """Build the complete scene-sector evidence table for valid surge scenes."""
    valid = surge_samples.loc[
        surge_samples['gtsm_sample_status'].eq('valid')
    ].copy()
    annual_columns = [
        'pilot_sector_id', 'year', 'experiment', 'gtsm_msl_native_m',
        'gtsm_msl_reference_offset_m', 'gtsm_msl_anomaly_m',
        'gtsm_msl_native_reference_period', 'gtsm_msl_cds_version',
    ]
    valid = valid.merge(
        annual[annual_columns],
        left_on=['pilot_sector_id', 'acquisition_year'],
        right_on=['pilot_sector_id', 'year'],
        how='left', validate='many_to_one',
    )
    if valid['gtsm_msl_anomaly_m'].isna().any():
        raise ValueError('one or more valid surge rows has no annual MSL')
    valid = evaluate_fes(valid, nodes, fes_config)
    valid['gtsm_product_version'] = (
        GTSM_SURGE_PRODUCT + '; ' + GTSM_MSL_PRODUCT
    )
    valid['gtsm_msl_reference_period'] = (
        gtsm.ANNUAL_MSL_TARGET_REFERENCE_PERIOD
    )
    valid['vertical_reference_status'] = VERTICAL_REFERENCE_STATUS
    valid = pilot.add_fes_astronomical_tide(valid)
    valid = pilot.add_pilot_still_water_anomaly(valid)
    valid = pilot.add_p023_water_bands(valid)
    return valid.sort_values(
        ['acquisition_time_utc', 'pilot_sector_id']
    ).reset_index(drop=True)


def surge_statistics(samples):
    """Return implementation-plan P055 diagnostics for valid candidates."""
    valid = samples.loc[samples['gtsm_sample_status'].eq('valid')].copy()

    def describe(frame):
        values = frame['gtsm_surge_m'].astype(float)
        absolute = values.abs()
        return {
            'row_count': len(values),
            'median_surge_m': float(values.median()),
            'absolute_median_m': float(absolute.median()),
            'absolute_p90_m': float(absolute.quantile(0.90)),
            'absolute_p95_m': float(absolute.quantile(0.95)),
            'absolute_p99_m': float(absolute.quantile(0.99)),
            'proportion_absolute_gt_0_1_m': float((absolute > 0.1).mean()),
        }

    return {
        'all_candidate_scene_sector_rows': describe(valid),
        'by_sector': {
            sector_id: describe(frame)
            for sector_id, frame in valid.groupby('pilot_sector_id')
        },
    }


def atomic_write_csv(frame, path):
    """Atomically replace one CSV after its complete temporary write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
                mode='w', dir=path.parent, suffix='.csv.tmp',
                encoding='utf-8', newline='', delete=False) as temporary:
            temporary_path = Path(temporary.name)
            frame.to_csv(temporary, index=False)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def atomic_write_json(value, path):
    """Atomically replace one human-readable JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
                mode='w', dir=path.parent, suffix='.json.tmp',
                encoding='utf-8', delete=False) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(value, temporary, indent=2)
            temporary.write('\n')
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def path_label(path):
    """Return a repository-relative label where one is available."""
    try:
        return str(path.relative_to(config.REPO_ROOT))
    except ValueError:
        return str(path)


def save_msl_figure(annual, path):
    """Save a compact raw-series and first-difference seam figure."""
    os.environ.setdefault(
        'MPLCONFIGDIR',
        str(Path(tempfile.gettempdir()) / 'holderness-bnn-matplotlib'),
    )
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    colors = plt.get_cmap('tab10')
    fig, axes = plt.subplots(
        2, 1, figsize=(9, 7), sharex=True,
        gridspec_kw={'height_ratios': [2, 1]},
    )
    for number, (sector_id, frame) in enumerate(
        annual.groupby('pilot_sector_id', sort=True)
    ):
        frame = frame.sort_values('year')
        label = sector_id.replace('HOL_PILOT_', '').replace('_', ' ').title()
        color = colors(number)
        axes[0].plot(
            frame['year'], frame['gtsm_msl_native_m'], marker='o',
            markersize=3, linewidth=1.5, color=color, label=label,
        )
        axes[1].plot(
            frame['year'].iloc[1:],
            frame['gtsm_msl_native_m'].diff().iloc[1:],
            marker='o', markersize=3, linewidth=1.2, color=color,
        )
    for axis in axes:
        axis.axvline(2014.5, color='0.25', linestyle='--', linewidth=1)
        axis.grid(alpha=0.25)
    axes[0].set_ylabel('Native annual MSL anomaly (m)\nrelative to 1986–2005')
    axes[0].set_title('GTSM annual mean sea level across the experiment boundary')
    axes[0].legend(frameon=False, fontsize=8)
    axes[1].set_ylabel('Annual increment (m)')
    axes[1].set_xlabel('Year')
    axes[1].annotate(
        'historical / future boundary', xy=(2014.5, 0.98),
        xycoords=('data', 'axes fraction'), xytext=(5, -2),
        textcoords='offset points', va='top', fontsize=8,
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
                dir=path.parent, suffix=path.suffix, delete=False) as temporary:
            temporary_path = Path(temporary.name)
        fig.savefig(temporary_path, dpi=200, bbox_inches='tight')
        os.replace(temporary_path, path)
    finally:
        plt.close(fig)
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def write_outputs(
        output_dir, figure_path, nodes, annual, audit, surge_samples,
        water_levels, scene_status, input_identities):
    """Write all evidence only after the complete calculation has passed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        'pilot_water_level_nodes': output_dir / 'pilot-water-level-nodes.csv',
        'gtsm_msl_station_series': (
            output_dir / 'gtsm-msl-station-series.csv'
        ),
        'gtsm_msl_merge_audit': output_dir / 'gtsm-msl-merge-audit.json',
        'gtsm_pilot_surge_samples': (
            output_dir / 'gtsm-pilot-surge-samples.csv'
        ),
        'pilot_scene_water_levels': (
            output_dir / 'pilot-scene-water-levels.csv'
        ),
        'gtsm_msl_figure': figure_path,
    }
    atomic_write_csv(nodes, output_paths['pilot_water_level_nodes'])
    atomic_write_csv(annual, output_paths['gtsm_msl_station_series'])
    atomic_write_json(audit, output_paths['gtsm_msl_merge_audit'])
    atomic_write_csv(
        surge_samples, output_paths['gtsm_pilot_surge_samples']
    )
    atomic_write_csv(water_levels, output_paths['pilot_scene_water_levels'])
    save_msl_figure(annual, figure_path)
    output_identities = {
        name: {
            'path': path_label(path),
            'sha256': gtsm.sha256_file(path),
        }
        for name, path in output_paths.items()
    }

    status_counts = Counter(scene_status.values())
    excluded = sorted(
        scene_id for scene_id, status in scene_status.items()
        if status != 'valid'
    )
    band_counts = (
        water_levels.groupby(['pilot_sector_id', 'water_level_band'])
        .size().rename('scene_count').reset_index().to_dict('records')
    )
    summary = {
        'schema_version': 1,
        'status': 'complete_water_level_evidence_dates_still_unselected',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'input_identities': input_identities,
        'output_identities': output_identities,
        'candidate_scene_count': len(scene_status),
        'scene_status_counts': dict(status_counts),
        'excluded_scene_ids': excluded,
        'scene_sector_row_count': len(water_levels),
        'annual_msl_merge_status': audit['status'],
        'surge_statistics': surge_statistics(surge_samples),
        'fes_ocean_flag_counts': {
            str(key): int(value) for key, value in Counter(
                map(int, water_levels['fes_ocean_flag'])
            ).items()
        },
        'fes_loading_flag_counts': {
            str(key): int(value) for key, value in Counter(
                map(int, water_levels['fes_loading_flag'])
            ).items()
        },
        'water_level_band_counts': band_counts,
        'vertical_reference_status': VERTICAL_REFERENCE_STATUS,
        'node_status': config.PILOT_WATER_LEVEL_GEOMETRY_STATUS,
        'generated_figure': path_label(figure_path),
        'not_authorised': ['imagery retrieval', 'shoreline extraction'],
    }
    atomic_write_json(
        summary, output_dir / 'pilot-water-level-summary.json'
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gtsm-dir', type=Path, required=True)
    parser.add_argument(
        '--fes-config', type=Path,
        default=config.DATA_RAW / 'fes2022b' / 'fes2022.yaml',
    )
    parser.add_argument(
        '--scenes', type=Path,
        default=config.PILOT_DATA / 'pilot-water-level-evaluation-scenes.csv',
    )
    parser.add_argument(
        '--sectors', type=Path,
        default=config.DATA_INTERIM / 'pilot' / 'pilot-sector-candidates.csv',
    )
    parser.add_argument(
        '--seed', type=Path,
        default=config.GEOMETRY_DATA / 'os-geometry-seed.geojson',
    )
    parser.add_argument(
        '--surge-manifest', type=Path,
        default=config.PILOT_DATA / 'gtsm-pilot-download-manifest.csv',
    )
    parser.add_argument(
        '--annual-manifest', type=Path,
        default=config.PILOT_DATA / 'gtsm-annual-msl-download-manifest.csv',
    )
    parser.add_argument('--output-dir', type=Path, default=config.PILOT_DATA)
    parser.add_argument(
        '--figure', type=Path,
        default=config.FIGURES / 'gtsm-msl-historical-future-seam.png',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='validate inputs and approved nodes without writing outputs',
    )
    args = parser.parse_args()

    gtsm_dir = gtsm.require_external_output_directory(
        args.gtsm_dir, config.REPO_ROOT
    )
    fes_config = args.fes_config.expanduser().resolve()
    if not fes_config.is_file():
        raise FileNotFoundError(fes_config)
    scenes = pd.read_csv(args.scenes)
    if len(scenes) != EXPECTED_SCENE_COUNT:
        raise ValueError(f'expected 110 frozen scenes, found {len(scenes)}')
    if scenes['source_scene_id'].duplicated().any():
        raise ValueError('frozen water-level scenes contain duplicate IDs')
    if gtsm.evaluation_pool_sha256(scenes) != EXPECTED_SCENE_POOL_SHA256:
        raise ValueError('frozen water-level scene identities or UTCs changed')

    surge_manifest, annual_manifest = validate_download_ledgers(
        gtsm_dir, args.surge_manifest, args.annual_manifest
    )
    planned_months = gtsm.retrieval_months(scenes)
    ledger_months = set(map(
        tuple,
        surge_manifest[['year', 'month']].astype(int).to_numpy(),
    ))
    frozen_months = set(map(
        tuple,
        planned_months[['year', 'month']].astype(int).to_numpy(),
    ))
    if ledger_months != frozen_months:
        raise ValueError('surge download ledger does not match frozen scene months')
    reference_grid = load_reference_grid(gtsm_dir, annual_manifest)
    nodes = build_sampling_nodes(args.seed, args.sectors, reference_grid)
    input_identities = {
        'frozen_scene_pool': {
            'path': path_label(args.scenes.resolve()),
            'file_sha256': gtsm.sha256_file(args.scenes),
            'scene_id_utc_sha256': gtsm.evaluation_pool_sha256(scenes),
        },
        'pilot_sectors': {
            'path': path_label(args.sectors.resolve()),
            'file_sha256': gtsm.sha256_file(args.sectors),
        },
        'provisional_geometry_seed': {
            'path': path_label(args.seed.resolve()),
            'file_sha256': gtsm.sha256_file(args.seed),
            'status': config.PILOT_WATER_LEVEL_GEOMETRY_STATUS,
        },
        'fes_configuration': {
            'path': path_label(fes_config),
            'file_sha256': gtsm.sha256_file(fes_config),
            'product': FES_PRODUCT,
        },
        'surge_download_manifest': {
            'path': path_label(args.surge_manifest.resolve()),
            'file_sha256': gtsm.sha256_file(args.surge_manifest),
        },
        'annual_msl_download_manifest': {
            'path': path_label(args.annual_manifest.resolve()),
            'file_sha256': gtsm.sha256_file(args.annual_manifest),
            'retrieval_plan_sha256': gtsm.annual_msl_plan_sha256(),
        },
        'gtsm_archive_checksum_manifest_sha256': (
            EXPECTED_ARCHIVE_MANIFEST_SHA256
        ),
    }
    print(
        f'pilot water-level design: {len(scenes)} scenes x '
        f'{len(nodes)} core sectors; {len(surge_manifest)} surge months'
    )
    print(nodes[[
        'pilot_sector_id', 'fes_node_longitude_deg',
        'fes_node_latitude_deg', 'gtsm_station_id',
        'gtsm_station_distance_m',
    ]].to_string(index=False))
    if args.dry_run:
        print('dry run passed; no evidence outputs were written')
        return

    annual = extract_annual_msl(
        gtsm_dir, annual_manifest, nodes, reference_grid
    )
    audit = msl_merge_audit(annual, reference_grid)
    surge_samples, scene_status = extract_surges(
        gtsm_dir, surge_manifest, scenes, nodes, reference_grid
    )
    water_levels = combine_water_levels(
        surge_samples, annual, nodes, fes_config
    )
    if len(water_levels) != 3 * sum(
        status == 'valid' for status in scene_status.values()
    ):
        raise ValueError('final water-level table does not match valid scenes')

    write_outputs(
        args.output_dir.expanduser().resolve(),
        args.figure.expanduser().resolve(),
        nodes, annual, audit, surge_samples, water_levels, scene_status,
        input_identities,
    )
    print(
        f'wrote {len(water_levels)} scene-sector rows to '
        f'{args.output_dir.expanduser().resolve()}'
    )
    print('pilot water-level preparation passed; this stage does not select dates')


if __name__ == '__main__':
    main()
