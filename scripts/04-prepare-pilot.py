"""Prepare an editable Landsat pilot candidate pool from scene availability."""

import argparse
import json
from pathlib import Path

import pandas as pd

from holderness import config, pilot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--scenes', type=Path,
        default=config.AVAILABILITY_DATA / 'landsat-scene-availability.csv',
    )
    parser.add_argument('--output-dir', type=Path, default=config.PILOT_DATA)
    parser.add_argument('--per-stratum', type=int, default=1)
    parser.add_argument('--seed', type=int, default=config.PILOT_CANDIDATE_SEED)
    parser.add_argument(
        '--dry-run', action='store_true',
        help='summarise the candidate pool without writing files',
    )
    args = parser.parse_args()

    scenes = pd.read_csv(args.scenes)
    candidates = pilot.select_candidate_pool(
        scenes, per_stratum=args.per_stratum, seed=args.seed
    )

    print(candidates.groupby(['sensor', 'decade', 'season']).size().to_string())
    print(f'\n{len(candidates)} preliminary scene candidates')
    print('water-level labelling and local-sector selection are still required')
    if args.dry_run:
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = args.output_dir / 'pilot-candidate-pool.csv'
    summary_path = args.output_dir / 'pilot-candidate-summary.json'
    candidates.to_csv(candidate_path, index=False)
    summary_path.write_text(json.dumps({
        'status': pilot.SCENE_CANDIDATE_POOL_STATUS,
        'selection_seed': args.seed,
        'per_stratum': args.per_stratum,
        'candidate_count': len(candidates),
        'selection_strata': ['roi_id', 'sensor', 'decade', 'season'],
        'pending_scene_labels': list(pilot.PENDING_SCENE_LABEL_COLUMNS),
        'pending_pilot_steps': list(pilot.PENDING_PILOT_STEPS),
        'spatial_context_unit': 'local_sector_not_roi',
    }, indent=2) + '\n')

    print(f'wrote {candidate_path}')
    print(f'wrote {summary_path}')


if __name__ == '__main__':
    main()
