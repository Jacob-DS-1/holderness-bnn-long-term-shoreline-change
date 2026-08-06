"""Build provisional overlapping ROIs for image-availability queries."""

import argparse
from pathlib import Path

from holderness import config, geometry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--seed', type=Path,
        default=config.GEOMETRY_DATA / 'os-geometry-seed.geojson',
    )
    parser.add_argument(
        '--output', type=Path,
        default=config.GEOMETRY_DATA / 'availability-rois.geojson',
    )
    args = parser.parse_args()

    seed_frame = geometry.read_geojson(args.seed)
    candidates = seed_frame[seed_frame['role'] == 'provisional_geometry_seed']
    if len(candidates) != 1:
        raise ValueError('seed file must contain one provisional geometry seed')

    rois = geometry.build_rois(
        candidates.iloc[0].geometry,
        epsg=config.EPSG,
        length=config.ROI_LENGTH_M,
        overlap=config.ROI_OVERLAP_M,
        half_width=config.INITIAL_MAX_DIST_REF_M,
        max_area=config.ROI_MAX_AREA_M2,
    )
    geometry.write_geojson(rois, args.output)

    print(f'wrote {args.output}')
    print(f'{len(rois)} provisional ROIs')
    print(f'maximum area: {rois.area_m2.max() / 1_000_000:.2f} km2')


if __name__ == '__main__':
    main()
