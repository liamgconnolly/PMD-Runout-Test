# Copyright (C) 2026 Liam G. Connolly
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Donaldson reversal for spindle runout measurement.

Convention (must match the physical setup, or the two outputs swap):

  Setup 1 (forward):  probe at 0deg, part mounted at reference mark.
      r1(theta) = P(theta) + S(theta)
  Setup 2 (reversed): part rotated 180deg on the spindle AND probe moved
      180deg to the opposite side, probe sign convention unchanged
      (surface approaching probe = positive in both setups).
      r2(theta) = P(theta) - S(theta)

  Part form:     P(theta) = (r1 + r2) / 2
  Spindle error: S(theta) = (r1 - r2) / 2

DC and the first harmonic are removed from both S and P by least squares
before reporting peak-to-valley values: the fundamental of the probe signal
is centering (eccentricity) error, not spindle error motion or part form.
Least squares (not FFT) so non-uniform angle spacing is handled correctly.
"""

from dataclasses import dataclass

import numpy as np

MIN_POINTS = 8
MIN_COVERAGE_DEG = 270.0


class ReversalError(ValueError):
    """Raised when the input data cannot support a trustworthy result."""


@dataclass(frozen=True)
class ReversalResult:
    angles_deg: np.ndarray
    spindle: np.ndarray  # S(theta), DC + 1st harmonic removed, same units as input
    part: np.ndarray  # P(theta), DC + 1st harmonic removed
    spindle_runout: float  # peak-to-valley of spindle
    part_out_of_roundness: float  # peak-to-valley of part


def _remove_dc_and_fundamental(angles_rad: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Least-squares removal of a0 + a1*cos(theta) + b1*sin(theta)."""
    basis = np.column_stack(
        [np.ones_like(angles_rad), np.cos(angles_rad), np.sin(angles_rad)]
    )
    coeffs, *_ = np.linalg.lstsq(basis, values)
    return values - basis @ coeffs


def _validate(angles_deg: np.ndarray, run1: np.ndarray, run2: np.ndarray) -> None:
    if angles_deg.shape != run1.shape or angles_deg.shape != run2.shape:
        raise ReversalError(
            f"Angle/run lengths differ: {len(angles_deg)} angles, "
            f"{len(run1)} forward points, {len(run2)} reversed points. "
            "Both runs must be measured at the same angles."
        )
    if len(angles_deg) < MIN_POINTS:
        raise ReversalError(
            f"Only {len(angles_deg)} points; need at least {MIN_POINTS} for a "
            "meaningful runout number."
        )
    wrapped = np.sort(angles_deg % 360.0)
    if len(np.unique(wrapped)) != len(wrapped):
        raise ReversalError("Duplicate angles (mod 360) in the data.")
    gaps = np.diff(np.concatenate([wrapped, [wrapped[0] + 360.0]]))
    if 360.0 - gaps.max() < MIN_COVERAGE_DEG:
        raise ReversalError(
            f"Angles span only {360.0 - gaps.max():.0f} deg of the circle "
            f"(largest gap {gaps.max():.0f} deg); need at least "
            f"{MIN_COVERAGE_DEG:.0f} deg coverage."
        )
    if not (np.isfinite(run1).all() and np.isfinite(run2).all()):
        raise ReversalError("Non-finite values in measurement data.")


def reversal(angles_deg, run1, run2) -> ReversalResult:
    """Compute spindle error motion and part form from a reversal pair.

    angles_deg: spindle angles (same for both runs, degrees).
    run1: forward-setup probe readings (any consistent length unit).
    run2: reversed-setup probe readings (same unit, same sign convention).
    """
    angles_deg = np.asarray(angles_deg, dtype=float)
    run1 = np.asarray(run1, dtype=float)
    run2 = np.asarray(run2, dtype=float)
    _validate(angles_deg, run1, run2)

    angles_rad = np.deg2rad(angles_deg)
    part = _remove_dc_and_fundamental(angles_rad, (run1 + run2) / 2.0)
    spindle = _remove_dc_and_fundamental(angles_rad, (run1 - run2) / 2.0)

    return ReversalResult(
        angles_deg=angles_deg,
        spindle=spindle,
        part=part,
        spindle_runout=float(spindle.max() - spindle.min()),
        part_out_of_roundness=float(part.max() - part.min()),
    )
