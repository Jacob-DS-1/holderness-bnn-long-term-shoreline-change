#!/usr/bin/env python
"""Check that one of the two project environments can import its core stack."""

import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path


ANALYSIS_IMPORTS = (
    'astropy',
    'copernicusmarine',
    'ee',
    'geopandas',
    'holderness',
    'numpy',
    'pandas',
    'pyfes',
    'pyproj',
    'pyTMD',
    'rasterio',
    'rioxarray',
    'scipy',
    'skimage',
    'sklearn',
    'statsmodels',
    'torch',
    'xarray',
)

COASTSAT_IMPORTS = (
    'holderness',
    'PIL',
    'coastsat.SDS_download',
    'coastsat.SDS_preprocess',
    'coastsat.SDS_shoreline',
    'coastsat.SDS_tools',
    'coastsat.SDS_transects',
)


def import_all(module_names):
    for name in module_names:
        importlib.import_module(name)


def check_coastsat_revision(coastsat_dir):
    revision_file = Path(__file__).resolve().parents[1] / 'COASTSAT_REVISION'
    revision = json.loads(revision_file.read_text())['commit']
    actual = subprocess.run(
        ['git', '-C', str(coastsat_dir), 'rev-parse', 'HEAD'],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual != revision:
        raise RuntimeError(f'CoastSat is at {actual}; expected {revision}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('environment', choices=('analysis', 'coastsat'))
    parser.add_argument(
        '--coastsat-dir',
        type=Path,
        default=Path(__file__).resolve().parents[2] / 'CoastSat',
    )
    args = parser.parse_args()

    if args.environment == 'analysis':
        import_all(ANALYSIS_IMPORTS)
    else:
        check_coastsat_revision(args.coastsat_dir)
        sys.path.insert(0, str(args.coastsat_dir))
        import_all(COASTSAT_IMPORTS)

    print(f'{args.environment} environment imports passed')


if __name__ == '__main__':
    main()
