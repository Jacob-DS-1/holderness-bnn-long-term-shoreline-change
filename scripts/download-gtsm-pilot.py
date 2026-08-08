#!/usr/bin/env python
"""Download the frozen pilot months from GTSM v3 to local raw storage."""

import argparse
import atexit
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pandas as pd

from holderness import config, gtsm, pilot


EXPECTED_SCENE_COUNT = 110
EXPECTED_MONTH_COUNT = 94
EXPECTED_POOL_SHA256 = (
    '0e27aee5f5570349d454b1422b5fd7e2492f1e119b658db9825dc22b8d483ad9'
)
EXPECTED_MONTH_PLAN_SHA256 = (
    'eb4a007f170ef5f572c214463092efff75883cf42f1eb44b34a5165563acc7fd'
)


def build_frozen_pool(scenes_path, candidate_pool_path, sectors_path):
    """Reproduce the approved water-blind evaluation pool and its months."""
    scenes = pd.read_csv(scenes_path)
    candidates = pd.read_csv(candidate_pool_path)
    sectors = pd.read_csv(sectors_path)

    catalog = pilot.collapse_scene_coverage(scenes)
    catalog = pilot.add_sector_coverage(catalog, sectors)
    evaluation_pool = gtsm.select_water_level_evaluation_pool(
        catalog, candidates['source_scene_id']
    )
    months = gtsm.retrieval_months(evaluation_pool)

    if len(evaluation_pool) != EXPECTED_SCENE_COUNT:
        raise ValueError(
            f'expected {EXPECTED_SCENE_COUNT} frozen scenes, '
            f'found {len(evaluation_pool)}'
        )
    if len(months) != EXPECTED_MONTH_COUNT:
        raise ValueError(
            f'expected {EXPECTED_MONTH_COUNT} frozen months, '
            f'found {len(months)}'
        )
    pool_digest = gtsm.evaluation_pool_sha256(evaluation_pool)
    month_digest = gtsm.month_plan_sha256(months)
    if pool_digest != EXPECTED_POOL_SHA256:
        raise ValueError(
            'frozen scene identities or acquisition times changed: '
            f'{pool_digest}'
        )
    if month_digest != EXPECTED_MONTH_PLAN_SHA256:
        raise ValueError(f'frozen month plan changed: {month_digest}')
    return evaluation_pool, months


def write_once_or_verify(path, contents):
    """Create frozen manifest text once or require an exact later match."""
    if path.exists():
        if path.read_text() != contents:
            raise ValueError(f'frozen manifest changed: {path}')
        print(f'verified {path}')
        return
    path.write_text(contents)
    print(f'wrote {path}')


def write_design_manifests(evaluation_pool, months, manifest_dir):
    """Write the frozen scene/month evidence before network retrieval."""
    manifest_dir.mkdir(parents=True, exist_ok=True)
    scenes_path = manifest_dir / 'pilot-water-level-evaluation-scenes.csv'
    months_path = manifest_dir / 'gtsm-pilot-retrieval-months.csv'
    summary_path = manifest_dir / 'gtsm-pilot-retrieval-summary.json'

    write_once_or_verify(scenes_path, evaluation_pool.to_csv(index=False))
    write_once_or_verify(months_path, months.to_csv(index=False))
    summary_contents = json.dumps({
        'schema_version': 1,
        'status': 'approved_for_retrieval',
        'decision_date': '2026-08-07',
        'selection_basis': (
            'existing seeded candidate pool intersected with primary '
            'geometry eligibility and complete core-sector coverage before '
            'water levels were inspected'
        ),
        'scene_count': len(evaluation_pool),
        'month_count': len(months),
        'dataset_id': gtsm.DATASET_ID,
        'experiment': gtsm.EXPERIMENT,
        'variable': gtsm.VARIABLE,
        'temporal_aggregation': gtsm.TEMPORAL_AGGREGATION,
        'version': gtsm.VERSION,
        'scene_time_method': (
            'linear interpolation only when both surrounding 10-minute '
            'values are finite'
        ),
        'missing_data_rule': (
            'exclude a pilot scene when either surrounding 10-minute value '
            'is missing at any required sector station; do not fill, change '
            'station or substitute hourly data'
        ),
    }, indent=2) + '\n'
    write_once_or_verify(summary_path, summary_contents)


def require_external_output_directory(output_dir):
    """Require an existing directory on a device outside the repository."""
    output_dir = output_dir.expanduser().resolve(strict=True)
    if not output_dir.is_dir():
        raise ValueError(f'GTSM output path is not a directory: {output_dir}')
    repo_root = config.REPO_ROOT.resolve()
    if output_dir == repo_root or repo_root in output_dir.parents:
        raise ValueError('GTSM output directory must be outside the repository')
    if output_dir.stat().st_dev == repo_root.stat().st_dev:
        raise ValueError(
            'GTSM output directory must be on a different mounted device'
        )
    return output_dir


