# Copyright (C) 2026 Liam G. Connolly
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tkinter front end for spindle runout measurement by Donaldson reversal.

Probe readings are VOLTS; the user-entered probe sensitivity (um/V) is the
only thing that turns them into a length, so it is required before any
recording is allowed. Everything stored, exported and plotted is micrometres.
"""

import argparse
import csv
import datetime
import math
import random
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .daq import CapProbeDAQ, DAQError, SimulatedDAQ, list_ai_channels
from .reversal import ReversalError, reversal

try:
    from importlib.metadata import version as _pkg_version

    VERSION = _pkg_version("pmd-runout")
except Exception:
    VERSION = "unknown"

PROGRAM = "PMD Spindle Runout"
BURST_S = 1.0  # per-point acquisition time
POLL_MS = 300  # live readout period
POLL_S = 0.1  # live readout acquisition time
BIG = ("TkDefaultFont", 16, "bold")
HUGE = ("TkDefaultFont", 20, "bold")

# (style, text) pairs rendered with tags in the Instructions tab.
# Styles: title, head, step, body, warn.
INSTRUCTIONS = [
    ("title", "Spindle Runout by Donaldson Reversal"),
    ("head", "Before you start - software and DAQ connection"),
    ("step", "1. The NI-DAQmx driver runtime must be installed (free from "
             "ni.com). Without it the app reports 'Could not find an "
             "installation of NI-DAQmx' and offers simulated mode, which is "
             "for UI practice only - simulated data is never a measurement."),
    ("step", "2. Connect the cDAQ-9174 chassis by USB and power it; the "
             "NI-9224 module must be seated in a slot. Windows should chime "
             "and the chassis appears in NI MAX as e.g. 'cDAQ1'."),
    ("step", "3. Connect the cap-probe box analog output (+/-10 V) to the "
             "NI-9224 input channel you intend to use."),
    ("step", "4. Launch the app (run.bat). Pick your channel from the "
             "drop-down (e.g. cDAQ1Mod1/ai0 - the list shows every AI "
             "channel NI-DAQmx can see) and press Connect / Reconnect. The "
             "live readout at top right shows the probe voltage."),
    ("head", "Measurement setup"),
    ("step", "5. Mount the test cylinder (precision cylinder / master ball) "
             "in the spindle and snug it up. Note which mark on the part is "
             "at 0 deg."),
    ("step", "6. Attach the printed vernier scale to the spindle so you can "
             "index the spindle to repeatable angles by hand."),
    ("step", "7. Position the capacitance probe against the cylinder at "
             "mid-height, aimed through the spindle axis. Set the standoff "
             "so the readout sits near the middle of the +/-10 V range, not "
             "near an end."),
    ("step", "8. Enter the probe sensitivity in um/V from the cap-probe box "
             "datasheet or its calibration sheet. There is no default: a "
             "guessed sensitivity scales every result you report. Recording "
             "stays disabled until this field holds a positive number."),
    ("step", "9. Watch the live readout settle. If the +/- std value is much "
             "larger than usual, something is vibrating or drifting - find "
             "it before you take data."),
    ("head", "Run 1 - forward"),
    ("step", "10. Select 'Run 1 - forward'."),
    ("step", "11. Rotate the spindle by hand to the first vernier angle. Let "
             "go, let it settle, keep your hands off the machine."),
    ("step", "12. Press 'Record at this angle'. The app takes a 1 s burst "
             "and averages it. The angle box advances by the step "
             "automatically."),
    ("step", "13. Repeat all the way around the circle. Use the same angles "
             "you intend to use in Run 2 - the reversal maths needs "
             "identical angle sets."),
    ("head", "Run 2 - reversed"),
    ("step", "14. Select 'Run 2 - reversed'."),
    ("step", "15. Rotate the PART 180 deg relative to the spindle: unchuck "
             "it and re-chuck it with its reference mark at the 180 deg "
             "position."),
    ("step", "16. Move the PROBE 180 deg to the diametrically opposite side "
             "of the part, at the same height."),
    ("warn", "17. Keep the SAME probe sign convention: surface moving toward "
             "the probe must still read the same sign as it did in Run 1. "
             "Do NOT invert the probe electronics, swap leads, or flip a "
             "polarity switch. If the sign convention flips, the spindle and "
             "part results swap places."),
    ("step", "18. Measure the SAME angles as Run 1, same procedure."),
    ("head", "Compute"),
    ("step", "19. Press 'Export CSV' first if you want the raw readings "
             "archived - the CSV contains only what was measured, never "
             "computed values."),
    ("step", "20. Press 'Compute Runout'. Results appear on the Results tab."),
    ("head", "What the reversal separates"),
    ("body", "A single probe reading is the sum of two unknowns: the shape "
             "of the part (its out-of-roundness) and the error motion of the "
             "spindle. Reversing both the part and the probe flips the sign "
             "of the spindle contribution relative to the part contribution, "
             "so the two runs give two independent equations: r1 = P + S and "
             "r2 = P - S. Hence P = (r1 + r2)/2 and S = (r1 - r2)/2. The DC "
             "term and the once-per-revolution term are then removed from "
             "both by least squares: a part mounted slightly off-centre "
             "produces a large pure first harmonic that is centring error, "
             "not spindle error motion and not part form (ASME B89.3.4). So "
             "you do not need to centre the part perfectly - but you do need "
             "every reading to be trusted."),
    ("head", "Troubleshooting"),
    ("body", "- A point whose std is much larger than the others means "
             "vibration, drift, or you touched something. Delete that row "
             "and re-take it.\n"
             "- 'Signal outside +/-10 V' means the probe is out of range or "
             "unplugged. Re-set the standoff; the reading is rejected, not "
             "clipped.\n"
             "- Compute refuses if the two runs do not have exactly the same "
             "angles. That is deliberate - the app will not interpolate your "
             "data.\n"
             "- 'Could not find an installation of NI-DAQmx' at startup: "
             "install the NI-DAQmx runtime, replug the cDAQ, restart the "
             "app."),
]


class App:
    """Main window. Construct with an already-open DAQ backend."""

    def __init__(self, root: tk.Tk, daq):
        self.root = root
        self.daq = daq
        self.runs = {1: [], 2: []}  # run -> list of (angle_deg, um, std_um)
        self.result = None
        self.busy = False

        try:  # modern Win11-style ttk theme; plain ttk if unavailable
            import sv_ttk

            sv_ttk.set_theme("light")
        except Exception:
            pass

        root.title(PROGRAM)
        root.geometry("1320x800")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_topbar()
        self.nb = ttk.Notebook(root)
        self.nb.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._build_measure_tab()
        self._build_results_tab()
        self._build_instructions_tab()

        self._poll()

    # ---------------------------------------------------------------- top bar

    def _build_topbar(self):
        top = ttk.Frame(self.root, padding=8)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(6, weight=1)

        self.sim_banner = tk.Label(
            self.root,
            text="SIMULATED - NOT REAL DATA",
            bg="#ff8c00",
            fg="black",
            font=HUGE,
        )

        ttk.Label(top, text="Channel:").grid(row=0, column=0, sticky="w")
        self.channel_var = tk.StringVar(value=getattr(self.daq, "channel", "cDAQ1Mod1/ai0"))
        self.channel_cb = ttk.Combobox(top, textvariable=self.channel_var, width=18)
        self.channel_cb.grid(row=0, column=1, padx=(4, 4))
        # enumerate live each time the list is opened; empty = no driver/device
        self.channel_cb.configure(postcommand=self._refresh_channels)
        self._refresh_channels()
        ttk.Button(top, text="Connect / Reconnect", command=self.reconnect).grid(
            row=0, column=2, padx=(0, 16)
        )

        ttk.Label(top, text="Probe sensitivity (um/V):").grid(row=0, column=3, sticky="w")
        self.sens_var = tk.StringVar(value="")  # no default: must come from the cal sheet
        ttk.Entry(top, textvariable=self.sens_var, width=10).grid(row=0, column=4, padx=4)
        self.sens_var.trace_add("write", lambda *_: self._update_record_state())

        box = ttk.LabelFrame(top, text="Live probe  (± = 1σ of burst)", padding=(12, 4))
        box.grid(row=0, column=6, sticky="e")
        self.readout_main = tk.Label(box, text="---", font=HUGE, anchor="e")
        self.readout_main.grid(row=0, column=0, sticky="e")
        self.readout_sub = tk.Label(box, text="", anchor="e")
        self.readout_sub.grid(row=1, column=0, sticky="e")

        self._refresh_banner()

    def _refresh_channels(self):
        chans = list_ai_channels()
        self.channel_cb.configure(values=chans or ["(no NI-DAQmx devices found)"])

    def _refresh_banner(self):
        if self.daq.is_simulated:
            self.sim_banner.grid(row=2, column=0, sticky="ew")
            self.root.rowconfigure(2, weight=0)
        else:
            self.sim_banner.grid_forget()

    def sensitivity(self):
        """um/V as a positive float, or None if the field is not usable."""
        try:
            s = float(self.sens_var.get())
        except ValueError:
            return None
        return s if s > 0 else None

    def _update_record_state(self):
        ok = self.sensitivity() is not None and not self.busy
        self.record_btn.state(["!disabled"] if ok else ["disabled"])
        self.hint.config(
            text=""
            if self.sensitivity() is not None
            else "Enter a positive probe sensitivity (um/V) before recording."
        )

    def reconnect(self):
        try:
            new = CapProbeDAQ(self.channel_var.get().strip())
        except DAQError as exc:
            messagebox.showerror("DAQ error", str(exc))
            return
        self.daq.close()
        self.daq = new
        self._refresh_banner()

    # ------------------------------------------------------------ live readout

    def _poll(self):
        if not self.busy:
            try:
                r = self.daq.read(POLL_S)
                s = self.sensitivity()
                if s is not None:
                    self._set_readout(
                        f"{r.mean_v * s:+.3f} ± {r.std_v * s:.3f} µm",
                        f"{r.mean_v:+.4f} ± {r.std_v:.4f} V",
                    )
                else:
                    self._set_readout(
                        f"{r.mean_v:+.4f} ± {r.std_v:.4f} V",
                        "enter sensitivity for µm",
                    )
            except DAQError as exc:
                msg = str(exc)
                self._set_readout(
                    "DAQ error", msg[:90] + ("…" if len(msg) > 90 else ""), "red"
                )
        self.root.after(POLL_MS, self._poll)

    def _set_readout(self, main, sub, color="black"):
        self.readout_main.config(text=main, fg=color)
        self.readout_sub.config(text=sub, fg=color)

    # ----------------------------------------------------------- measure tab

    def _build_measure_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Measure")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(2, weight=1)

        ctl = ttk.Frame(tab)
        ctl.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        self.run_var = tk.IntVar(value=1)
        ttk.Radiobutton(ctl, text="Run 1 - forward", variable=self.run_var, value=1).grid(
            row=0, column=0, padx=(0, 12)
        )
        ttk.Radiobutton(
            ctl,
            text="Run 2 - reversed (part + probe rotated 180 deg)",
            variable=self.run_var,
            value=2,
        ).grid(row=0, column=1, padx=(0, 24))

        ttk.Label(ctl, text="Angle (deg):").grid(row=0, column=2)
        self.angle_var = tk.StringVar(value="0")
        ttk.Spinbox(
            ctl, from_=-360, to=720, increment=5, textvariable=self.angle_var, width=8
        ).grid(row=0, column=3, padx=4)
        ttk.Label(ctl, text="Step:").grid(row=0, column=4)
        self.step_var = tk.StringVar(value="30")
        ttk.Entry(ctl, textvariable=self.step_var, width=6).grid(row=0, column=5, padx=4)

        self.record_btn = ttk.Button(
            ctl, text="Record at this angle", command=self.record
        )
        self.record_btn.grid(row=0, column=6, padx=12)

        self.hint = ttk.Label(tab, text="", foreground="red")
        self.hint.grid(row=1, column=0, columnspan=2, sticky="w")

        self.trees = {}
        for run, col in ((1, 0), (2, 1)):
            box = ttk.LabelFrame(
                tab, text=f"Run {run}" + (" - forward" if run == 1 else " - reversed"),
                padding=6,
            )
            box.grid(row=2, column=col, sticky="nsew", padx=4)
            box.columnconfigure(0, weight=1)
            box.rowconfigure(0, weight=1)
            cols = ("angle_deg", "displacement_um", "std_um")
            tv = ttk.Treeview(box, columns=cols, show="headings", height=14)
            for c in cols:
                tv.heading(c, text=c)
                tv.column(c, width=120, anchor="e")
            tv.grid(row=0, column=0, columnspan=2, sticky="nsew")
            sb = ttk.Scrollbar(box, orient="vertical", command=tv.yview)
            sb.grid(row=0, column=2, sticky="ns")
            tv.configure(yscrollcommand=sb.set)
            ttk.Button(
                box, text="Delete selected", command=lambda r=run: self.delete_selected(r)
            ).grid(row=1, column=0, sticky="w", pady=(6, 0))
            ttk.Button(box, text="Clear run", command=lambda r=run: self.clear_run(r)).grid(
                row=1, column=1, sticky="e", pady=(6, 0)
            )
            self.trees[run] = tv

        bot = ttk.Frame(tab)
        bot.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(bot, text="Export CSV", command=self.export_csv).grid(row=0, column=0)
        ttk.Button(bot, text="Compute Runout", command=self.compute).grid(
            row=0, column=1, padx=8
        )
        if self.daq.is_simulated:
            ttk.Button(
                bot, text="Fill demo reversal data", command=self.fill_demo
            ).grid(row=0, column=2, padx=8)

        self._update_record_state()

    def _refresh_tree(self, run):
        tv = self.trees[run]
        tv.delete(*tv.get_children())
        for angle, um, std in sorted(self.runs[run]):
            tv.insert("", "end", values=(f"{angle:g}", f"{um:.4f}", f"{std:.4f}"))

    def delete_selected(self, run):
        tv = self.trees[run]
        angles = {float(tv.item(i, "values")[0]) for i in tv.selection()}
        if not angles:
            return
        self.runs[run] = [row for row in self.runs[run] if row[0] not in angles]
        self._refresh_tree(run)

    def clear_run(self, run):
        if self.runs[run] and messagebox.askyesno(
            "Clear run", f"Delete all {len(self.runs[run])} points from Run {run}?"
        ):
            self.runs[run] = []
            self._refresh_tree(run)

    def fill_demo(self):
        """Simulated mode only: fabricate a plausible reversal pair so the
        full Export/Compute/Results flow can be exercised without hardware.
        Known truth: spindle 3-lobe 0.15 um + 5th 0.05 um, part 2-lobe
        0.40 um, different eccentricity each run, ~4 nm noise.
        """
        if self.runs[1] or self.runs[2]:
            if not messagebox.askyesno(
                "Overwrite", "Replace all recorded points with demo data?"
            ):
                return
        rng = random.Random()
        if self.sensitivity() is None:
            self.sens_var.set("2.5")
        for run, sign in ((1, 1.0), (2, -1.0)):
            self.runs[run] = []
            for angle in range(0, 360, 30):
                th = math.radians(angle)
                part = 0.40 * math.cos(2 * th) + 0.03 * math.cos(6 * th + 1.1)
                spindle = 0.15 * math.cos(3 * th + 0.8) + 0.05 * math.sin(5 * th)
                ecc = (5.0, 1.2, 0.3) if run == 1 else (4.2, 0.9, -1.5)
                um = (
                    ecc[0]
                    + ecc[1] * math.cos(th + ecc[2])
                    + part
                    + sign * spindle
                    + rng.gauss(0.0, 0.004)
                )
                self.runs[run].append((float(angle), um, abs(rng.gauss(0.004, 0.001))))
            self._refresh_tree(run)

    # --------------------------------------------------------------- recording

    def record(self):
        sens = self.sensitivity()
        if sens is None:
            messagebox.showerror(
                "Sensitivity required",
                "Enter the probe sensitivity in um/V from the cap-probe box "
                "calibration sheet before recording.",
            )
            return
        try:
            angle = round(float(self.angle_var.get()), 3)
        except ValueError:
            messagebox.showerror("Bad angle", "Angle must be a number (degrees).")
            return
        run = self.run_var.get()
        if any(a == angle for a, _, _ in self.runs[run]):
            if not messagebox.askokcancel(
                "Duplicate angle",
                f"Run {run} already has a point at {angle:g} deg. Replace it?",
            ):
                return
            # old point is removed in _recorded, only once the new burst succeeds

        self.busy = True
        self.record_btn.state(["disabled"])
        self._set_readout("Recording…", f"1 s burst at {angle:g}°")

        # tkinter is not thread-safe: the worker must not touch tk at all
        # (even root.after crashes from another thread on Python 3.13+).
        # It drops its result in a list; the main thread polls for it.
        box = []

        def worker():
            try:
                box.append((self.daq.read(BURST_S), None))
            except DAQError as exc:
                box.append((None, exc))
            except Exception as exc:  # never leave the UI stuck in "Recording..."
                box.append((None, DAQError(f"Unexpected acquisition failure: {exc}")))

        threading.Thread(target=worker, daemon=True).start()
        self._await_record(run, angle, sens, box)

    def _await_record(self, run, angle, sens, box):
        if not box:
            self.root.after(50, lambda: self._await_record(run, angle, sens, box))
            return
        reading, exc = box[0]
        self._recorded(run, angle, sens, reading, exc)

    def _recorded(self, run, angle, sens, reading, exc):
        self.busy = False
        self._update_record_state()
        if exc is not None:
            messagebox.showerror("DAQ error - nothing recorded", str(exc))
            return
        # volts -> micrometres using the user's calibration; std scales the same way
        self.runs[run] = [row for row in self.runs[run] if row[0] != angle]
        self.runs[run].append((angle, reading.mean_v * sens, reading.std_v * sens))
        self._refresh_tree(run)
        try:
            step = float(self.step_var.get())
        except ValueError:
            step = 0.0
        self.angle_var.set(f"{angle + step:g}")

    # ------------------------------------------------------------------ export

    def export_csv(self):
        if not (self.runs[1] or self.runs[2]):
            messagebox.showerror("Nothing to export", "No points recorded yet.")
            return
        path = filedialog.asksaveasfilename(
            title="Export raw readings",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        sens = self.sensitivity()
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            for line in (
                f"{PROGRAM} v{VERSION}",
                f"exported: {datetime.datetime.now().astimezone().isoformat(timespec='seconds')}",
                f"channel: {getattr(self.daq, 'channel', '?')}",
                f"sample_rate_hz: {getattr(self.daq, 'sample_rate', '?')}",
                f"burst_duration_s: {BURST_S}",
                f"sensitivity_um_per_v: {sens if sens is not None else 'UNSET'}",
                f"data_source: {'SIMULATED' if self.daq.is_simulated else 'hardware'}",
                "raw recorded readings only - no computed or interpolated values",
            ):
                fh.write(f"# {line}\n")
            w.writerow(["run", "angle_deg", "displacement_um", "std_um"])
            for run in (1, 2):
                for angle, um, std in sorted(self.runs[run]):
                    w.writerow([run, f"{angle:g}", f"{um:.6f}", f"{std:.6f}"])
        messagebox.showinfo("Exported", f"Wrote {path}")

    # ----------------------------------------------------------------- compute

    def compute(self):
        a1 = sorted(a for a, _, _ in self.runs[1])
        a2 = sorted(a for a, _, _ in self.runs[2])
        if a1 != a2:
            only1 = [a for a in a1 if a not in a2]
            only2 = [a for a in a2 if a not in a1]
            messagebox.showerror(
                "Angle sets differ",
                "Both runs must be measured at exactly the same angles; the app "
                "will not interpolate.\n\n"
                f"Only in Run 1: {', '.join(f'{a:g}' for a in only1) or '(none)'}\n"
                f"Only in Run 2: {', '.join(f'{a:g}' for a in only2) or '(none)'}",
            )
            return
        r1 = [um for _, um, _ in sorted(self.runs[1])]
        r2 = [um for _, um, _ in sorted(self.runs[2])]
        try:
            self.result = reversal(a1, r1, r2)  # micrometres in -> micrometres out
        except ReversalError as exc:
            messagebox.showerror("Cannot compute runout", str(exc))
            return
        self._show_result()
        self.nb.select(1)

    # ------------------------------------------------------------- results tab

    def _build_results_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Results")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)

        self.spindle_lbl = ttk.Label(tab, text="Spindle error motion (P-V): --", font=HUGE)
        self.spindle_lbl.grid(row=0, column=0, sticky="w")
        self.part_lbl = ttk.Label(tab, text="Part out-of-roundness (P-V): --", font=HUGE)
        self.part_lbl.grid(row=1, column=0, sticky="w", pady=(0, 8))

        self.fig = Figure(figsize=(6, 6))
        self.ax = self.fig.add_subplot(projection="polar")
        self.canvas = FigureCanvasTkAgg(self.fig, master=tab)
        self.canvas.get_tk_widget().grid(row=2, column=0, sticky="nsew")

        ttk.Label(
            tab,
            text="DC + once-per-rev eccentricity removed per ASME B89.3.4 "
            "(centering error is not spindle error).",
            wraplength=900,
        ).grid(row=3, column=0, sticky="w", pady=(6, 0))

    def _show_result(self):
        res = self.result
        pre = "SIMULATED - " if self.daq.is_simulated else ""
        self.spindle_lbl.config(
            text=f"{pre}Spindle error motion (P-V): {res.spindle_runout:.3f} um "
            f"({res.spindle_runout * 1000.0:.0f} nm)"
        )
        self.part_lbl.config(
            text=f"{pre}Part out-of-roundness (P-V): {res.part_out_of_roundness:.3f} um "
            f"({res.part_out_of_roundness * 1000.0:.0f} nm)"
        )

        th = np.deg2rad(np.append(res.angles_deg, res.angles_deg[0]))
        s = np.append(res.spindle, res.spindle[0])
        p = np.append(res.part, res.part[0])
        # Display-only radial offset R0: roundness plots are drawn about a
        # reference circle so both traces are visible. R0 carries no physics.
        span = max(float(np.abs(np.concatenate([s, p])).max()), 1e-9)
        r0 = 4.0 * span
        self.ax.clear()
        self.ax.plot(th, r0 + s, "-o", ms=3, label="S(theta) spindle error, um")
        self.ax.plot(th, r0 + p, "-s", ms=3, label="P(theta) part form, um")
        self.ax.set_ylim(0, r0 + 2.0 * span)
        self.ax.set_yticklabels([])  # radius is offset by R0; ticks would mislead
        self.ax.set_title(f"Reference circle R0 = {r0:.3f} um (display only)")
        self.ax.legend(loc="lower left", bbox_to_anchor=(-0.15, -0.12))
        self.fig.tight_layout()
        self.canvas.draw_idle()

    # -------------------------------------------------------- instructions tab

    def _build_instructions_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="Instructions")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        txt = tk.Text(
            tab, wrap="word", font=("TkDefaultFont", 10), padx=16, pady=12,
            spacing3=6, relief="flat",
        )
        txt.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(tab, orient="vertical", command=txt.yview)
        sb.grid(row=0, column=1, sticky="ns")
        txt.configure(yscrollcommand=sb.set)
        txt.tag_configure("title", font=("TkDefaultFont", 16, "bold"), spacing3=10)
        txt.tag_configure(
            "head", font=("TkDefaultFont", 12, "bold"), spacing1=12, spacing3=6
        )
        txt.tag_configure("step", lmargin1=12, lmargin2=34)
        txt.tag_configure("body", lmargin1=12, lmargin2=12)
        txt.tag_configure(
            "warn",
            lmargin1=12,
            lmargin2=34,
            background="#fff3cd",
            font=("TkDefaultFont", 10, "bold"),
        )
        for style, text in INSTRUCTIONS:
            txt.insert("end", text + "\n", style)
        txt.configure(state="disabled")

    # ------------------------------------------------------------------ teardown

    def on_close(self):
        try:
            self.daq.close()
        finally:
            self.root.destroy()


def _open_daq(channel: str):
    """Real DAQ, or simulated after an explicit user choice. Fail closed."""
    try:
        return CapProbeDAQ(channel)
    except DAQError as exc:
        root = tk.Tk()
        root.withdraw()
        go_sim = messagebox.askokcancel(
            "No DAQ hardware",
            f"{exc}\n\nContinue in SIMULATED mode (UI testing only)?\n"
            "Simulated data is NOT a measurement.",
        )
        root.destroy()
        if not go_sim:
            return None
        return SimulatedDAQ()


def main() -> None:
    ap = argparse.ArgumentParser(prog="pmd-runout", description=PROGRAM)
    ap.add_argument("--sim", action="store_true", help="force simulated mode (no hardware)")
    ap.add_argument("--channel", default="cDAQ1Mod1/ai0", help="NI-DAQmx AI channel")
    args = ap.parse_args(sys.argv[1:])

    daq = SimulatedDAQ() if args.sim else _open_daq(args.channel)
    if daq is None:
        sys.exit(1)
    root = tk.Tk()
    App(root, daq)
    root.mainloop()


if __name__ == "__main__":
    main()
