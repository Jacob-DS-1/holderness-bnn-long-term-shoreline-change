"""Prepare a blinded pilot candidate pool from the availability manifest."""

import numpy as np
import pandas as pd


PENDING_SCENE_LABEL_COLUMNS = (
    'water_level_band',
)

SCENE_CANDIDATE_POOL_STATUS = 'scene_candidate_pool_not_frozen'

PENDING_PILOT_STEPS = (
    'scene_shortlist_selection',
    'local_sector_selection',
    'water_level_assignment',
    'independent_validation_match',
)

FES_TIDE_COMPONENT_COLUMNS = (
    'fes_ocean_tide_m',
    'fes_loading_tide_m',
)
FES_ASTRONOMICAL_TIDE_COLUMN = 'fes_astronomical_tide_m'

PILOT_STILL_WATER_COMPONENT_COLUMNS = (
    'gtsm_msl_anomaly_m',
    FES_ASTRONOMICAL_TIDE_COLUMN,
    'gtsm_surge_m',
)
PILOT_STILL_WATER_COLUMN = 'pilot_still_water_anomaly_m'

P023_WATER_LEVEL_BANDS = (
    'below_local_amsl',
    'local_amsl_to_below_plus_0_2_m',
    'at_or_above_local_amsl_plus_0_2_m',
)
P023_AMSL_FILTER_COLUMN = 'passes_local_amsl_filter'
P023_AMSL_PLUS_0_2_M_FILTER_COLUMN = (
    'passes_local_amsl_plus_0_2_m_filter'
)

SCENE_INVARIANT_COLUMNS = (
    'stream',
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
)


def _pipe_values(value):
    """Return non-empty values from a pipe-delimited manifest field."""
    return {item for item in str(value).split('|') if item}


def _finite_numeric_columns(frame, columns):
    """Return requested columns as numbers or reject invalid values."""
    missing = set(columns).difference(frame.columns)
    if missing:
        raise ValueError(f'missing columns: {sorted(missing)}')

    numeric = frame.loc[:, list(columns)].apply(pd.to_numeric, errors='coerce')
    finite = np.isfinite(numeric.to_numpy(dtype=float))
    if not finite.all():
        invalid = {}
        for position, column in enumerate(columns):
            rows = frame.index[~finite[:, position]].tolist()
            if rows:
                invalid[column] = rows[:5]
        raise ValueError(
            'water-level inputs must be finite numeric values; '
            f'invalid rows by column: {invalid}'
        )
    return numeric


def collapse_scene_coverage(scenes):
    """Collapse ROI-scene rows to one validated row per source scene.

    A source scene can intersect several availability ROIs. Metadata must be
    invariant across those rows; only the ROI coverage is aggregated.
    """
    required = set(SCENE_INVARIANT_COLUMNS) | {'roi_id'}
    missing = required.difference(scenes.columns)
    if missing:
        raise ValueError(f'missing scene columns: {sorted(missing)}')
    if scenes.empty:
        raise ValueError('the scene manifest is empty')
    if scenes['source_scene_id'].isna().any():
        raise ValueError('source_scene_id must not be missing')
    if scenes.duplicated(['source_scene_id', 'roi_id']).any():
        raise ValueError('duplicate source_scene_id and roi_id rows')

    grouped = scenes.groupby('source_scene_id', sort=True, dropna=False)
    counts = grouped[list(SCENE_INVARIANT_COLUMNS)].nunique(dropna=False)
    inconsistent = counts.gt(1).any(axis=1)
    if inconsistent.any():
        scene_ids = counts.index[inconsistent].tolist()
        raise ValueError(
            f'inconsistent metadata across ROI rows for scenes: {scene_ids[:5]}'
        )

    catalog = (
        scenes.sort_values(['source_scene_id', 'roi_id'])
        .drop_duplicates('source_scene_id')
        .loc[:, SCENE_INVARIANT_COLUMNS]
        .copy()
    )
    roi_coverage = grouped['roi_id'].agg(
        lambda values: '|'.join(sorted(set(values)))
    )
    catalog['covered_roi_ids'] = catalog['source_scene_id'].map(roi_coverage)
    catalog['covered_roi_count'] = catalog['covered_roi_ids'].map(
        lambda value: len(_pipe_values(value))
    )

    return catalog.sort_values(
        ['acquisition_time_utc', 'sensor', 'source_scene_id']
    ).reset_index(drop=True)


