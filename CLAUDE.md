# PMD-Runout-Test

Spindle runout measurement (cap probe → cDAQ-9174/NI-9224 via nidaqmx) with
Donaldson reversal. Tkinter GUI. Layout: `src/pmd_runout/` — `daq.py`
(hardware + simulated backends, volts only), `reversal.py` (pure math,
tested in `tests/`), `app.py` (GUI, CSV export, entry point `main`).
License AGPL-3.0-or-later; every source file carries the copyright header.

## Ethos

- This analyzes measurements of a real physical spindle. The math, physics,
  and units must be correct and triple-checked — a wrong runout number
  misleads real machine decisions.
- Fail closed: if a result can't be verified (missing calibration, ambiguous
  units, suspect data), refuse/flag it loudly rather than producing a
  plausible-looking number.
- Report results honestly: measured values with their provenance, never
  fabricated or interpolated data presented as measurement.

## Environment

- Run tests ONLY via `py -3.14 -m pytest`; package management is `uv`.
- Never install packages and never touch the conda envs on this machine —
  they belong to other projects. If a dependency is missing, stop and
  report instead.

## Git

- Never push to a *public* repo without a huge warning flag first.
