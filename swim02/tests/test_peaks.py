# -*- coding: utf-8 -*-
"""The NumPy peak finder must behave like scipy.signal.find_peaks.

SciPy is no longer a runtime dependency (it costs ~140 MB in the venv and
~50 MB in a packaged build) but the strokes / stroke-rate estimates were tuned
against it, so the replacement is cross-checked here whenever SciPy happens to
be available in the development environment.
"""
from __future__ import annotations

import numpy as np
import pytest

import swim_ai as S

scipy_signal = pytest.importorskip("scipy.signal")


def _signals():
    rng = np.random.default_rng(3)
    t = np.linspace(0, 6, 360)
    yield "sine", np.sin(2 * np.pi * t)
    yield "sine+noise", np.sin(2 * np.pi * t) + 0.1 * rng.normal(size=t.size)
    yield "two-tones", (np.sin(2 * np.pi * 1.3 * t)
                        + 0.4 * np.sin(2 * np.pi * 4.1 * t))
    yield "random-walk", np.cumsum(rng.normal(size=t.size)) * 0.1
    yield "plateau", np.repeat([0, 1, 2, 2, 1, 0, 3, 3, 0], 20).astype(float)


@pytest.mark.parametrize("name,sig", list(_signals()))
def test_matches_scipy_without_arguments(name, sig):
    ours, _ = S.find_peaks(sig)
    theirs, _ = scipy_signal.find_peaks(sig)
    assert np.array_equal(ours, theirs), name


@pytest.mark.parametrize("name,sig", list(_signals()))
def test_matches_scipy_with_distance_and_prominence(name, sig):
    span = float(np.ptp(sig)) or 1.0
    for dist, prom in ((15, 0.2 * span), (40, 0.05 * span), (7, 0.6 * span)):
        ours, _ = S.find_peaks(sig, distance=dist, prominence=prom)
        theirs, _ = scipy_signal.find_peaks(sig, distance=dist, prominence=prom)
        assert np.array_equal(ours, theirs), (name, dist, prom)


def test_short_and_empty_inputs():
    assert S.find_peaks(np.array([]))[0].size == 0
    assert S.find_peaks(np.array([1.0, 2.0]))[0].size == 0
    assert np.array_equal(S.find_peaks(np.array([0.0, 1.0, 0.0]))[0], [1])


def test_distance_is_respected():
    x = np.zeros(50)
    for i in (5, 10, 30):
        x[i] = 1.0
    x[10] = 2.0                       # the tallest wins inside the window
    peaks, _ = S.find_peaks(x, distance=20)
    assert list(peaks) == [10, 30]


def test_prominence_filters_ripples():
    t = np.linspace(0, 4, 200)
    sig = np.sin(2 * np.pi * t) + 0.05 * np.sin(2 * np.pi * 12 * t)
    loose, _ = S.find_peaks(sig, prominence=0.01)
    tight, _ = S.find_peaks(sig, prominence=0.5)
    assert len(tight) < len(loose)
    assert len(tight) >= 3


def test_engine_imports_without_scipy(monkeypatch):
    """swim_ai must not import scipy any more (the module is loaded already,
    so inspect the source instead of reloading it)."""
    import inspect

    src = inspect.getsource(S)
    code = [line.strip() for line in src.splitlines()
            if not line.lstrip().startswith("#")]
    assert not any(line.startswith(("import scipy", "from scipy"))
                   for line in code)