def add_sector_coverage(scene_catalog, sectors, required_roles=('core_candidate',)):
    """Attach conservative sector coverage derived from availability ROIs.

    A scene covers a sector only when it occurs in every ROI intersecting that
    sector. This is a metadata feasibility check, not local pixel validation.
    """
    scene_required = {'source_scene_id', 'covered_roi_ids'}
    sector_required = {
        'pilot_sector_id', 'role', 'intersecting_roi_ids',
    }
    missing_scene = scene_required.difference(scene_catalog.columns)
    missing_sector = sector_required.difference(sectors.columns)
    if missing_scene:
        raise ValueError(
            f'missing scene-catalog columns: {sorted(missing_scene)}'
        )
    if missing_sector:
        raise ValueError(f'missing sector columns: {sorted(missing_sector)}')
    if sectors['pilot_sector_id'].duplicated().any():
        raise ValueError('pilot_sector_id values must be unique')

    sector_rois = {
        row.pilot_sector_id: _pipe_values(row.intersecting_roi_ids)
        for row in sectors.itertuples(index=False)
    }
    if any(not values for values in sector_rois.values()):
        raise ValueError('every pilot sector must intersect at least one ROI')

    required_sector_ids = set(
        sectors.loc[
            sectors['role'].isin(required_roles), 'pilot_sector_id'
        ]
    )
    if not required_sector_ids:
        raise ValueError('no sectors match required_roles')

    result = scene_catalog.copy()

    def covered_sectors(covered_roi_ids):
        scene_rois = _pipe_values(covered_roi_ids)
        return [
            sector_id for sector_id, required_rois in sector_rois.items()
            if required_rois.issubset(scene_rois)
        ]

    coverage = result['covered_roi_ids'].map(covered_sectors)
    result['covered_sector_ids'] = coverage.map(
        lambda values: '|'.join(values)
    )
    result['covered_sector_count'] = coverage.map(len)
    result['covers_all_required_sectors'] = coverage.map(
        lambda values: required_sector_ids.issubset(values)
    )
    return result


def add_pilot_still_water_anomaly(water_levels):
    """Add the tide, surge and mean-sea-level anomaly used by the pilot.

    All three components must be present and finite. The result remains a
    still-water quantity: no wave setup or runup term is included.
    """
    result = water_levels.copy()
    components = _finite_numeric_columns(
        result, PILOT_STILL_WATER_COMPONENT_COLUMNS
    )
    anomaly = components.sum(axis=1)
    if not np.isfinite(anomaly.to_numpy(dtype=float)).all():
        raise ValueError('calculated pilot still-water anomaly is not finite')
    result[PILOT_STILL_WATER_COLUMN] = anomaly
    return result


def add_fes_astronomical_tide(water_levels):
    """Add FES ocean and loading tide under the pinned CoastSat convention.

    The confirmed convention is ``ocean tide + loading tide``. Both component
    values must be present and finite; the input table is not modified.
    """
    result = water_levels.copy()
    components = _finite_numeric_columns(result, FES_TIDE_COMPONENT_COLUMNS)
    astronomical_tide = components.sum(axis=1)
    if not np.isfinite(astronomical_tide.to_numpy(dtype=float)).all():
        raise ValueError('calculated FES astronomical tide is not finite')
    result[FES_ASTRONOMICAL_TIDE_COLUMN] = astronomical_tide
    return result


def add_p023_water_bands(water_levels):
    """Assign the three P023 bands and corresponding image-filter flags.

    Bands are below local AMSL, from local AMSL up to but excluding 0.2 m,
    and at least 0.2 m above local AMSL. The Boolean flags indicate whether
    a scene passes each of the two candidate low-water exclusions.
    """
    result = water_levels.copy()
    values = _finite_numeric_columns(
        result, (PILOT_STILL_WATER_COLUMN,)
    )[PILOT_STILL_WATER_COLUMN]

    below_amsl = values < 0.0
    below_plus_0_2_m = values < 0.2
    result['water_level_band'] = np.select(
        [below_amsl, below_plus_0_2_m],
        P023_WATER_LEVEL_BANDS[:2],
        default=P023_WATER_LEVEL_BANDS[2],
    )
    result[P023_AMSL_FILTER_COLUMN] = ~below_amsl
    result[P023_AMSL_PLUS_0_2_M_FILTER_COLUMN] = ~below_plus_0_2_m
    return result


