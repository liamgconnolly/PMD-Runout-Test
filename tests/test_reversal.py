# Copyright (C) 2026 Liam G. Connolly
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify the reversal math recovers known synthetic spindle/part errors."""

import numpy as np
import pytest

from pmd_runout.reversal import (
    ReversalError,
    _remove_dc_and_fundamental,
    reversal,
)


def synth(n=36, seed=0):
    """Build r1/r2 from a known spindle error S and part form P.

    Includes DC offsets and eccentricity (1st harmonic) in each run, which
    the analysis must reject, plus higher harmonics it must recover.
    """
    theta = np.deg2rad(np.arange(n) * 360.0 / n)
    # ground truth: harmonics >= 2 only (what reversal should report)
    spindle = 0.30 * np.cos(2 * theta) + 0.10 * np.sin(5 * theta)
    part = 0.50 * np.cos(3 * theta + 0.4) + 0.05 * np.cos(7 * theta)
    # per-run nuisance: probe standoff DC + centering eccentricity
    ecc1 = 5.0 + 2.0 * np.cos(theta + 0.1)
    ecc2 = -3.0 + 1.5 * np.cos(theta - 0.7)
    r1 = part + spindle + ecc1
    r2 = part - spindle + ecc2
    return np.rad2deg(theta), r1, r2, spindle, part


def test_recovers_spindle_and_part():
    angles, r1, r2, spindle, part = synth()
    res = reversal(angles, r1, r2)
    # nuisance DC/eccentricity splits between S and P but both are
    # re-centered by the fit, so recovery should be near machine precision
    np.testing.assert_allclose(res.spindle, spindle, atol=1e-9)
    np.testing.assert_allclose(res.part, part, atol=1e-9)
    assert res.spindle_runout == pytest.approx(spindle.max() - spindle.min())
    assert res.part_out_of_roundness == pytest.approx(part.max() - part.min())


def test_nonuniform_angles():
    rng = np.random.default_rng(1)
    angles = np.sort(rng.uniform(0, 360, 24))
    theta = np.deg2rad(angles)
    spindle = 0.2 * np.sin(3 * theta)
    part = 0.4 * np.cos(2 * theta)
    res = reversal(angles, part + spindle + 1.0, part - spindle - 2.0)
    # under non-uniform sampling the best-fit fundamental of the true signal
    # is nonzero, and removing it is the defined behavior — compare against
    # the truth with its own best-fit DC+fundamental removed
    np.testing.assert_allclose(
        res.spindle, _remove_dc_and_fundamental(theta, spindle), atol=1e-9
    )
    np.testing.assert_allclose(
        res.part, _remove_dc_and_fundamental(theta, part), atol=1e-9
    )


def test_pure_spindle_error_yields_round_part():
    angles, r1, r2, spindle, _ = synth()
    theta = np.deg2rad(angles)
    only_spindle = 0.25 * np.cos(4 * theta)
    res = reversal(angles, only_spindle, -only_spindle)
    np.testing.assert_allclose(res.part, 0.0, atol=1e-9)
    np.testing.assert_allclose(res.spindle, only_spindle, atol=1e-9)


def test_rejects_mismatched_lengths():
    angles, r1, r2, *_ = synth()
    with pytest.raises(ReversalError, match="lengths differ"):
        reversal(angles, r1[:-1], r2)


def test_rejects_too_few_points():
    with pytest.raises(ReversalError, match="at least 8"):
        reversal([0, 90, 180, 270], [0, 0, 0, 0], [0, 0, 0, 0])


def test_rejects_duplicate_angles():
    angles = [0, 45, 90, 135, 180, 225, 270, 360]  # 0 and 360 collide mod 360
    z = np.zeros(8)
    with pytest.raises(ReversalError, match="Duplicate"):
        reversal(angles, z, z)


def test_rejects_partial_arc():
    angles = np.linspace(0, 120, 12)  # only a third of the circle
    z = np.zeros(12)
    with pytest.raises(ReversalError, match="coverage"):
        reversal(angles, z, z)


def test_rejects_nan():
    angles, r1, r2, *_ = synth()
    r1[3] = np.nan
    with pytest.raises(ReversalError, match="Non-finite"):
        reversal(angles, r1, r2)
