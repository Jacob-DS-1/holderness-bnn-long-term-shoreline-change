"""Query scene availability for one imagery stream without downloading images."""

import argparse
from pathlib import Path

from holderness import availability, config, geometry


def stream_settings(stream):
    if stream == 'landsat':
        return (
            config.LANDSAT_SENSORS,
            config.LANDSAT_DATES,
            config.LANDSAT_GEE_COLLECTIONS,
        )
    return (
        config.SENTINEL_SENSORS,
        config.SENTINEL_DATES,
        config.SENTINEL_GEE_COLLECTIONS,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stream', choices=('landsat', 'sentinel'), required=True)
    parser.add_argument('--gee-project')
    parser.add_argument(
        '--coastsat-dir', type=Path,
        default=Path(__file__).resolve().parents[2] / 'CoastSat',
        help='CoastSat checkout (default: sibling ../CoastSat)',
    )
    parser.add_argument(
        '--rois', type=Path,
        default=config.GEOMETRY_DATA / 'availability-rois.geojson',
    )
    parser.add_argument('--output-dir', type=Path, default=config.AVAILABILITY_DATA)
    parser.add_argument(
        '--dry-run', action='store_true',
        help='print the planned metadata queries without connecting to GEE',
    )
    args = parser.parse_args()

    rois = geometry.read_geojson(args.rois)
    sensors, dates, collections = stream_settings(args.stream)
    query_plan = availability.build_query_plan(
        rois, args.stream, sensors, dates, collections
    )

    if args.dry_run:
        print(query_plan.to_string(index=False))
        print(f'\n{len(query_plan)} metadata queries; no imagery will be downloaded')
        return

    project = config.get_gee_project(args.gee_project)
    download_module = availability.connect_to_earth_engine(
        project, args.coastsat_dir
    )
    scenes = availability.query_scene_availability(
        rois,
        stream=args.stream,
        sensors=sensors,
        dates=dates,
        collections=collections,
        download_module=download_module,
        max_geometric_rmse=config.LANDSAT_MAX_GEOMETRIC_RMSE_M,
    )
    paths = availability.write_availability_manifests(
        scenes, args.output_dir, args.stream
    )

    print(f'{len(scenes)} ROI-scene records')
    for path in paths:
        print(f'wrote {path}')


if __name__ == '__main__':
    main()
