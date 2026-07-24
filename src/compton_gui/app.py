#!/usr/bin/env python3
r"""
app.py
======

Desktop GUI front-end for pluggable Compton-scattering physics models.

Layout (top -> bottom):

  * "Electrons" panel (blue)  -- electron-bunch parameters in practical units;
    the transverse bunch sizes sigma_ex, sigma_ey are derived live from the
    emittance and the beta function.  When a 6-D ``.ele`` file is loaded via
    ``File -> Load file *.ele...`` the entries turn into a read-only display
    of the parameters derived from the loaded bunch
    (``File -> Clear loaded file`` reverts to input mode).
  * "Laser" panel (blue)      -- laser + relative-position parameters; the peak
    normalises vector potential a_0 is derived live from the laser parameters.
  * "Compton photons" panel (yellow) -- collimation angles, Monte-Carlo sample
    count, random seed and a Calculate button; after a run it prints the
    estimated relative spectral width (and each term of the estimate), the
    total and collimated flux, the mean photon number per electron and the
    fractions of electrons emitting 0/1/2 photons.
  * A tabbed plot area:
      1. Spectrum & Electron  -- collimated photon spectrum + initial-vs-final
         electron energy distribution (the original two-figure view).
      2. Temporal Envelope    -- photon-emission rate/count vs. time.
      3. Spatial Distribution -- transverse (x, y) distribution of photons
         at emission.
      4. Angular Distribution -- angle-only (theta_x, theta_y) photon density,
         integrated over energy.
      5. Angular-Range Spectrum -- an on-demand spectrum restricted to a
         user-picked (theta_x, theta_y) sub-range, computed on request via
         its own "Compute" button (independent of the main Calculate run).

This GUI is model-agnostic: physics engines are plugged in through the
``model_api.ModelAdapter`` registry (see ``model_api.py``) instead of a
hardcoded import. Two adapters are registered by ``models.discover_models()``:
``dfe5`` (the dfe5_compton_mc engine, always available) and ``xigma-i``
(``xigma_i.gui_adapter``, GPU/cupy-only -- shown disabled in the Model menu
if unavailable). Model-specific controls (crossing angle, quantum toggle,
.ele loading, new-observable tabs, ...) are greyed out per the active
model's ``capabilities()``; see ``_apply_model_capabilities``.

Run: ``python3 -m compton_gui.app`` or ``scripts/run_gui.py``.
"""

from __future__ import annotations

import os
import queue
import threading
import traceback

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from compton_gui.physics_constants import C_LIGHT, E_CHARGE, HBAR, EPS0, MEC2_EV, MEC2_J

from compton_gui.model_api import ModelAdapter, SampledSpectrum, validate_results
from compton_gui.models import discover_models

# panel colours
BLUE = "#d6e4f5"
RED = "#f5d6d6"
YELLOW = "#f7f0c0"
GREY = "#e4e4e4"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def _float_or_none(var: tk.StringVar):
    try:
        return float(var.get())
    except (ValueError, tk.TclError):
        return None


def peak_a0(fields: dict):
    """Peak normalised vector potential a_0 from the laser fields (or None)."""
    lam_nm = _float_or_none(fields["laser_wavelength_nm"])
    e_mJ = _float_or_none(fields["laser_energy_mJ"])
    dur_ps = _float_or_none(fields["pulse_duration_ps"])
    R_m = _float_or_none(fields["rayleigh_length_m"])
    if None in (lam_nm, e_mJ, dur_ps, R_m) or min(lam_nm, e_mJ, dur_ps, R_m) <= 0:
        return None
    lambda_L = lam_nm * 1e-9
    omega_L = 2.0 * np.pi * C_LIGHT / lambda_L
    N_L = (e_mJ * 1e-3) / (HBAR * omega_L)
    sigma0_l = 0.5 * np.sqrt(R_m * lambda_L / np.pi)
    sigma_par_L = C_LIGHT * (dur_ps * 1e-12)
    peak_fL = 1.0 / ((2.0 * np.pi) ** 1.5 * sigma0_l ** 2 * sigma_par_L)
    """my QED additions, recoil parameter recoil_q, Compton parameter X_quant"""
    recoil_q = 4.0 * EPS0 * HBAR * omega_L / MEC2_J
    """my QED additions, recoil parameter recoil_q, Compton parameter X_quant"""
    k_a0 = (2.0 * E_CHARGE ** 2 * HBAR * C_LIGHT ** 2 * N_L
            / (EPS0 * MEC2_J ** 2 * omega_L))
    return float(np.sqrt(k_a0 * peak_fL))


def sigma_e(emit_norm_mmmrad, beta_m, gamma):
    """Transverse rms bunch size [m] from normalized emittance, beta [m] and gamma."""
    if (emit_norm_mmmrad is None or beta_m is None or gamma is None
            or emit_norm_mmmrad < 0 or beta_m <= 0 or gamma <= 0):
        return None
    emit_geom = emit_norm_mmmrad * 1e-6 / gamma
    return float(np.sqrt(emit_geom * beta_m))


def laser_focal_radii(wavelength_nm, rayleigh_length_m):
    """Return radial RMS, FWHM, and exp(-1/2) focal radii [m]."""
    if (wavelength_nm is None or rayleigh_length_m is None
            or wavelength_nm <= 0 or rayleigh_length_m <= 0):
        return None
    waist_1e2 = np.sqrt(rayleigh_length_m * wavelength_nm * 1e-9 / np.pi)
    return (float(waist_1e2 / 2.0),
        float(waist_1e2 * np.sqrt(np.log(2.0) / 2.0 )),
        float(waist_1e2 / (2.0* np.sqrt(2.0))))


