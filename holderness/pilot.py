"""Prepare a blinded pilot candidate pool from the availability manifest."""

import numpy as np
import pandas as pd


PENDING_LABEL_COLUMNS = (
    'water_level_band',
    'defence_status',
    'coastal_regime',
    'morphology_notes',
)


def select_candidate_pool(scenes, per_stratum=1, seed=20260806):
    """Sample eligible Landsat scenes across ROI, mission, decade and season.

    This is a candidate pool, not the final pilot. Water level, defence and
    morphology labels must be completed before final pilot scenes are frozen.
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
    candidates['pilot_status'] = 'candidate_pending_labels'
    candidates['selection_seed'] = seed
    for column in PENDING_LABEL_COLUMNS:
        candidates[column] = ''

    return candidates.sort_values([
        'roi_id', 'sensor', 'acquisition_time_utc', 'source_scene_id'
    ]).reset_index(drop=True)
