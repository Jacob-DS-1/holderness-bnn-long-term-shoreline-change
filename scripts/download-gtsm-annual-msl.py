#!/usr/bin/env python
"""Download the two fixed GTSM annual mean-sea-level archives."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pandas as pd

from holderness import config, gtsm


PLAN_FILENAME = 'gtsm-annual-msl-retrieval-plan.json'
DOWNLOAD_MANIFEST_FILENAME = 'gtsm-annual-msl-download-manifest.csv'
LOCK_FILENAME = '.gtsm-annual-msl-download.lock'


def plan_document(plan):
    """Return the frozen scientific and retrieval provenance document."""
    return {
        'schema_version': 1,
        'status': 'approved_for_retrieval',
        'decision_date': '2026-08-07',
        'dataset_id': gtsm.DATASET_ID,
        'model_version': gtsm.ANNUAL_MSL_MODEL_VERSION,
        'cds_experiment_version': gtsm.ANNUAL_MSL_CDS_VERSION,
        'version_scope': (
            'GTSM v3.0 is the hydrodynamic model; v1 is the CDS '
            'historical/future experiment-file version'
        ),
        'variable': gtsm.ANNUAL_MSL_VARIABLE,
        'temporal_aggregation': gtsm.ANNUAL_MSL_TEMPORAL_AGGREGATION,
        'study_years': '1990-2024',
        'source_reference_period': (
            gtsm.ANNUAL_MSL_SOURCE_REFERENCE_PERIOD
        ),
        'target_reference_period': (
            gtsm.ANNUAL_MSL_TARGET_REFERENCE_PERIOD
        ),
        'target_transformation': (
            'recenter each selected-station annual series to its '
            '1991-2020 mean after retrieval; preserve the raw '
            '1986-2005-referenced values'
        ),
        'post_2015_limitation': (
            'the supplied annual sea-level-rise fields after 2015 are '
            'projection-based rather than observed annual mean sea level'
        ),
        'retrieval_plan_sha256': gtsm.annual_msl_plan_sha256(plan),
        'archives': plan,
    }


def write_once_or_verify(path, contents):
    """Create frozen plan text once or require an exact later match."""
    if path.exists():
        if path.read_text() != contents:
            raise ValueError(f'frozen annual-MSL plan changed: {path}')
        print(f'verified {path}')
        return
    path.write_text(contents)
    print(f'wrote {path}')


@contextmanager
def download_lock(output_dir):
    """Prevent concurrent annual-MSL publication in the output directory."""
    lock_path = output_dir / LOCK_FILENAME
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RuntimeError(
            f'annual-MSL retrieval lock already exists: {lock_path}'
        ) from error
    with os.fdopen(descriptor, 'w') as lock:
        lock.write(f'pid={os.getpid()}\n')
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def inspect_archive_state(target, partial, experiment):
    """Return the safe action for one final/partial archive pair."""
    if target.exists() and partial.exists():
        raise FileExistsError(
            f'both final and partial annual-MSL archives exist: '
            f'{target}, {partial}'
        )
    if target.exists():
        gtsm.validate_annual_msl_archive(target, experiment)
        return 'existing_valid'
    if partial.exists():
        gtsm.validate_annual_msl_archive(partial, experiment)
        return 'promote_valid_partial'
    return 'download'


def load_prior_records(path, plan):
    """Load and validate the recoverable two-row download ledger."""
    if not path.exists():
        return {}

    records = pd.read_csv(path).to_dict('records')
    required = {
        'experiment', 'start_year', 'end_year', 'archive_filename', 'sha256',
    }
    expected = {item['experiment']: item for item in plan}
    records_by_experiment = {}
    for record in records:
        missing = required.difference(record)
        if missing:
            raise ValueError(
                f'annual-MSL manifest is missing columns: {sorted(missing)}'
            )
        experiment = str(record['experiment'])
        if experiment not in expected:
            raise ValueError(
                f'annual-MSL manifest has an unexpected experiment: '
                f'{experiment}'
            )
        if experiment in records_by_experiment:
            raise ValueError(
                f'annual-MSL manifest duplicates experiment: {experiment}'
            )
        specification = expected[experiment]
        identity = (
            int(record['start_year']),
            int(record['end_year']),
            str(record['archive_filename']),
        )
        expected_identity = (
            specification['start_year'],
            specification['end_year'],
            specification['archive_filename'],
        )
        if identity != expected_identity:
            raise ValueError(
                f'annual-MSL manifest identity changed for {experiment}'
            )
        records_by_experiment[experiment] = record
    return records_by_experiment


def write_download_manifest(records_by_experiment, path, plan):
    """Atomically update the recoverable annual-MSL download ledger."""
    order = {item['experiment']: position for position, item in enumerate(plan)}
    records = sorted(
        records_by_experiment.values(),
        key=lambda record: order[record['experiment']],
    )
    temporary = path.with_suffix(path.suffix + '.tmp')
    pd.DataFrame(records).to_csv(temporary, index=False)
    temporary.replace(path)


def cds_client():
    """Create the CDS client only when a live request is required."""
    import cdsapi

    return cdsapi.Client(
        quiet=True,
        progress=False,
        retry_max=10,
        sleep_max=60,
        timeout=120,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--manifest-dir', type=Path, default=config.PILOT_DATA,
    )
    parser.add_argument(
        '--output-dir', type=Path, required=True,
        help='existing directory on a mounted device outside the repository',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='validate and print both fixed requests without writing or connecting',
    )
    args = parser.parse_args()

    plan = gtsm.annual_msl_retrieval_plan()
    output_dir = gtsm.require_external_output_directory(
        args.output_dir, config.REPO_ROOT
    )

    for specification in plan:
        experiment = specification['experiment']
        target = output_dir / specification['archive_filename']
        partial = target.with_suffix(target.suffix + '.partial')
        action = inspect_archive_state(target, partial, experiment)
        print(json.dumps({
            'experiment': experiment,
            'years': (
                f'{specification["start_year"]:04d}-'
                f'{specification["end_year"]:04d}'
            ),
            'target': str(target),
            'action': action,
            'request': specification['request'],
        }, sort_keys=True))

    print(
        'annual-MSL request: 2 archives, 35 unique years, '
        f'plan sha256 {gtsm.annual_msl_plan_sha256(plan)}'
    )
    if args.dry_run:
        return

    manifest_dir = args.manifest_dir.expanduser().resolve()
    manifest_dir.mkdir(parents=True, exist_ok=True)
    plan_path = manifest_dir / PLAN_FILENAME
    plan_contents = json.dumps(plan_document(plan), indent=2) + '\n'
    write_once_or_verify(plan_path, plan_contents)

    download_manifest = manifest_dir / DOWNLOAD_MANIFEST_FILENAME
    records_by_experiment = load_prior_records(download_manifest, plan)
    client = None

    with download_lock(output_dir):
        for number, specification in enumerate(plan, start=1):
            experiment = specification['experiment']
            target = output_dir / specification['archive_filename']
            partial = target.with_suffix(target.suffix + '.partial')
            action = inspect_archive_state(target, partial, experiment)

            if action == 'promote_valid_partial':
                print(
                    f'[{number}/2] promoting validated {partial.name}',
                    flush=True,
                )
                gtsm.publish_without_overwrite(partial, target)
                status = 'promoted_valid_partial'
            elif action == 'download':
                print(f'[{number}/2] downloading {target.name}', flush=True)
                if client is None:
                    client = cds_client()
                client.retrieve(
                    gtsm.DATASET_ID,
                    specification['request'],
                    str(partial),
                )
                gtsm.validate_annual_msl_archive(partial, experiment)
                gtsm.publish_without_overwrite(partial, target)
                status = 'downloaded'
            else:
                print(
                    f'[{number}/2] validating existing {target.name}',
                    flush=True,
                )
                status = 'existing_valid'

            validation = gtsm.validate_annual_msl_archive(
                target, experiment
            )
            checksum = gtsm.sha256_file(target)
            if experiment in records_by_experiment:
                prior = records_by_experiment[experiment]
                if str(prior['sha256']) != checksum:
                    raise ValueError(
                        f'annual-MSL archive checksum changed: {target.name}'
                    )
            else:
                records_by_experiment[experiment] = {
                    'dataset_id': gtsm.DATASET_ID,
                    'model_version': gtsm.ANNUAL_MSL_MODEL_VERSION,
                    'cds_experiment_version': gtsm.ANNUAL_MSL_CDS_VERSION,
                    'variable': gtsm.ANNUAL_MSL_VARIABLE,
                    'temporal_aggregation': (
                        gtsm.ANNUAL_MSL_TEMPORAL_AGGREGATION
                    ),
                    'experiment': experiment,
                    'start_year': specification['start_year'],
                    'end_year': specification['end_year'],
                    'year_count': specification['year_count'],
                    'source_reference_period': (
                        gtsm.ANNUAL_MSL_SOURCE_REFERENCE_PERIOD
                    ),
                    'target_reference_period': (
                        gtsm.ANNUAL_MSL_TARGET_REFERENCE_PERIOD
                    ),
                    'status': status,
                    **validation,
                    'sha256': checksum,
                    'retrieval_plan_sha256': (
                        gtsm.annual_msl_plan_sha256(plan)
                    ),
                    'validated_at_utc': datetime.now(
                        timezone.utc
                    ).isoformat(),
                }
            write_download_manifest(
                records_by_experiment, download_manifest, plan
            )
            print(
                f'[{number}/2] passed '
                f'({validation["archive_bytes"] / 1024 ** 2:.1f} MiB)',
                flush=True,
            )

    print(f'wrote {download_manifest}')
    print('GTSM annual mean-sea-level retrieval passed')


if __name__ == '__main__':
    main()