# ---------------------------------------------------------------------------
# Widget helper -- coloured field grid
# ---------------------------------------------------------------------------
def add_field_grid(parent, specs, fields, n_cols, bg, width=10, group_starts=(),
                   state="normal"):
    """Place (label, default, key) triples in an n_cols-wide grid inside a
    coloured (bg) panel, using classic tk widgets so the background shows.

    Returns a list of (Entry widget, label key) for the fields that were placed,
    so the caller can flip their ``state`` (e.g. disabled when the panel is
    being used as an output display)."""
    entries = []
    for idx, (label, default, key) in enumerate(specs):
        row, col = divmod(idx, n_cols)
        lpad = 18 if idx in group_starts else 8
        tk.Label(parent, text=label, bg=bg, anchor="w").grid(
            row=row, column=col * 2, sticky="w", padx=(lpad, 3), pady=3)
        var = tk.StringVar(value=str(default))
        ent = tk.Entry(parent, textvariable=var, width=width, justify="right",
                       state=state)
        ent.grid(row=row, column=col * 2 + 1, padx=(0, 10), pady=3)
        fields[key] = var
        entries.append((ent, key))
    return entries


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class DFE4App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Compton Source Simulator")
        self.geometry("1280x960+20+10")

        self.fields: dict[str, tk.StringVar] = {}
        self.quantum_var = tk.BooleanVar(value=False)  # False = classical, True = quantum
        self.nonlin_var = tk.BooleanVar(value=True)    # xigma-i-only: emulate a0 downshift
        self.res = None                 # model_api.CommonResults | None
        self.cfg_used = None            # active model's Config-shaped object | None
        self.rep_rate_hz = 1.0
        self.a0_used = 0.0
        self.q: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.q_ang: queue.Queue = queue.Queue()
        self.ang_worker: threading.Thread | None = None

        # Model registry: discover once, pick dfe5 as the startup default
        # (it's always available; xigma-i may be registered as an
        # UnavailableAdapter if cupy/CUDA isn't usable on this machine).
        self.models = discover_models()
        self.model_var = tk.StringVar(value="dfe5")
        self.active_adapter: ModelAdapter = self.models["dfe5"]
        self._trust_warned: set[str] = set()

        # SDDS-bunch loading state.  ``loaded_bunch`` is the dict returned by
        # the active adapter's ``load_ele_file`` (per-particle arrays + header
        # parameters) and is fed to the adapter's ``run`` as the ``electrons``
        # argument.  ``loaded_path`` is the source filename shown in the menu.
        self.loaded_bunch: dict | None = None
        self.loaded_path: str | None = None
        # Cached list of (Entry widget, key) tuples for the Electron panel
        # input fields, so we can flip their state when the panel switches
        # between input-mode and display-mode.
        self._electron_entries: list[tuple[tk.Entry, str]] = []
        # Trace ids we attach to electron-panel StringVars so we can detach
        # them while the panel is in display mode (otherwise the
        # ``_update_derived`` callback would clobber our output values).
        self._electron_traces: list[tuple[tk.StringVar, str]] = []

        self._build_menu()
        self._build_trust_banner()
        self._build_electrons_panel()
        self._build_laser_panel()
        self._build_compton_panel()
        self._build_model_params_panel()
        self._build_plot_area()
        self._wire_live_updates()
        self._update_derived()
        self._apply_model_capabilities()

    # ---- menu -----------------------------------------------------------
    def _build_menu(self):
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Load file *.ele...", command=self._load_ele)
        filemenu.add_command(label="Clear loaded file",
                              command=self._clear_loaded_ele)
        filemenu.add_separator()
        filemenu.add_command(label="Save plots...", command=self._save_fig)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=filemenu)
        self.filemenu = filemenu
        self._ele_menu_indices = (0, 1)  # "Load file...", "Clear loaded file"

        modelmenu = tk.Menu(menubar, tearoff=0)
        for name, adapter in self.models.items():
            caps = adapter.capabilities()
            modelmenu.add_radiobutton(
                label=caps.display_name, variable=self.model_var, value=name,
                command=self._on_model_selected)
            available, reason = adapter.available()
            if not available:
                modelmenu.entryconfig(caps.display_name, state="disabled")
        menubar.add_cascade(label="Model", menu=modelmenu)
        self.modelmenu = modelmenu

        optmenu = tk.Menu(menubar, tearoff=0)
        optmenu.add_radiobutton(label="Classical",
                                 variable=self.quantum_var, value=False)
        optmenu.add_radiobutton(label="Quantum corrections",
                                 variable=self.quantum_var, value=True)
        optmenu.add_separator()
        optmenu.add_checkbutton(label="Emulate nonlinearity (a0 downshift)",
                                 variable=self.nonlin_var)
        menubar.add_cascade(label="Options", menu=optmenu)
        self.optmenu = optmenu
        self._quantum_menu_indices = (0, 1)
        self._nonlin_menu_index = 3

        calcmenu = tk.Menu(menubar, tearoff=0)
        calcmenu.add_command(label="Calculate", command=self.on_start)
        menubar.add_cascade(label="Calculations", menu=calcmenu)

        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)
        self.config(menu=menubar)

    def _build_trust_banner(self):
        self.trust_lbl = tk.Label(self, text="", anchor="w",
                                   font=("TkDefaultFont", 9, "italic"))
        self.trust_lbl.pack(side="top", fill="x", padx=8, pady=(2, 0))

    # ---- model selection --------------------------------------------------
    def _on_model_selected(self):
        name = self.model_var.get()
        self.active_adapter = self.models[name]
        self._rebuild_model_params_panel()
        self._apply_model_capabilities()

    def _apply_model_capabilities(self):
        """Grey out / restore controls the active model doesn't support, and
        refresh the trust banner. Called on startup and on every model switch."""
        caps = self.active_adapter.capabilities()

        # crossing angle: force to 0 and disable when unsupported
        crossing_entry = self._laser_entry_by_key.get("crossing_angle")
        if crossing_entry is not None:
            if caps.supports_crossing_angle:
                crossing_entry.config(state="normal")
            else:
                self.fields["crossing_angle"].set("0")
                crossing_entry.config(state="disabled")

        # quantum toggle
        for idx in self._quantum_menu_indices:
            self.optmenu.entryconfig(
                idx, state="normal" if caps.supports_quantum_toggle else "disabled")
        if not caps.supports_quantum_toggle:
            self.quantum_var.set(False)

        # nonlinearity-emulation toggle (xigma-i-only axis)
        self.optmenu.entryconfig(
            self._nonlin_menu_index,
            state="normal" if caps.supports_nonlinearity_emulation else "disabled")

        # .ele file I/O
        for idx in self._ele_menu_indices:
            self.filemenu.entryconfig(
                idx, state="normal" if caps.supports_ele_file_io else "disabled")
        if not caps.supports_ele_file_io and self.loaded_bunch is not None:
            messagebox.showwarning(
                "Model note",
                f"{caps.display_name} does not support loaded .ele bunches; "
                "clearing the loaded file.")
            self._clear_loaded_ele()

        # new-observable tabs
        for tab, supported in (
                (self.tab_temporal, caps.supports_temporal_envelope),
                (self.tab_spatial, caps.supports_spatial_distribution),
                (self.tab_angular, caps.supports_angular_distribution),
                (self.tab_angular_range, caps.supports_angular_range_spectrum)):
            self.notebook.tab(tab, state="normal" if supported else "disabled")
        self.angular_range_compute_btn.config(
            state="normal" if caps.supports_angular_range_spectrum else "disabled")

        # trust banner
        colour = "#175" if caps.trust_level == "production" else "#a52"
        self.trust_lbl.config(
            text=f"Model: {caps.display_name} - {caps.trust_level}"
                 + (f"  ({caps.trust_note})" if caps.trust_level != "production" else ""),
            fg=colour)
        if caps.trust_level.startswith("experimental") and caps.name not in self._trust_warned:
            self._trust_warned.add(caps.name)
            messagebox.showwarning(
                f"{caps.display_name}: experimental model",
                caps.trust_note)

    def _show_about(self):
        messagebox.showinfo(
            "About",
            "Compton Source Simulator\n\n"
            "Model-agnostic GUI front-end for pluggable Compton-scattering "
            "physics engines (dfe5_compton_mc, xigma-i, ...).")

    def _save_fig(self):
        path = filedialog.asksaveasfilename(defaultextension=".png",
                                            filetypes=[("PNG", "*.png")])
        if path:
            self.fig.savefig(path, dpi=150)

    # ---- SDDS .ele file load / clear -----------------------------------
    def _load_ele(self):
        """Load a 6-D electron bunch from an SDDS ``.ele`` file and turn the
        Electrons panel into an output display of the parameters that the
        simulation will actually use."""
        path = filedialog.askopenfilename(
            title="Load 6-D electron distribution",
            defaultextension=".ele",
            filetypes=[("SDDS electron distribution", "*.ele"),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            bunch = self.active_adapter.load_ele_file(path)
        except Exception as e:
            messagebox.showerror(
                "Cannot load .ele file",
                f"Failed to parse {os.path.basename(path)}:\n\n{e}")
            return
        try:
            summary = self.active_adapter.ele_file_summary(bunch)
        except Exception as e:
            messagebox.showerror(
                "Cannot compute parameters",
                f"Loaded {os.path.basename(path)} but failed to derive "
                f"parameters:\n\n{e}")
            return
        self.loaded_bunch = bunch
        self.loaded_path = path
        self._set_electron_panel_display(summary, os.path.basename(path))

    def _clear_loaded_ele(self):
        """Drop the loaded ``.ele`` bunch and restore the Electrons panel
        to its normal input mode (using whatever is currently in the
        entry fields)."""
        if self.loaded_bunch is None:
            return
        self.loaded_bunch = None
        self.loaded_path = None
        self._set_electron_panel_input()

    def _set_electron_panel_display(self, summary, basename):
        """Flip the Electron-panel entries to read-only and write the
        parameters derived from the loaded file."""
        # Detach live-update traces so they don't clobber our display values
        for var, tname in self._electron_traces:
            try:
                var.trace_remove("write", tname)
            except tk.TclError:
                pass
        self._electron_traces = []

        values = {
            "mean_energy_MeV": f"{summary['mean_energy_MeV']:.4g}",
            "rel_spread_pct":  f"{summary['rel_spread_pct']:.4g}",
            "bunch_duration_ps": f"{summary['bunch_duration_ps']:.4g}",
            "emit_x_mmmrad":   f"{summary['emit_x_mmmrad']:.4g}",
            "emit_y_mmmrad":   f"{summary['emit_y_mmmrad']:.4g}",
            "beta_x_m":        f"{summary['beta_x_m']:.4g}",
            "beta_y_m":        f"{summary['beta_y_m']:.4g}",
        }
        for key, text in values.items():
            self.fields[key].set(text)
        for ent, _key in self._electron_entries:
            ent.config(state="readonly", disabledforeground="#123",
                       readonlybackground=BLUE)

        self.sigma_ex_lbl.config(
            text=f"sigma_x = {summary['sigma_ex_um']:.3f} um")
        self.sigma_ey_lbl.config(
            text=f"sigma_y = {summary['sigma_ey_um']:.3f} um")
        self.electron_mode_lbl.config(
            text=f"(loaded from {basename} - Electrons panel is read-only)")

    def _set_electron_panel_input(self):
        """Restore the Electron-panel entries to editable input mode and
        re-attach the live-update traces."""
        for ent, _key in self._electron_entries:
            ent.config(state="normal")
        self.electron_mode_lbl.config(
            text="(input mode - edit the fields above to define the bunch)")
        # Re-attach the write traces used by _update_derived.
        for k in ("emit_x_mmmrad", "emit_y_mmmrad", "beta_x_m", "beta_y_m",
                  "mean_energy_MeV"):
            tname = self.fields[k].trace_add(
                "write", lambda *a: self._update_derived())
            self._electron_traces.append((self.fields[k], tname))
        self._update_derived()

    # ---- Electrons panel (blue) ----------------------------------------
    def _build_electrons_panel(self):
        p = tk.LabelFrame(self, text="ELECTRONS", bg=BLUE, fg="#123",
                      font=("TkDefaultFont", 14, "bold"))
        p.pack(side="top", fill="x", padx=6, pady=(6, 3))

        specs = [
        ("Mean energy [MeV]", 2000, "mean_energy_MeV"),
        ("Rel. spread [%]", 0.1, "rel_spread_pct"),
        ("Charge [nC]", 1, "charge_nC"),
        ("Duration [ps]", 10, "bunch_duration_ps"),
        ("eps_x,n [mm*mrad]", 1.0, "emit_x_mmmrad"),
        ("eps_y,n [mm*mrad]", 1.0, "emit_y_mmmrad"),
        ("beta_x [m]", 0.2, "beta_x_m"),
        ("beta_y [m]", 0.2, "beta_y_m"),
        ]
        self._electron_entries = add_field_grid(
            p, specs, self.fields, n_cols=4, bg=BLUE, width=5)
        # derived transverse sizes
        self.sigma_ex_lbl = tk.Label(p, text="sigma_x = --", bg=BLUE, anchor="w")
        self.sigma_ex_lbl.grid(row=0, column=8, sticky="w", padx=(15, 5), pady=3)

        self.sigma_ey_lbl = tk.Label(p, text="sigma_y = --", bg=BLUE, anchor="w")
        self.sigma_ey_lbl.grid(row=1, column=8, sticky="w", padx=(15, 5), pady=3)
        # hint that flips between "input" and "loaded from <file>" in display mode
        self.electron_mode_lbl = tk.Label(
            p, text="(input mode - edit the fields above to define the bunch)",
            bg=BLUE, anchor="w", fg="#234",
            font=("TkDefaultFont", 9, "italic"))
        self.electron_mode_lbl.grid(row=2, column=0, columnspan=9, sticky="w",
                                    padx=10, pady=(2, 2))

    # ---- Laser panel (red) --------------------------------------------
    def _build_laser_panel(self):
        p = tk.LabelFrame(self, text="LASER", bg=RED, fg="#123",
                          font=("TkDefaultFont", 14, "bold"))
        p.pack(side="top", fill="x", padx=6, pady=3)
        specs = [
            ("Laser wavelength [nm]", 1000, "laser_wavelength_nm"),
            ("Laser energy [mJ]", 300, "laser_energy_mJ"),
            ("Pulse duration [ps]", 3, "pulse_duration_ps"),
            ("Rayleigh length [m]", 0.00126, "rayleigh_length_m"),
            ("Pulse frequency [Hz]", 100, "pulse_frequency_Hz"),
            ("Crossing angle [rad]", 0, "crossing_angle"),
            ("t-mismatch [ps]", 0, "time_mismatch_ps"),
            ("X-mismatch [mm]", 0, "x_mismatch_mm"),
            ("Y-mismatch [mm]", 0, "y_mismatch_mm"),
            ("Z-mismatch [mm]", 0, "z_mismatch_mm"),
        ]
        # laser fields fill row 0 (5 cols); mismatch fields start on row 1
        laser_entries = add_field_grid(p, specs, self.fields, n_cols=5, bg=RED,
                                       width=5, group_starts={6})
        self._laser_entry_by_key = {key: ent for ent, key in laser_entries}
        self.a0_lbl = tk.Label(p, text="a_0 : --", bg=RED, anchor="w",
                               font=("TkDefaultFont", 10, "bold"))
        self.a0_lbl.grid(row=2, column=0, columnspan=2, sticky="w", padx=8,
                         pady=(4, 2))

        self.laser_radius_lbls = []
        for column, text in ((2, "RMS radius = --"),
                             (4, "FWHM radius = --"),
                             (6, "e^{-1/2} radius = --")):
            label = tk.Label(p, text=text, bg=RED, anchor="w")
            label.grid(row=2, column=column, columnspan=2, sticky="w",
                       padx=8, pady=(4, 2))
            self.laser_radius_lbls.append(label)

    # ---- Compton photons panel (yellow) --------------------------------
    def _build_compton_panel(self):
        p = tk.LabelFrame(self, text="COMPTON PHOTONS", bg=YELLOW, fg="#432",
                          font=("TkDefaultFont", 14, "bold"))
        p.pack(side="top", fill="x", padx=6, pady=3)

        # inputs row
        inp = tk.Frame(p, bg=YELLOW)
        inp.grid(row=0, column=0, columnspan=2, sticky="w", padx=4, pady=(2, 6))
        specs = [
            ("theta_x,col [mrad]", 0.05, "theta_x_col_mrad"),
            ("theta_y,col [mrad]", 0.05, "theta_y_col_mrad"),
            ("Number of macroelectrons", 200000, "n_mc"),
            ("Random seed", 1, "seed"),
        ]
        for i, (label, default, key) in enumerate(specs):
            tk.Label(inp, text=label, bg=YELLOW).grid(row=0, column=2 * i, sticky="w", padx=(8, 3))
            var = tk.StringVar(value=str(default))
            tk.Entry(inp, textvariable=var, width=11, justify="right").grid(row=0, column=2 * i + 1, padx=(0, 6))
            self.fields[key] = var
        self.calc_btn = tk.Button(inp, text="Calculate", command=self.on_start)
        self.calc_btn.grid(row=0, column=8, padx=12)
        self.status_lbl = tk.Label(inp, text="idle", bg=YELLOW, width=10)
        self.status_lbl.grid(row=0, column=9, padx=4)

        # relative-spread estimate formula (rendered with matplotlib mathtext)
        self.spread_fig = plt.Figure(figsize=(9.6, 0.55))
        self.spread_fig.patch.set_facecolor(YELLOW)
        axf = self.spread_fig.add_axes([0, 0, 1, 1]); axf.axis("off")
        axf.text(0.01, 0.5,
                 r"$\frac{\Delta \hbar \omega_c}{\hbar \omega_c}\approx"
                 r"\sqrt{(\gamma\theta_{col})^4+4\left(\frac{\Delta \gamma}{\gamma}\right)^2"
                 r"+\left(\frac{\Delta \hbar \omega_L}{\hbar \omega_L}\right)^2"
                 r"+\left(\frac{\epsilon}{\sigma}\right)^4"
                 r"+\left(\frac{a_0^2}{2}\right)^2}$",
                 ha="left", va="center", fontsize=13)
        cf = FigureCanvasTkAgg(self.spread_fig, master=p)
        cf.get_tk_widget().grid(row=1, column=0, columnspan=2, sticky="we", padx=6)
        self.spread_canvas = cf

        # outputs: left = spread terms, right = fluxes / statistics
        bottom_frame = tk.Frame(p, bg=YELLOW)
        bottom_frame.grid(row=3, column=0, columnspan=3, sticky="we", padx=6, pady=4)
        bottom_frame.columnconfigure(0, weight=0, minsize=120)
        bottom_frame.columnconfigure(1, weight=0, minsize=120)
        bottom_frame.columnconfigure(2, weight=0, minsize=120)

        mono = ("TkFixedFont", 11)

        left = tk.Frame(bottom_frame, bg=YELLOW, width=120, height=200)
        left.propagate(False)
        left.grid(row=0, column=0, sticky="nw", padx=10, pady=4)

        righta = tk.Frame(bottom_frame, bg=YELLOW, width=120, height=200)
        righta.propagate(False)
        righta.grid(row=0, column=1, sticky="nw", padx=50, pady=4)

        rightb = tk.Frame(bottom_frame, bg=YELLOW, width=120, height=200)
        rightb.propagate(False)
        rightb.grid(row=0, column=2, sticky="nw", padx=5, pady=4)

        self.term_lbls: dict[str, tk.Label] = {}
        term_specs = [
            ("coll", "(g*th_col)^4:"),
            ("espread", "4(Dg/g)^2:"),
            ("laser_bw", "(D*hw_L/hw_L)^2:"),
            ("emit", "(eps/sig)^4:"),
            ("a0", "(a0^2/2)^2:"),
            ("total", "D*hw_c/hw_c:"),
        ]
        for r, (key, name) in enumerate(term_specs):
            font = (mono[0], mono[1], "bold") if key == "total" else mono
            tk.Label(left, text=name, bg=YELLOW, font=font, width=18, anchor="w").grid(row=r, column=0, sticky="w")
            lab = tk.Label(left, text="--", bg=YELLOW, font=font, width=17, anchor="w")
            lab.grid(row=r, column=1, sticky="w")
            self.term_lbls[key] = lab

        self.stat_lbls: dict[str, tk.Label] = {}
        stat_specs = [
            ("total_flux", "Total flux:"),
            ("coll_flux", "Collimated flux:"),
            ("nph_ne", "Nph/Ne:"),
            ("ne0", "Ne0(0ph emit e-):"),
            ("ne1", "Ne1(1ph emit e-):"),
            ("ne2", "Ne2(2ph emit e-):"),
        ]
        for r, (key, name) in enumerate(stat_specs):
            tk.Label(righta, text=name, bg=YELLOW, font=mono, width=17, anchor="w").grid(row=r, column=0, sticky="w")
            lab = tk.Label(righta, text="--", bg=YELLOW, font=mono, width=19, anchor="w")
            lab.grid(row=r, column=1, sticky="w")
            self.stat_lbls[key] = lab

        tk.Label(rightb, text="Recoil parameter:", bg=YELLOW, font=mono, anchor="w").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.stat_lbls["recoil_q"] = tk.Label(rightb, text="--", bg=YELLOW, font=mono, anchor="w")
        self.stat_lbls["recoil_q"].grid(row=0, column=1, sticky="w", padx=5, pady=2)

    # ---- Model parameters panel (grey) -- model-specific numeric fields,
    # rebuilt whenever the active model changes (see _on_model_selected).
    def _build_model_params_panel(self):
        self.model_params_frame = tk.LabelFrame(
            self, text="MODEL PARAMETERS", bg=GREY, fg="#123",
            font=("TkDefaultFont", 14, "bold"))
        self.model_params_frame.pack(side="top", fill="x", padx=6, pady=3)
        self._rebuild_model_params_panel()

    def _rebuild_model_params_panel(self):
        """Repopulate the Model Parameters panel from
        ``self.active_adapter.extra_params()``. Never re-packs the frame
        itself (only its children) so switching models repeatedly doesn't
        reorder it relative to the plot area below."""
        for child in self.model_params_frame.winfo_children():
            child.destroy()

        specs = self.active_adapter.extra_params()
        if not specs:
            tk.Label(self.model_params_frame, bg=GREY, fg="#567",
                     text="(this model has no model-specific parameters)",
                     font=("TkDefaultFont", 9, "italic")).grid(
                row=0, column=0, sticky="w", padx=8, pady=4)
            return

        # Preserve values already entered if the key survives a model
        # switch (e.g. switching away and back); otherwise use the
        # adapter's own default.
        seeded = [(label, self.fields[key].get() if key in self.fields else default, key)
                  for label, default, key in specs]
        add_field_grid(self.model_params_frame, seeded, self.fields,
                       n_cols=4, bg=GREY, width=8)

    # ---- plots (tabbed notebook) ----------------------------------------
    def _build_plot_area(self):
        outer = ttk.Frame(self)
        outer.pack(side="top", fill="both", expand=True, padx=6, pady=(3, 6))
        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)

        # Tab 1: Spectrum & Electron (the original two-figure view)
        tab1 = ttk.Frame(self.notebook)
        self.notebook.add(tab1, text="Spectrum & Electron")
        self.fig = plt.Figure(figsize=(11, 3.6))
        self.ax_spec, self.ax_e = self.fig.subplots(1, 2)
        self.canvas = FigureCanvasTkAgg(self.fig, master=tab1)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # Tab 2: Temporal Envelope
        self.tab_temporal = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_temporal, text="Temporal Envelope")
        self.fig_t = plt.Figure(figsize=(11, 3.6))
        self.ax_t = self.fig_t.add_subplot(111)
        self.canvas_t = FigureCanvasTkAgg(self.fig_t, master=self.tab_temporal)
        self.canvas_t.get_tk_widget().pack(fill="both", expand=True)

        # Tab 3: Spatial Distribution
        self.tab_spatial = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_spatial, text="Spatial Distribution")
        self.fig_s = plt.Figure(figsize=(11, 3.6))
        self.ax_s = self.fig_s.add_subplot(111)
        self.canvas_s = FigureCanvasTkAgg(self.fig_s, master=self.tab_spatial)
        self.canvas_s.get_tk_widget().pack(fill="both", expand=True)

        # Tab 4: Angular Distribution
        self.tab_angular = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_angular, text="Angular Distribution")
        self.fig_a = plt.Figure(figsize=(11, 3.6))
        self.ax_a = self.fig_a.add_subplot(111)
        self.canvas_a = FigureCanvasTkAgg(self.fig_a, master=self.tab_angular)
        self.canvas_a.get_tk_widget().pack(fill="both", expand=True)

        # Tab 5: Angular-Range Spectrum (on-demand, own Compute button)
        self.tab_angular_range = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_angular_range, text="Angular-Range Spectrum")
        self._build_angular_range_tab(self.tab_angular_range)

        self._render_placeholder()

    def _build_angular_range_tab(self, parent):
        ctrl = tk.Frame(parent)
        ctrl.pack(side="top", fill="x", padx=6, pady=6)
        self.ang_range_vars: dict[str, tk.StringVar] = {}
        tx0 = _float_or_none(self.fields.get("theta_x_col_mrad")) or 0.05
        ty0 = _float_or_none(self.fields.get("theta_y_col_mrad")) or 0.05
        specs = [
            ("theta_x min [mrad]", -tx0, "tx_min"),
            ("theta_x max [mrad]", tx0, "tx_max"),
            ("theta_y min [mrad]", -ty0, "ty_min"),
            ("theta_y max [mrad]", ty0, "ty_max"),
        ]
        for i, (label, default, key) in enumerate(specs):
            tk.Label(ctrl, text=label).grid(row=0, column=2 * i, sticky="w", padx=(8, 3))
            var = tk.StringVar(value=str(default))
            tk.Entry(ctrl, textvariable=var, width=9, justify="right").grid(
                row=0, column=2 * i + 1, padx=(0, 6))
            self.ang_range_vars[key] = var
        self.angular_range_compute_btn = tk.Button(
            ctrl, text="Compute", command=self.on_compute_angular_range)
        self.angular_range_compute_btn.grid(row=0, column=8, padx=12)
        self.angular_range_status_lbl = tk.Label(ctrl, text="idle", width=10)
        self.angular_range_status_lbl.grid(row=0, column=9, padx=4)

        self.fig_r = plt.Figure(figsize=(11, 3.2))
        self.ax_r = self.fig_r.add_subplot(111)
        self.canvas_r = FigureCanvasTkAgg(self.fig_r, master=parent)
        self.canvas_r.get_tk_widget().pack(fill="both", expand=True)
        self.ax_r.text(0.5, 0.5, "Pick a range and press Compute",
                       ha="center", va="center")
        self.ax_r.set_xticks([]); self.ax_r.set_yticks([])
        self.canvas_r.draw()

    def _render_placeholder(self):
        for ax, t in ((self.ax_spec, "Collimated photon spectrum"),
                      (self.ax_e, "Electron energy: initial vs. final")):
            ax.clear()
            ax.text(0.5, 0.5, "Press Calculate to run", ha="center", va="center")
            ax.set_title(t); ax.set_xticks([]); ax.set_yticks([])
        self.fig.tight_layout()
        self.canvas.draw()
        for ax, canvas, fig, title in (
                (self.ax_t, self.canvas_t, self.fig_t, "Temporal envelope"),
                (self.ax_s, self.canvas_s, self.fig_s, "Spatial distribution"),
                (self.ax_a, self.canvas_a, self.fig_a, "Angular distribution")):
            ax.clear()
            ax.text(0.5, 0.5, "Press Calculate to run", ha="center", va="center")
            ax.set_title(title); ax.set_xticks([]); ax.set_yticks([])
            fig.tight_layout()
            canvas.draw()

    # ---- live (no-run) updates -----------------------------------------
    def _wire_live_updates(self):
        for k in ("emit_x_mmmrad", "emit_y_mmmrad", "beta_x_m", "beta_y_m",
                 "mean_energy_MeV"):
            tname = self.fields[k].trace_add(
                "write", lambda *a: self._update_derived())
            self._electron_traces.append((self.fields[k], tname))
        for k in ("laser_wavelength_nm", "laser_energy_mJ", "pulse_duration_ps",
                  "rayleigh_length_m"):
            self.fields[k].trace_add("write", lambda *a: self._update_derived())
        for k in ("theta_x_col_mrad", "theta_y_col_mrad"):
            self.fields[k].trace_add("write", lambda *a: self._update_outputs())

    def _update_derived(self):
        """Refresh electron and laser values derived from the current fields."""
        energy_mev = _float_or_none(self.fields["mean_energy_MeV"])
        gamma = energy_mev * 1e6 / MEC2_EV if energy_mev is not None else None
        sx = sigma_e(_float_or_none(self.fields["emit_x_mmmrad"]),
                     _float_or_none(self.fields["beta_x_m"]), gamma)
        sy = sigma_e(_float_or_none(self.fields["emit_y_mmmrad"]),
                     _float_or_none(self.fields["beta_y_m"]), gamma)
        self.sigma_ex_lbl.config(text=f"sigma_x = {sx*1e6:.3f} um" if sx else "sigma_x = --")
        self.sigma_ey_lbl.config(text=f"sigma_y = {sy*1e6:.3f} um" if sy else "sigma_y = --")
        a0 = peak_a0(self.fields)
        self.a0_lbl.config(text=f"a_0 : {a0:.4g}" if a0 is not None else "a_0 : --")

        radii = laser_focal_radii(
            _float_or_none(self.fields["laser_wavelength_nm"]),
            _float_or_none(self.fields["rayleigh_length_m"]))
        radius_names = ("RMS", "FWHM", "e^{-1/2}")
        for label, name, radius in zip(
                self.laser_radius_lbls, radius_names,
                radii if radii is not None else (None,) * 3):
            text = f"{name} radius = {radius*1e6:.3f} um" if radius else f"{name} radius = --"
            label.config(text=text)

    # ---- run / threading ------------------------------------------------
    def on_start(self):
        if self.worker is not None and self.worker.is_alive():
            return
        adapter = self.active_adapter
        try:
            cfg, extra = adapter.params_to_config(self.fields, self.quantum_var.get())
        except Exception as e:
            messagebox.showerror("Invalid parameter", str(e))
            return
        if extra["warnings"]:
            messagebox.showwarning("Model note", "\n\n".join(extra["warnings"]))

        # If a 6-D .ele file was loaded we override the per-particle
        # sampling inside ``run_simulation`` with the loaded bunch and use
        # the bunch length as the effective ``n_mc``.
        electrons = None
        n_mc = int(extra["n_mc"])
        if self.loaded_bunch is not None:
            electrons = self.loaded_bunch
            n_mc = int(self.loaded_bunch["n_mc"])

        self.cfg_used = cfg
        self.rep_rate_hz = extra["rep_rate_hz"]
        self.a0_used = peak_a0(self.fields) or 0.0
        self.calc_btn.config(state="disabled")
        self.status_lbl.config(text="running...")

        def work():
            try:
                res = adapter.run(cfg, n_mc=n_mc, seed=extra["seed"],
                                  electrons=electrons)
                problems = validate_results(res)
                if problems:
                    raise RuntimeError(
                        f"{adapter.capabilities().display_name} adapter returned "
                        f"malformed results: {'; '.join(problems)}")
                self.q.put(("ok", res))
            except Exception as e:
                self.q.put(("error", "".join(traceback.format_exception(e))))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self.after(100, self._poll_queue)

    def _poll_queue(self):
        try:
            status, payload = self.q.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_queue)
            return
        self.calc_btn.config(state="normal")
        if status == "error":
            self.status_lbl.config(text="error")
            messagebox.showerror("Simulation failed", payload)
            return
        self.res = payload
        self.status_lbl.config(text="done")
        self._update_outputs()

    # ---- on-demand angular-range spectrum (own worker/queue) ------------
    def on_compute_angular_range(self):
        if self.ang_worker is not None and self.ang_worker.is_alive():
            return
        if self.res is None:
            messagebox.showwarning("No results yet", "Run Calculate at least once first.")
            return
        adapter = self.active_adapter
        try:
            tx_min = float(self.ang_range_vars["tx_min"].get()) * 1e-3
            tx_max = float(self.ang_range_vars["tx_max"].get()) * 1e-3
            ty_min = float(self.ang_range_vars["ty_min"].get()) * 1e-3
            ty_max = float(self.ang_range_vars["ty_max"].get()) * 1e-3
        except (ValueError, tk.TclError) as e:
            messagebox.showerror("Invalid range", str(e))
            return

        self.angular_range_compute_btn.config(state="disabled")
        self.angular_range_status_lbl.config(text="running...")

        def work():
            try:
                result = adapter.spectrum_in_angular_range(
                    (tx_min, tx_max), (ty_min, ty_max))
                self.q_ang.put(("ok", result))
            except Exception as e:
                self.q_ang.put(("error", "".join(traceback.format_exception(e))))

        self.ang_worker = threading.Thread(target=work, daemon=True)
        self.ang_worker.start()
        self.after(100, self._poll_queue_angular)

    def _poll_queue_angular(self):
        try:
            status, payload = self.q_ang.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_queue_angular)
            return
        caps = self.active_adapter.capabilities()
        self.angular_range_compute_btn.config(
            state="normal" if caps.supports_angular_range_spectrum else "disabled")
        if status == "error":
            self.angular_range_status_lbl.config(text="error")
            messagebox.showerror("Angular-range spectrum failed", payload)
            return
        self.angular_range_status_lbl.config(text="done")
        self._render_angular_range_result(payload)

    # ---- collimation-dependent outputs (no re-run) ---------------------
    def _collimation_rad(self):
        tx = _float_or_none(self.fields["theta_x_col_mrad"])
        ty = _float_or_none(self.fields["theta_y_col_mrad"])
        tx = tx * 1e-3 if tx is not None else None
        ty = ty * 1e-3 if ty is not None else None
        return tx, ty

    def _update_outputs(self):
        if self.res is None or self.cfg_used is None:
            return
        res, cfg = self.res, self.cfg_used
        tx, ty = self._collimation_rad()

        # --- relative-spread estimate terms (model-agnostic: only needs the
        # common Config fields every adapter's Config exposes) ---
        gamma = cfg.eps0
        theta_coll = np.hypot(tx or 0.0, ty or 0.0)          # rad (corner radius)
        term_coll = (gamma * theta_coll) ** 4
        term_espread = 4.0 * cfg.sigma_eps_rel ** 2
        # laser relative bandwidth from the finite pulse duration: 1/(omega_L sigma_t)
        sigma_t = cfg.sigma_par_L / C_LIGHT
        dEph = 1.0 / (cfg.omega_L * sigma_t) if sigma_t > 0 else 0.0
        term_laser = dEph ** 2
        # emittance/divergence: gamma * combined rms divergence = eps_n/sigma
        div2 = cfg.emit_x / cfg.beta_x + cfg.emit_y / cfg.beta_y
        gdiv = gamma * np.sqrt(div2)
        term_emit = gdiv ** 4
        term_a0 = (self.a0_used ** 2 / 2.0) ** 2
        spread = np.sqrt(term_coll + term_espread + term_laser + term_emit + term_a0)

        self.term_lbls["coll"].config(text=f"{term_coll:.3e}")
        self.term_lbls["espread"].config(text=f"{term_espread:.3e}")
        self.term_lbls["laser_bw"].config(text=f"{term_laser:.3e}")
        self.term_lbls["emit"].config(text=f"{term_emit:.3e}")
        self.term_lbls["a0"].config(text=f"{term_a0:.3e}")
        self.term_lbls["total"].config(text=f"{spread*100:.3f} %")

        # --- fluxes and statistics (branch on result shape) ---
        total_flux, coll_flux, cmask = self._photon_fluxes(res, tx, ty)
        self.stat_lbls["total_flux"].config(text=f"{total_flux:.3e} ph/s")
        self.stat_lbls["coll_flux"].config(text=f"{coll_flux:.3e} ph/s")

        if res.photon_multiplicity is not None:
            pm = res.photon_multiplicity
            self.stat_lbls["nph_ne"].config(text=f"{pm.mean_n_phot:.4e}")
            self.stat_lbls["ne0"].config(text=f"{pm.frac_n0*100:.3f} %")
            self.stat_lbls["ne1"].config(text=f"{pm.frac_n1*100:.3f} %")
            self.stat_lbls["ne2"].config(text=f"{pm.frac_n2*100:.3f} %")
        else:
            for key in ("nph_ne", "ne0", "ne1", "ne2"):
                self.stat_lbls[key].config(text="N/A")

        omega_L = 2.0 * np.pi * C_LIGHT / cfg.lambda_L
        recoil_q = 4.0 * gamma * HBAR * omega_L / MEC2_J
        self.stat_lbls["recoil_q"].config(text=f"{recoil_q:.6f}")

        self._render_plots(res, cmask)

    def _photon_fluxes(self, res, tx, ty):
        """Return (total_flux, collimated_flux, cmask_or_None) [ph/s].

        cmask is only meaningful (and only returned) for SampledSpectrum
        results, where _render_plots uses it to mask the raw photon array;
        for BinnedSpectrum results the collimated flux is obtained by
        integrating the cached angular spectrum instead.
        """
        if isinstance(res.spectrum, SampledSpectrum):
            spec = res.spectrum
            n_tot = spec.E_eV.size
            total_flux = n_tot * spec.weight * self.rep_rate_hz
            photon_samples = res.photon_samples
            thx = getattr(photon_samples, "ph_thx_lab", None)
            thy = getattr(photon_samples, "ph_thy_lab", None)
            if tx is not None and ty is not None and n_tot and thx is not None:
                cmask = (np.abs(thx) <= tx) & (np.abs(thy) <= ty)
            else:
                cmask = np.zeros(n_tot, dtype=bool)
            coll_flux = int(cmask.sum()) * spec.weight * self.rep_rate_hz
            return total_flux, coll_flux, cmask

        # BinnedSpectrum: total flux is the already-physical total yield;
        # collimated flux integrates the cached angular spectrum over the
        # current collimation window.
        total_flux = res.total_yield * self.rep_rate_hz
        ang = res.angular_spectrum
        if ang is None or tx is None or ty is None:
            return total_flux, 0.0, None
        ix = np.abs(ang.theta_x) <= tx
        iy = np.abs(ang.theta_y) <= ty
        if not ix.any() or not iy.any():
            return total_flux, 0.0, None
        dE = np.gradient(ang.E_eV)
        dtx = np.gradient(ang.theta_x)
        dty = np.gradient(ang.theta_y)
        sub = ang.d2NdEdOmega[np.ix_(ix, iy)]
        coll_yield = np.einsum("ijk,i,j,k->", sub, dtx[ix], dty[iy], dE)
        return total_flux, coll_yield * self.rep_rate_hz, None

    # ---- plotting -------------------------------------------------------
    def _render_plots(self, res, cmask):
        if isinstance(res.spectrum, SampledSpectrum):
            self._render_spectrum_sampled(res, cmask)
        else:
            self._render_spectrum_binned(res)

        if res.electron_state is not None:
            self._render_electron_state(res.electron_state)
        else:
            self.ax_e.clear()
            self.ax_e.text(0.5, 0.5,
                            "N/A for this model\n(no electron final-state tracking)",
                            ha="center", va="center")
            self.ax_e.set_title("Electron energy: initial vs. final")
            self.ax_e.set_xticks([]); self.ax_e.set_yticks([])

        self.fig.tight_layout()
        self.canvas.draw()

        self._render_temporal_envelope(res)
        self._render_spatial_distribution(res)
        self._render_angular_distribution(res)

    def _render_spectrum_sampled(self, res, cmask):
        spec = res.spectrum
        self.ax_spec.clear()
        E_keV = spec.E_eV / 1e3
        Ec = E_keV[cmask] if cmask is not None and cmask.size else E_keV[:0]
        if E_keV.size:
            emax = E_keV.max() * 1.02
            self.ax_spec.hist(E_keV, bins=120, range=(0, emax),
                              weights=np.full(E_keV.size, spec.weight),
                              color="0.8", label="all (4*pi)")
        if Ec.size:
            self.ax_spec.hist(Ec, bins=120, range=(0, E_keV.max() * 1.02),
                              weights=np.full(Ec.size, spec.weight),
                              histtype="step", color="crimson", lw=1.5,
                              label="collimated")
        self.ax_spec.set_xlabel(r"photon energy $\hbar\omega_\gamma$ [keV]")
        self.ax_spec.set_ylabel("photons / bin")
        self.ax_spec.set_title("Collimated photon spectrum")
        self.ax_spec.legend(fontsize=8)

    def _render_spectrum_binned(self, res):
        spec = res.spectrum
        self.ax_spec.clear()
        E_keV = spec.E_eV / 1e3
        dNdE_per_keV = spec.dNdE_per_eV * 1e3
        self.ax_spec.plot(E_keV, dNdE_per_keV, color="0.4", label="all (4*pi)")

        tx, ty = self._collimation_rad()
        ang = res.angular_spectrum
        if ang is not None and tx is not None and ty is not None:
            ix = np.abs(ang.theta_x) <= tx
            iy = np.abs(ang.theta_y) <= ty
            if ix.any() and iy.any():
                dtx = np.gradient(ang.theta_x)
                dty = np.gradient(ang.theta_y)
                sub = ang.d2NdEdOmega[np.ix_(ix, iy)]
                coll_dNdE = np.einsum("ijk,i,j->k", sub, dtx[ix], dty[iy])
                self.ax_spec.plot(ang.E_eV / 1e3, coll_dNdE * 1e3,
                                  color="crimson", label="collimated")

        self.ax_spec.set_xlabel(r"photon energy $\hbar\omega_\gamma$ [keV]")
        self.ax_spec.set_ylabel(r"dN/dE [photons / keV]")
        self.ax_spec.set_title("Photon spectrum (semi-analytic, binned)")
        self.ax_spec.legend(fontsize=8)

    def _render_electron_state(self, electron_state):
        self.ax_e.clear()
        E_i = electron_state.eps_i * MEC2_EV / 1e6
        E_f = electron_state.eps_f * MEC2_EV / 1e6
        w = np.full(E_i.size, electron_state.weight)
        rng = (min(E_f.min(), E_i.min()), E_i.max())
        self.ax_e.hist(E_i, bins=120, range=rng, weights=w, histtype="step",
                       color="gray", lw=1.3, label="initial")
        self.ax_e.hist(E_f, bins=120, range=rng, weights=w, histtype="step",
                       color="crimson", lw=1.3, label="final (total)")
        self.ax_e.set_xlabel("electron energy [MeV]")
        self.ax_e.set_ylabel("electrons / bin")
        self.ax_e.set_title("Electron energy: initial vs. final")
        self.ax_e.set_yscale("log")
        self.ax_e.legend(fontsize=8)

    def _render_unavailable(self, ax, canvas, fig, title, message):
        ax.clear()
        ax.text(0.5, 0.5, message, ha="center", va="center")
        ax.set_title(title)
        ax.set_xticks([]); ax.set_yticks([])
        fig.tight_layout()
        canvas.draw()

    def _render_temporal_envelope(self, res):
        te = res.temporal_envelope
        if te is None:
            self._render_unavailable(
                self.ax_t, self.canvas_t, self.fig_t, "Temporal envelope",
                "N/A for this model\n(no temporal data)")
            return
        self.ax_t.clear()
        # Duck-typed on shape, not isinstance: adapters for models that
        # shouldn't depend on this GUI project (e.g. xigma_i.gui_adapter)
        # define their own structurally-identical local dataclasses rather
        # than importing SampledTemporalEnvelope/BinnedTemporalEnvelope.
        if hasattr(te, "weight"):
            t_ps = te.t_seconds * 1e12
            if t_ps.size:
                self.ax_t.hist(t_ps, bins=120,
                               weights=np.full(t_ps.size, te.weight),
                               color="0.4")
            self.ax_t.set_ylabel("photons / bin")
        else:
            self.ax_t.plot(te.t_seconds * 1e12, te.rate, color="0.4")
            self.ax_t.set_ylabel("emission rate [a.u.]")
        self.ax_t.set_xlabel("emission time [ps]")
        self.ax_t.set_title("Photon temporal envelope")
        self.fig_t.tight_layout()
        self.canvas_t.draw()

    def _render_spatial_distribution(self, res):
        sd = res.spatial_distribution
        if sd is None:
            self._render_unavailable(
                self.ax_s, self.canvas_s, self.fig_s, "Spatial distribution",
                "N/A for this model\n(no spatial-deposition kernel yet -- "
                "see docs/new-features-plan.md)")
            return
        self.ax_s.clear()
        # Duck-typed on shape, not isinstance -- see _render_temporal_envelope.
        if hasattr(sd, "weight"):
            x_um = sd.x * 1e6
            y_um = sd.y * 1e6
            if x_um.size:
                h, xedges, yedges = np.histogram2d(
                    x_um, y_um, bins=80,
                    weights=np.full(x_um.size, sd.weight))
                self.ax_s.pcolormesh(xedges, yedges, h.T, shading="auto")
        else:
            self.ax_s.pcolormesh(sd.x_centers * 1e6, sd.y_centers * 1e6,
                                 sd.density.T, shading="auto")
        self.ax_s.set_xlabel("x [um]")
        self.ax_s.set_ylabel("y [um]")
        self.ax_s.set_title("Photon transverse (spatial) distribution at emission")
        self.fig_s.tight_layout()
        self.canvas_s.draw()

    def _render_angular_distribution(self, res):
        self.ax_a.clear()
        if isinstance(res.spectrum, SampledSpectrum):
            photon_samples = res.photon_samples
            thx = getattr(photon_samples, "ph_thx_lab", None)
            thy = getattr(photon_samples, "ph_thy_lab", None)
            weight = getattr(photon_samples, "weight", 1.0)
            if thx is None or thy is None or thx.size == 0:
                self._render_unavailable(
                    self.ax_a, self.canvas_a, self.fig_a,
                    "Angular distribution", "N/A (no photons)")
                return
            thx_mrad = thx * 1e3
            thy_mrad = thy * 1e3
            h, xedges, yedges = np.histogram2d(
                thx_mrad, thy_mrad, bins=80,
                weights=np.full(thx_mrad.size, weight))
            self.ax_a.pcolormesh(xedges, yedges, h.T, shading="auto")
        else:
            ang = res.angular_spectrum
            if ang is None:
                self._render_unavailable(
                    self.ax_a, self.canvas_a, self.fig_a,
                    "Angular distribution", "N/A (no angular data)")
                return
            # angle-only density: integrate the cached d2N/dE dOmega grid
            # over the energy axis (a pure aggregation of already-present
            # data, no new adapter/engine call).
            dE = np.gradient(ang.E_eV)
            d2N_dOmega = np.einsum("ijk,k->ij", ang.d2NdEdOmega, dE)
            self.ax_a.pcolormesh(ang.theta_x * 1e3, ang.theta_y * 1e3,
                                 d2N_dOmega.T, shading="auto")
        self.ax_a.set_xlabel(r"$\theta_x$ [mrad]")
        self.ax_a.set_ylabel(r"$\theta_y$ [mrad]")
        self.ax_a.set_title("Photon angular distribution (energy-integrated)")
        self.fig_a.tight_layout()
        self.canvas_a.draw()

    def _render_angular_range_result(self, result):
        self.ax_r.clear()
        spec = result.spectrum
        # Duck-typed on shape, not isinstance -- see _render_temporal_envelope.
        if hasattr(spec, "weight"):
            E_keV = spec.E_eV / 1e3
            if E_keV.size:
                self.ax_r.hist(E_keV, bins=120,
                               weights=np.full(E_keV.size, spec.weight),
                               color="crimson")
        else:
            self.ax_r.plot(spec.E_eV / 1e3, spec.dNdE_per_eV * 1e3, color="crimson")
        self.ax_r.set_xlabel(r"photon energy $\hbar\omega_\gamma$ [keV]")
        self.ax_r.set_ylabel("photons (or dN/dE) in range")
        tx0, tx1 = result.theta_x_range
        ty0, ty1 = result.theta_y_range
        self.ax_r.set_title(
            f"Spectrum in theta_x in [{tx0*1e3:.3g},{tx1*1e3:.3g}] mrad, "
            f"theta_y in [{ty0*1e3:.3g},{ty1*1e3:.3g}] mrad")
        self.fig_r.tight_layout()
        self.canvas_r.draw()


def main():
    app = DFE4App()
    app.mainloop()


if __name__ == "__main__":
    main()
