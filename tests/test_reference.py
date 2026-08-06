"""Regression tests for the reference shoreline pipeline.

These pin the geometry produced from data/raw/TA.gml to a known-good run
(August 2026, geopandas 1.1.3 / shapely 2.1.2 / numpy 2.4.6). They exist to
catch a library upgrade silently altering the reference shorelines that every
downstream result depends on - not to check that the code is correct in the
abstract.

If one fails after upgrading a dependency, do not simply update the expected
value. Plot the affected line first and establish what changed and whether the
new geometry is better or worse.

The GML is gitignored, so these skip on a fresh clone until it is downloaded.
"""

import numpy as np
import pytest

from holderness import config, reference


pytestmark = pytest.mark.skipif(
    not config.GML_PATH.exists(),
    reason=f'source GML not present at {config.GML_PATH}',
)


# --- fixtures: the GML is ~218 MB, so parse it once per session --------------

@pytest.fixture(scope='session')
def gdfs():
    return reference.load_tidal_boundary(config.GML_PATH, config.LAYER, config.EPSG)


@pytest.fixture(scope='session')
def lines(gdfs):
    gdf_mhw, gdf_mlw, _ = gdfs
    out = {}
    for name, g in [('mhw', gdf_mhw), ('mlw', gdf_mlw)]:
        _, out[name] = reference.build_reference_lines(
            g, config.ANCHOR_SOUTH, config.ANCHOR_NORTH
        )
    return out


@pytest.fixture(scope='session')
def profile(lines):
    return reference.separation_profile(lines['mhw'], lines['mlw'], config.SAMPLE_STEP)


# --- source data -------------------------------------------------------------

def test_feature_counts(gdfs):
    _, _, counts = gdfs
    assert counts['mhw']['n_in'] == 351
    assert counts['mlw']['n_in'] == 216


def test_no_geometries_dropped(gdfs):
    """The OS extract is clean; anything dropped means the source changed."""
    _, _, counts = gdfs
    for name, c in counts.items():
        assert c['n_in'] == c['n_out'], f'{name}: {c}'


# --- trimmed lines -----------------------------------------------------------

@pytest.mark.parametrize('name,expected', [('mhw', 60207), ('mlw', 61532)])
def test_trimmed_length(lines, name, expected):
    assert lines[name].length == pytest.approx(expected, rel=config.EXPECT_TOL)


def test_lines_are_single_linestrings(lines):
    for name, line in lines.items():
        assert line.geom_type == 'LineString', f'{name} is {line.geom_type}'


def test_lines_run_south_to_north(lines):
    for name, line in lines.items():
        assert line.coords[0][1] < line.coords[-1][1], f'{name} runs the wrong way'


def test_mlw_is_seaward_of_mhw(lines):
    """On this coast seaward is east, so MLW easting should exceed MHW easting."""
    mhw = np.array(lines['mhw'].coords)
    sampled = [lines['mhw'].interpolate(d) for d in np.linspace(0, lines['mhw'].length, 200)]
    paired = [lines['mlw'].interpolate(lines['mlw'].project(p)) for p in sampled]
    east_of = sum(q.x > p.x for p, q in zip(sampled, paired))
    assert east_of / len(sampled) > 0.95, f'only {east_of}/{len(sampled)} samples east'
    assert mhw.shape[1] == 2


# --- hairpins ----------------------------------------------------------------

@pytest.mark.parametrize('name,expected', [('mhw', 6), ('mlw', 8)])
def test_hairpin_count(lines, name, expected):
    assert len(reference.hairpin_locations(lines[name])) == expected


def test_hairpin_locations_stable(lines):
    """First MHW hairpin sits near the outfall at ~23.1 km from Kilnsea."""
    first = reference.hairpin_locations(lines['mhw'])[0]
    assert first[0] == pytest.approx(23060, abs=50)


# --- separation --------------------------------------------------------------

def test_separation_statistics(profile):
    _, _, sep = profile
    assert np.median(sep) == pytest.approx(113, abs=2)
    assert np.percentile(sep, 5) == pytest.approx(57, abs=2)
    assert np.percentile(sep, 95) == pytest.approx(207, abs=3)
    assert sep.max() == pytest.approx(241, abs=3)


def test_separation_never_negative(profile):
    _, _, sep = profile
    assert (sep >= 0).all()


# --- midline -----------------------------------------------------------------

def test_midline_sits_halfway(lines, profile):
    _, pts_mhw, _ = profile
    _, ratio = reference.build_midline(pts_mhw, lines['mlw'])
    assert np.nanmedian(ratio) == pytest.approx(1.0, abs=1e-3)
    assert np.nanpercentile(ratio, 95) == pytest.approx(1.0, abs=1e-2)


def test_midline_length_between_inputs(lines, profile):
    _, pts_mhw, _ = profile
    midline, _ = reference.build_midline(pts_mhw, lines['mlw'])
    assert midline.length == pytest.approx(59775, rel=config.EXPECT_TOL)


# --- densify -----------------------------------------------------------------

def test_densify_spacing_within_target(lines):
    arr = reference.densify(lines['mhw'], config.DENSIFY_STEP)
    spacing = np.linalg.norm(np.diff(arr, axis=0), axis=1)
    assert spacing.max() <= config.DENSIFY_STEP + 1e-6
    assert len(arr) == 4015


def test_densify_endpoints_preserved(lines):
    arr = reference.densify(lines['mhw'], config.DENSIFY_STEP)
    assert arr[0] == pytest.approx(lines['mhw'].coords[0], abs=0.01)
    assert arr[-1] == pytest.approx(lines['mhw'].coords[-1], abs=0.01)


# --- persistence -------------------------------------------------------------

def test_save_load_roundtrip(tmp_path):
    arr = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    fn = tmp_path / 'nested' / 'refsl.pkl'
    reference.save_reference(arr, fn)
    assert np.array_equal(reference.load_reference(fn), arr)


def test_save_rejects_wrong_shape(tmp_path):
    with pytest.raises(ValueError):
        reference.save_reference(np.arange(10), tmp_path / 'bad.pkl')


# --- guards ------------------------------------------------------------------

def test_separation_rejects_bad_step(lines):
    with pytest.raises(ValueError):
        reference.separation_profile(lines['mhw'], lines['mlw'], 0)


def test_build_rejects_short_component(gdfs):
    gdf_mhw, _, _ = gdfs
    with pytest.raises(ValueError, match='longest component'):
        reference.build_reference_lines(
            gdf_mhw, config.ANCHOR_SOUTH, config.ANCHOR_NORTH, min_length=10**9
        )
