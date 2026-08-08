#!/usr/bin/env python
"""Validate the ignored local FES2022b configuration with one smoke test."""

import argparse
from pathlib import Path

import numpy as np
import pyfes
import yaml

from holderness import config, fes


EXPECTED_CONSTITUENT_COUNT = 34

# This point is 3 km seaward of the provisional Withernsea pilot-sector
# midpoint. It is used only to verify files, PyFES and interpolation; it is not
# a final water-level sampling location or an accuracy validation point.
SMOKE_LONGITUDE = 0.07399752
SMOKE_LATITUDE = 53.74599146
SMOKE_TIME_UTC = '2025-01-01T00:00:00'
SMOKE_BBOX = (0.02, 53.68, 0.13, 53.82)


def constituent_paths(config_path):
    """Return and validate the ocean and loading paths in a FES YAML file."""
    contents = yaml.safe_load(config_path.read_text())
    sections = {
        'ocean': ('tide', 'cartesian', 'paths'),
        'loading': ('radial', 'cartesian', 'paths'),
    }
    result = {}

    for component, keys in sections.items():
        value = contents
        try:
            for key in keys:
                value = value[key]
        except (KeyError, TypeError) as error:
            raise ValueError(
                f'FES configuration has no {component} constituent paths'
            ) from error

        if not isinstance(value, dict):
            raise ValueError(
                f'FES {component} constituent paths must be a mapping'
            )
        if len(value) != EXPECTED_CONSTITUENT_COUNT:
            raise ValueError(
                f'expected {EXPECTED_CONSTITUENT_COUNT} {component} '
                f'constituents, found {len(value)}'
            )

        paths = [Path(path).expanduser() for path in value.values()]
        missing = [path for path in paths if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                f'{component} constituent file is missing: {missing[0]}'
            )
        result[component] = paths

    return result


def evaluate_component(model, dates, longitudes, latitudes, name):
    """Evaluate and validate one PyFES tide component at the smoke point."""
    short_period_cm, long_period_cm, flags = pyfes.evaluate_tide(
        model, dates, longitudes, latitudes
    )
    flag = fes.require_interpolated_flag(flags[0], name)
    height_m = fes.component_height_metres(
        short_period_cm[0], long_period_cm[0]
    )
    return {
        'short_period_cm': float(short_period_cm[0]),
        'long_period_cm': float(long_period_cm[0]),
        'height_m': height_m,
        'flag': flag,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--config', type=Path,
        default=config.DATA_RAW / 'fes2022b' / 'fes2022.yaml',
        help='ignored machine-local FES2022b YAML configuration',
    )
    args = parser.parse_args()
    config_path = args.config.expanduser().resolve()

    if not config_path.is_file():
        raise FileNotFoundError(f'FES configuration not found: {config_path}')

    paths = constituent_paths(config_path)
    print(f'configuration: {config_path}')
    print(
        f'constituents: {len(paths["ocean"])} ocean + '
        f'{len(paths["loading"])} loading'
    )
    print(
        'diagnostic only: this fixed point and date are not final scientific '
        'sampling choices'
    )

    loaded = pyfes.config.load(str(config_path), bbox=SMOKE_BBOX)
    dates = np.array([np.datetime64(SMOKE_TIME_UTC)])
    longitudes = np.array([SMOKE_LONGITUDE])
    latitudes = np.array([SMOKE_LATITUDE])

    ocean = evaluate_component(
        loaded.models['tide'], dates, longitudes, latitudes, 'ocean'
    )
    loading = evaluate_component(
        loaded.models['radial'], dates, longitudes, latitudes, 'loading'
    )
    astronomical_tide_m = ocean['height_m'] + loading['height_m']

    print(
        f'smoke point: ({SMOKE_LONGITUDE:.8f}, {SMOKE_LATITUDE:.8f}) at '
        f'{SMOKE_TIME_UTC} UTC'
    )
    for name, result in (('ocean', ocean), ('loading', loading)):
        description = fes.quality_flag_description(result['flag'])
        print(
            f'{name}: short={result["short_period_cm"]:.6f} cm, '
            f'long={result["long_period_cm"]:.6f} cm, '
            f'total={result["height_m"]:.9f} m, '
            f'flag={result["flag"]} ({description})'
        )
    print(f'ocean + loading: {astronomical_tide_m:.12f} m')
    print('FES2022b local smoke check passed')


if __name__ == '__main__':
    main()
