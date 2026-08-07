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

## Student instructions

(Same content as the app's Instructions tab.)

### Before you start — software and DAQ connection

1. The NI-DAQmx driver runtime must be installed (free from ni.com). Without
   it the app reports "Could not find an installation of NI-DAQmx" and offers
   simulated mode, which is for UI practice only — simulated data is never a
   measurement.
2. Connect the cDAQ-9174 chassis by USB and power it; the NI-9224 module must
   be seated in a slot. The chassis appears in NI MAX as e.g. `cDAQ1`.
3. Connect the cap-probe box analog output (±10 V) to the NI-9224 input
   channel you intend to use.
4. Launch the app (`run.bat`). Pick your channel from the drop-down
   (e.g. `cDAQ1Mod1/ai0`) and press Connect / Reconnect. The live readout at
   top right shows the probe voltage.

### Measurement setup

5. Mount the test cylinder (precision cylinder / master ball) in the spindle
   and snug it up. Note which mark on the part is at 0°.
6. Attach the printed vernier scale to the spindle so you can index the
   spindle to repeatable angles by hand.
7. Position the capacitance probe against the cylinder at mid-height, aimed
   through the spindle axis. Set the standoff so the readout sits near the
   middle of the ±10 V range, not near an end.
8. Enter the probe sensitivity in µm/V from the cap-probe box datasheet or
   its calibration sheet. There is no default: a guessed sensitivity scales
   every result you report. Recording stays disabled until this field holds a
   positive number.
9. Watch the live readout settle. If the ±std value is much larger than
   usual, something is vibrating or drifting — find it before you take data.

### Run 1 — forward

10. Select "Run 1 — forward".
11. Rotate the spindle by hand to the first vernier angle. Let go, let it
    settle, keep your hands off the machine.
12. Press "Record at this angle". The app takes a 1 s burst and averages it.
    The angle box advances by the step automatically.
13. Repeat all the way around the circle. Use the same angles you intend to
    use in Run 2 — the reversal maths needs identical angle sets.

### Run 2 — reversed

14. Select "Run 2 — reversed".
15. Rotate the **part** 180° relative to the spindle: unchuck it and re-chuck
    it with its reference mark at the 180° position.
16. Move the **probe** 180° to the diametrically opposite side of the part,
    at the same height.
17. ⚠️ Keep the **same probe sign convention**: surface moving toward the
    probe must still read the same sign as it did in Run 1. Do not invert the
    probe electronics, swap leads, or flip a polarity switch. If the sign
    convention flips, the spindle and part results swap places.
18. Measure the same angles as Run 1, same procedure.

### Compute

19. Press "Export CSV" first if you want the raw readings archived — the CSV
    contains only what was measured, never computed values.
20. Press "Compute Runout". Results appear on the Results tab.

### What the reversal separates

A single probe reading is the sum of two unknowns: the shape of the part
(its out-of-roundness) and the error motion of the spindle. Reversing both
the part and the probe flips the sign of the spindle contribution relative to
the part contribution, so the two runs give two independent equations:
r1 = P + S and r2 = P − S. Hence P = (r1 + r2)/2 and S = (r1 − r2)/2. The DC
term and the once-per-revolution term are then removed from both by least
squares: a part mounted slightly off-centre produces a large pure first
harmonic that is centring error, not spindle error motion and not part form
(ASME B89.3.4). So you do not need to centre the part perfectly — but you do
need every reading to be trusted.

### Troubleshooting

- A point whose std is much larger than the others means vibration, drift, or
  you touched something. Delete that row and re-take it.
- "Signal outside ±10 V" means the probe is out of range or unplugged.
  Re-set the standoff; the reading is rejected, not clipped.
- Compute refuses if the two runs do not have exactly the same angles. That
  is deliberate — the app will not interpolate your data.
- "Could not find an installation of NI-DAQmx" at startup: install the
  NI-DAQmx runtime, replug the cDAQ, restart the app.

## License

AGPL-3.0-or-later — Copyright (C) 2026 Liam G. Connolly. See [LICENSE](LICENSE).