def acquire_download_lock(output_dir):
    """Prevent two retrieval processes from publishing the same archives."""
    lock_path = output_dir / '.gtsm-pilot-download.lock'
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RuntimeError(
            f'GTSM retrieval lock already exists: {lock_path}'
        ) from error
    with os.fdopen(descriptor, 'w') as lock:
        lock.write(f'pid={os.getpid()}\n')
    atexit.register(lock_path.unlink, missing_ok=True)


def write_download_manifest(records, path):
    """Atomically update the recoverable raw-download ledger."""
    ordered = pd.DataFrame(records).sort_values(['year', 'month'])
    temporary = path.with_suffix(path.suffix + '.tmp')
    ordered.to_csv(temporary, index=False)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--scenes', type=Path,
        default=config.AVAILABILITY_DATA / 'landsat-scene-availability.csv',
    )
    parser.add_argument(
        '--candidate-pool', type=Path,
        default=config.PILOT_DATA / 'pilot-candidate-pool.csv',
    )
    parser.add_argument(
        '--sectors', type=Path,
        default=config.DATA_INTERIM / 'pilot' / 'pilot-sector-candidates.csv',
    )
    parser.add_argument(
        '--manifest-dir', type=Path, default=config.PILOT_DATA,
    )
    parser.add_argument(
        '--output-dir', type=Path, required=True,
        help='machine-local raw-data directory, preferably on a large volume',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='validate and print the frozen request without writing or downloading',
    )
    args = parser.parse_args()

    evaluation_pool, months = build_frozen_pool(
        args.scenes, args.candidate_pool, args.sectors
    )
    output_dir = require_external_output_directory(args.output_dir)
    total_scenes = int(months['scene_count'].sum())
    print(
        f'frozen GTSM request: {len(evaluation_pool)} scenes, '
        f'{len(months)} months, {total_scenes} scene-month memberships'
    )
    print(
        f'period: {months.iloc[0].year:04d}-{months.iloc[0].month:02d} to '
        f'{months.iloc[-1].year:04d}-{months.iloc[-1].month:02d}'
    )
    if args.dry_run:
        return

    write_design_manifests(
        evaluation_pool, months, args.manifest_dir.expanduser().resolve()
    )

    import cdsapi

    acquire_download_lock(output_dir)
    client = cdsapi.Client(
        quiet=True,
        progress=False,
        retry_max=10,
        sleep_max=60,
        timeout=120,
    )
    download_manifest = (
        args.manifest_dir.expanduser().resolve()
        / 'gtsm-pilot-download-manifest.csv'
    )
    if download_manifest.exists():
        prior_records = pd.read_csv(download_manifest).to_dict('records')
    else:
        prior_records = []
    records_by_month = {
        (int(record['year']), int(record['month'])): record
        for record in prior_records
    }

    for number, row in enumerate(months.itertuples(index=False), start=1):
        year = int(row.year)
        month = int(row.month)
        target = output_dir / gtsm.archive_filename(year, month)
        partial = target.with_suffix(target.suffix + '.partial')

        if target.exists():
            print(
                f'[{number}/{len(months)}] validating existing {target.name}',
                flush=True,
            )
            status = 'existing_valid'
        else:
            if partial.exists():
                raise ValueError(
                    f'incomplete download already exists: {partial}; '
                    'inspect or remove it before resuming'
                )
            print(
                f'[{number}/{len(months)}] downloading {target.name}',
                flush=True,
            )
            client.retrieve(
                gtsm.DATASET_ID,
                gtsm.retrieval_request(year, month),
                str(partial),
            )
            gtsm.validate_archive(partial, year, month)
            if target.exists():
                raise FileExistsError(
                    f'target appeared during download; refusing overwrite: {target}'
                )
            partial.rename(target)
            status = 'downloaded'

        validation = gtsm.validate_archive(target, year, month)
        checksum = gtsm.sha256_file(target)
        key = (year, month)
        if key in records_by_month:
            prior = records_by_month[key]
            if prior['sha256'] != checksum:
                raise ValueError(
                    f'archive checksum changed since retrieval: {target.name}'
                )
        else:
            records_by_month[key] = {
                'year': year,
                'month': month,
                'status': status,
                **validation,
                'sha256': checksum,
                'validated_at_utc': datetime.now(timezone.utc).isoformat(),
            }
        write_download_manifest(
            list(records_by_month.values()), download_manifest
        )
        print(
            f'[{number}/{len(months)}] passed '
            f'({validation["archive_bytes"] / 1024 ** 2:.1f} MiB)',
            flush=True,
        )

    print(f'wrote {download_manifest}')
    print('GTSM pilot surge retrieval passed')


if __name__ == '__main__':
    main()