def validate_metadata_shortlist(
        shortlist, required_core_sector_ids, target_count,
        required_mission_counts):
    """Validate an already proposed shortlist without selecting scenes.

    Every row represents one source scene and must cover every required core
    sector. ``required_mission_counts`` gives the exact expected count for
    each Landsat mission. The function returns a compact validation summary
    and raises ``ValueError`` for an invalid shortlist.
    """
    required_columns = {
        'source_scene_id',
        'sensor',
        'primary_geometry_eligible',
        'covered_sector_ids',
    }
    missing = required_columns.difference(shortlist.columns)
    if missing:
        raise ValueError(f'missing shortlist columns: {sorted(missing)}')

    if not isinstance(target_count, int) or isinstance(target_count, bool):
        raise ValueError('target_count must be a positive integer')
    if target_count <= 0:
        raise ValueError('target_count must be a positive integer')

    required_sectors = {
        str(value).strip() for value in required_core_sector_ids
        if str(value).strip()
    }
    if not required_sectors:
        raise ValueError('required_core_sector_ids must not be empty')

    mission_counts = dict(required_mission_counts)
    if not mission_counts:
        raise ValueError('required_mission_counts must not be empty')
    if any(
            not isinstance(count, int) or isinstance(count, bool) or count <= 0
            for count in mission_counts.values()):
        raise ValueError('required mission counts must be positive integers')
    if sum(mission_counts.values()) != target_count:
        raise ValueError('required mission counts must sum to target_count')

    if len(shortlist) != target_count:
        raise ValueError(
            f'expected {target_count} shortlist rows, found {len(shortlist)}'
        )

    scene_ids = shortlist['source_scene_id'].fillna('').astype(str).str.strip()
    if scene_ids.eq('').any():
        raise ValueError('source_scene_id must not be missing or blank')
    if scene_ids.duplicated().any():
        duplicates = sorted(scene_ids.loc[scene_ids.duplicated()].unique())
        raise ValueError(f'duplicate source_scene_id values: {duplicates}')

    eligibility = shortlist['primary_geometry_eligible']
    eligible = eligibility.notna() & eligibility.eq(True)
    if not eligible.all():
        rejected = scene_ids.loc[~eligible].tolist()
        raise ValueError(
            f'all shortlisted scenes must be geometry eligible: {rejected}'
        )

    missing_coverage = []
    for scene_id, covered in zip(
            scene_ids, shortlist['covered_sector_ids'], strict=True):
        missing_sectors = required_sectors.difference(_pipe_values(covered))
        if missing_sectors:
            missing_coverage.append((scene_id, sorted(missing_sectors)))
    if missing_coverage:
        raise ValueError(
            'shortlisted scenes do not cover every required core sector: '
            f'{missing_coverage[:5]}'
        )

    actual_mission_counts = shortlist['sensor'].value_counts().to_dict()
    if actual_mission_counts != mission_counts:
        raise ValueError(
            'mission counts do not match the required representation: '
            f'expected {mission_counts}, found {actual_mission_counts}'
        )

    return {
        'scene_count': len(shortlist),
        'mission_counts': actual_mission_counts,
        'required_core_sector_ids': sorted(required_sectors),
    }


def select_candidate_pool(scenes, per_stratum=1, seed=20260806):
    """Sample eligible Landsat scenes across ROI, mission, decade and season.

    This is a scene-metadata candidate pool, not the final pilot. Water level
    is scene-specific; defence and morphology belong to local pilot sectors
    and are attached only after sector selection.
    """
    required = {
        'stream', 'roi_id', 'sensor', 'source_scene_id',
        'acquisition_time_utc', 'decade', 'season',
        'primary_geometry_eligible',
    }
    missing = required.difference(scenes.columns)
    if missing:
        raise ValueError(f'missing scene columns: {sorted(missing)}')
    if per_stratum <= 0:
        raise ValueError('per_stratum must be positive')
    if set(scenes['stream'].dropna().unique()) - {'landsat'}:
        raise ValueError('the primary pilot candidate pool must use Landsat only')

    eligible = scenes[scenes['primary_geometry_eligible']].copy()
    if eligible.empty:
        raise ValueError('no scenes pass the primary geometric-RMSE rule')

    rng = np.random.default_rng(seed)
    selected = []
    strata = ['roi_id', 'sensor', 'decade', 'season']
    for values, group in eligible.groupby(strata, sort=True):
        size = min(per_stratum, len(group))
        positions = rng.choice(len(group), size=size, replace=False)
        sample = group.iloc[np.sort(positions)].copy()
        sample['selection_stratum'] = '|'.join(str(value) for value in values)
        selected.append(sample)

    candidates = pd.concat(selected, ignore_index=True)
    candidates['pilot_status'] = SCENE_CANDIDATE_POOL_STATUS
    candidates['selection_seed'] = seed
    for column in PENDING_SCENE_LABEL_COLUMNS:
        candidates[column] = ''

    return candidates.sort_values([
        'roi_id', 'sensor', 'acquisition_time_utc', 'source_scene_id'
    ]).reset_index(drop=True)
