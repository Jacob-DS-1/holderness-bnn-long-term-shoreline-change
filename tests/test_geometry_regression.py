"""Regression checks against the local OS OpenMap Local extract."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from holderness import config, geometry


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='session')
def boundaries():
    if not config.OS_TIDAL_BOUNDARY_PATH.exists():
        pytest.skip(f'source GML not present at {config.OS_TIDAL_BOUNDARY_PATH}')
    return geometry.load_os_tidal_boundaries(
        config.OS_TIDAL_BOUNDARY_PATH,
        config.OS_TIDAL_BOUNDARY_LAYER,
        config.EPSG,
    )


@pytest.fixture(scope='session')
def boundary_lines(boundaries):
    frames, _ = boundaries
    return {
        name: geometry.build_boundary_line(
            frame, config.OS_ANCHOR_SOUTH, config.OS_ANCHOR_NORTH
        )
        for name, frame in frames.items()
    }


@pytest.fixture(scope='session')
def os_seed(boundary_lines):
    return geometry.build_os_seed(
        boundary_lines['mhw'], boundary_lines['mlw'], config.OS_SEED_STEP_M
    )


def test_source_feature_counts_and_geometry_quality(boundaries):
    _, counts = boundaries
    assert counts['mhw']['n_in'] == 351
    assert counts['mlw']['n_in'] == 216
    assert all(values['n_in'] == values['n_out'] for values in counts.values())


def test_source_checksum_matches_manifest():
    if not config.OS_TIDAL_BOUNDARY_PATH.exists():
        pytest.skip(f'source GML not present at {config.OS_TIDAL_BOUNDARY_PATH}')

    manifest = json.loads(
        (REPO_ROOT / 'docs' / 'data-licence-manifest.json').read_text()
    )
    datasets = {dataset['id']: dataset for dataset in manifest['datasets']}
    recorded = datasets['os_openmap_local_tidal_boundary']['source']['checksum']

    digest = hashlib.sha256()
    with config.OS_TIDAL_BOUNDARY_PATH.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    assert recorded == f'sha256:{digest.hexdigest()}'


@pytest.mark.parametrize('name', ['mhw', 'mlw'])
def test_boundary_length_and_orientation(boundary_lines, name):
    line = boundary_lines[name]
    assert line.length == pytest.approx(
        config.EXPECTED_OS_LENGTH_M[name], abs=2
    )
    assert line.coords[0][1] < line.coords[-1][1]


def test_low_water_line_is_seaward(boundary_lines):
    mhw = boundary_lines['mhw']
    mlw = boundary_lines['mlw']
    samples = [mhw.interpolate(distance)
               for distance in np.linspace(0, mhw.length, 200)]
    paired = [mlw.interpolate(mlw.project(point)) for point in samples]
    assert sum(low.x > high.x for high, low in zip(samples, paired)) > 190


@pytest.mark.parametrize('name,expected', [('mhw', 6), ('mlw', 8)])
def test_os_hairpin_count_is_stable(boundary_lines, name, expected):
    assert len(geometry.hairpin_ranges(boundary_lines[name])) == expected


def test_os_seed_geometry_and_intertidal_width(os_seed):
    seed, chainages, widths = os_seed
    assert seed.length == pytest.approx(
        config.EXPECTED_OS_LENGTH_M['seed'], abs=2
    )
    assert chainages[0] == 0
    assert np.median(widths) == pytest.approx(113, abs=2)
    assert np.percentile(widths, 95) == pytest.approx(207, abs=3)
    assert widths.max() == pytest.approx(241, abs=3)


def test_short_component_guard(boundaries):
    frames, _ = boundaries
    with pytest.raises(ValueError, match='longest component'):
        geometry.build_boundary_line(
            frames['mhw'], config.OS_ANCHOR_SOUTH, config.OS_ANCHOR_NORTH,
            min_component_length=10**9,
        )
