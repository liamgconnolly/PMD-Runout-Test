# PMD Spindle Runout

Measures spindle runout for the Precision Machine Design table-top lathe
project, replacing the legacy LabVIEW tool. A capacitance probe (±10 V analog
via cap-probe box) is read by a cDAQ-9174 + NI-9224 through the official
[nidaqmx](https://github.com/ni/nidaqmx-python) wrapper. Students record probe
readings at printed-vernier angles in two setups (Donaldson reversal:
part + probe rotated 180°), export raw CSV, and compute spindle error motion
separated from the test-cylinder's own form error.

Eccentricity (DC + once-per-rev) is removed per ASME B89.3.4 — centering
error is not spindle error. Raw CSV exports are always the untouched probe
readings.

## Requirements

- Windows, Python 3.14 (managed by [uv](https://docs.astral.sh/uv/))
- NI-DAQmx runtime installed (for real measurements; not needed for
  simulated UI mode)

## Run

```
uv run pmd-runout          # real hardware
uv run pmd-runout --sim    # simulated probe, UI testing only
```

## Test

```
py -3.14 -m pytest
```

## License

AGPL-3.0-or-later — Copyright (C) 2026 Liam G. Connolly. See [LICENSE](LICENSE).
