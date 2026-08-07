# Copyright (C) 2026 Liam G. Connolly
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Capacitance-probe acquisition via NI-DAQmx (cDAQ-9174 + NI-9224).

Two interchangeable backends:
  CapProbeDAQ  - real hardware through the official nidaqmx wrapper.
  SimulatedDAQ - no hardware/driver needed; clearly labeled, for UI work.

All readings are in VOLTS. Conversion to length happens in the app using
the user-entered probe sensitivity, so the calibration is always explicit.
"""

import math
import random
from dataclasses import dataclass

VOLT_RANGE = 10.0  # NI-9224 / cap probe box output span, +/-10 V
OVERRANGE_V = 9.9  # readings beyond this = probe out of range / clipped


class DAQError(RuntimeError):
    """Hardware, driver, or signal-validity failure. Fail closed."""


@dataclass(frozen=True)
class Reading:
    mean_v: float
    std_v: float
    n_samples: int


def _validate(samples: list[float]) -> Reading:
    n = len(samples)
    if n == 0:
        raise DAQError("DAQ returned no samples.")
    mean = sum(samples) / n
    std = math.sqrt(sum((s - mean) ** 2 for s in samples) / n)
    if max(abs(s) for s in samples) > OVERRANGE_V:
        raise DAQError(
            f"Signal at {max(samples, key=abs):+.2f} V is outside +/-{OVERRANGE_V} V: "
            "probe out of range or unplugged. Reading rejected."
        )
    if not math.isfinite(mean) or not math.isfinite(std):
        raise DAQError("Non-finite samples from DAQ. Reading rejected.")
    return Reading(mean_v=mean, std_v=std, n_samples=n)


class CapProbeDAQ:
    """One AI voltage channel, finite burst reads, mean +/- std in volts."""

    is_simulated = False

    def __init__(self, channel: str = "cDAQ1Mod1/ai0", sample_rate: float = 1000.0):
        self.channel = channel
        self.sample_rate = sample_rate
        try:
            import nidaqmx
            from nidaqmx.constants import TerminalConfiguration
        except Exception as exc:  # driver runtime missing, not just package
            raise DAQError(
                "NI-DAQmx is not available on this machine. Install the NI-DAQmx "
                f"runtime, or use simulated mode for UI work only. ({exc})"
            ) from exc
        self._nidaqmx = nidaqmx
        try:
            self._task = nidaqmx.Task()
            self._task.ai_channels.add_ai_voltage_chan(
                channel,
                min_val=-VOLT_RANGE,
                max_val=VOLT_RANGE,
                terminal_config=TerminalConfiguration.DEFAULT,
            )
        except Exception as exc:
            raise DAQError(f"Could not open channel '{channel}': {exc}") from exc

    def read(self, duration_s: float = 1.0) -> Reading:
        n = max(2, round(self.sample_rate * duration_s))
        try:
            self._task.timing.cfg_samp_clk_timing(
                self.sample_rate, samps_per_chan=n
            )
            samples = self._task.read(
                number_of_samples_per_channel=n, timeout=duration_s + 5.0
            )
        except DAQError:
            raise
        except Exception as exc:
            raise DAQError(f"Acquisition failed: {exc}") from exc
        return _validate(list(samples))

    def close(self) -> None:
        try:
            self._task.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class SimulatedDAQ:
    """Fake probe for UI development. Output is clearly synthetic:
    slow sinusoidal drift + noise around mid-range. Never use for real data;
    the app stamps 'SIMULATED' in the UI and CSV provenance.
    """

    is_simulated = True

    def __init__(self, channel: str = "SIMULATED", sample_rate: float = 1000.0):
        self.channel = "SIMULATED"
        self.sample_rate = sample_rate
        self._t = 0.0
        self._rng = random.Random(0)

    def read(self, duration_s: float = 1.0) -> Reading:
        n = max(2, round(self.sample_rate * duration_s))
        samples = []
        for _ in range(n):
            self._t += 1.0 / self.sample_rate
            samples.append(
                2.0
                + 0.5 * math.sin(2 * math.pi * 0.05 * self._t)
                + self._rng.gauss(0.0, 0.002)
            )
        return _validate(samples)

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
