"""Build the provisional OS geometry seed used for availability ROIs."""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from holderness import config, geometry


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=config.GEOMETRY_DATA)
    args = parser.parse_args()

    boundaries, counts = geometry.load_os_tidal_boundaries(
        config.OS_TIDAL_BOUNDARY_PATH,
        config.OS_TIDAL_BOUNDARY_LAYER,
        config.EPSG,
    )
    lines = {
        name: geometry.build_boundary_line(
            frame, config.OS_ANCHOR_SOUTH, config.OS_ANCHOR_NORTH
        )
        for name, frame in boundaries.items()
    }
    seed, chainages, widths = geometry.build_os_seed(
        lines['mhw'], lines['mlw'], config.OS_SEED_STEP_M
    )
    source_sha256 = sha256(config.OS_TIDAL_BOUNDARY_PATH)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    seed_path = output_dir / 'os-geometry-seed.geojson'
    width_path = output_dir / 'os-intertidal-widths.csv'
    summary_path = output_dir / 'os-geometry-seed-summary.json'

    seed_frame = geometry.seed_geodataframe(seed, config.EPSG, config.SITE)
    seed_frame['source_sha256'] = source_sha256
    seed_frame['source_date_status'] = 'not_supplied_by_os_openmap_local'
    geometry.write_geojson(seed_frame, seed_path)
    pd.DataFrame({
        'chainage_m': chainages,
        'intertidal_width_m': widths,
    }).to_csv(width_path, index=False)
    summary_path.write_text(json.dumps({
        'role': 'provisional_geometry_seed',
        'source': config.OS_TIDAL_BOUNDARY_PATH.name,
        'source_sha256': source_sha256,
        'source_date_status': 'not_supplied_by_os_openmap_local',
        'epsg': config.EPSG,
        'feature_counts': counts,
        'length_m': round(seed.length, 1),
        'median_intertidal_width_m': round(float(pd.Series(widths).median()), 1),
    }, indent=2) + '\n')

    print(f'wrote {seed_path}')
    print(f'wrote {width_path}')
    print(f'wrote {summary_path}')


if __name__ == '__main__':
    main()
