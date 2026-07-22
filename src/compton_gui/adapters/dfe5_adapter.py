"""ModelAdapter wrapping the existing dfe5_compton_mc engine.

This is the "control" adapter: it moves today's params_to_config/run_simulation
call pattern behind the model_api.ModelAdapter shape without changing a single
line of dfe5_compton_mc.py's physics (beyond the additive ph_t/ph_x/ph_y
fields threaded through Results -- see dfe5_compton_mc.py's Results docstring
and model_api.py's temporal/spatial dataclasses).
"""

from __future__ import annotations

import numpy as np

import dfe5_compton_mc as _dfe5
from compton_gui.model_api import (
    AngularRangeSpectrumResult,
    CommonResults,
    ElectronFinalState,
    ModelCapabilities,
    PhotonMultiplicity,
    SampledSpatialDistribution,
    SampledSpectrum,
    SampledTemporalEnvelope,
)


class ParamError(Exception):
    pass


def _float(fields: dict, key: str) -> float:
    try:
        return float(fields[key].get())
    except ValueError:
        raise ParamError(f"'{key}' is not a valid number: {fields[key].get()!r}")


class Dfe5Adapter:
    def __init__(self):
        self._last_results = None   # dfe5_compton_mc.Results | None

    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            name="dfe5",
            display_name="dfe5 (Monte Carlo)",
            requires_gpu=False,
            supports_crossing_angle=True,
            supports_quantum_toggle=True,
            supports_nonlinearity_emulation=False,
            supports_electron_final_state=True,
            supports_photon_multiplicity=True,
            supports_ele_file_io=True,
            supports_seed_reproducibility=True,
            requires_recompute_on_collimation_change=False,
            trust_level="production",
            trust_note="Sequential multi-photon inverse-Compton Monte Carlo "
                       "(the original dfe5_compton_mc engine).",
            supports_temporal_envelope=True,
            supports_spatial_distribution=True,
            supports_angular_distribution=True,
            supports_angular_range_spectrum=True,
        )

    def available(self) -> tuple[bool, str]:
        return True, ""

    def params_to_config(self, fields: dict, quantum: bool = False):
        """Convert the GUI fields into a physics Config plus a driver dict.

        Ported verbatim from dfe5_gui2.params_to_config.
        """
        g = lambda k: _float(fields, k)

        # --- electrons ---
        eps0 = g("mean_energy_MeV") * 1e6 / _dfe5.MEC2_EV
        N_e = g("charge_nC") * 1e-9 / _dfe5.E_CHARGE
        sigma_eps_rel = g("rel_spread_pct") / 100.0
        sigma_par_e = _dfe5.C_LIGHT * (g("bunch_duration_ps") * 1e-12)
        emit_x = g("emit_x_mmmrad") * 1e-6 / eps0
        emit_y = g("emit_y_mmmrad") * 1e-6 / eps0
        beta_x = g("beta_x_m")
        beta_y = g("beta_y_m")
        sigma0_x = np.sqrt(emit_x * beta_x) if beta_x > 0 else 0.0
        sigma0_y = np.sqrt(emit_y * beta_y) if beta_y > 0 else 0.0

        # --- laser ---
        lambda_L = g("laser_wavelength_nm") * 1e-9
        pulse_energy_J = g("laser_energy_mJ") * 1e-3
        sigma_par_L = _dfe5.C_LIGHT * (g("pulse_duration_ps") * 1e-12)
        R_sf = g("rayleigh_length_m")
        sigma0_l = 0.5 * np.sqrt(max(R_sf, 0.0) * lambda_L / np.pi) if R_sf > 0 else 0.0
        rep_rate_hz = g("pulse_frequency_Hz")
        crossing_angle = g("crossing_angle")

        # --- relative position (mismatch) ---
        delta_x = g("x_mismatch_mm") * 1e-3
        delta_y = g("y_mismatch_mm") * 1e-3
        delta_z = g("z_mismatch_mm") * 1e-3 + _dfe5.C_LIGHT * (g("time_mismatch_ps") * 1e-12)

        warnings = []
        if sigma0_x <= 0 or sigma0_y <= 0:
            warnings.append("Beta_x/Beta_y must be > 0 to define a finite beam size; "
                            "using a point-like beam on the affected axis.")
        if sigma0_l <= 0:
            warnings.append("Rayleigh length must be > 0; using a very small laser "
                            "waist as a fallback.")

        cfg = _dfe5.Config(
            eps0=eps0, sigma_eps_rel=sigma_eps_rel,
            emit_x=max(emit_x, 1e-30), emit_y=max(emit_y, 1e-30),
            sigma0_x=max(sigma0_x, 1e-12), sigma0_y=max(sigma0_y, 1e-12),
            sigma_par_e=max(sigma_par_e, 1e-12), N_e=N_e,
            lambda_L=lambda_L, sigma0_l=max(sigma0_l, 1e-9),
            R_sf=max(R_sf, 0.0), sigma_par_L=max(sigma_par_L, 1e-9),
            pulse_energy_J=pulse_energy_J,
            delta_x=delta_x, delta_y=delta_y, delta_z=delta_z,
            crossing_angle=crossing_angle,
            quantum=quantum,
        )
        extra = dict(n_mc=int(g("n_mc")), seed=int(g("seed")),
                     rep_rate_hz=rep_rate_hz, warnings=warnings)
        return cfg, extra

    def run(self, cfg, n_mc: int, seed: int, electrons: dict | None = None) -> CommonResults:
        res = _dfe5.run_simulation(cfg, n_mc=n_mc, seed=seed, electrons=electrons)
        self._last_results = res
        s = res.summary
        return CommonResults(
            model_name="dfe5",
            cfg=cfg,
            n_mc=res.n_mc,
            total_yield=s["N_gamma_total"],
            spectrum=SampledSpectrum(E_eV=res.ph_E_eV, weight=res.weight),
            summary=s,
            angular_spectrum=None,
            photon_samples=res,
            electron_state=ElectronFinalState(eps_i=res.eps_i, eps_f=res.eps_f, weight=res.weight),
            photon_multiplicity=PhotonMultiplicity(
                mean_n_phot=s["measured_mean_n_phot"],
                frac_n0=s["frac_n0_measured"],
                frac_n1=s["frac_n1"],
                frac_n2=s["frac_n2"],
                frac_n3plus=s["frac_n3plus"],
            ),
            temporal_envelope=SampledTemporalEnvelope(t_seconds=res.ph_t, weight=res.weight),
            spatial_distribution=SampledSpatialDistribution(
                x=res.ph_x, y=res.ph_y, weight=res.weight),
            final_distribution_path=s.get("final_distribution_path"),
        )

    def load_ele_file(self, path: str) -> dict:
        return _dfe5.load_ele_file(path)

    def ele_file_summary(self, bunch: dict) -> dict:
        return _dfe5.ele_file_summary(bunch)

    def spectrum_in_angular_range(self, theta_x_range, theta_y_range, **kwargs):
        """Mask the cached per-photon lab angles against the picked range and
        histogram the resulting subset -- reuses dfe5_compton_mc.py's own
        angular-window mask pattern (see run_simulation's ``in_window``),
        just applied at the adapter layer instead of only for summary
        counts."""
        if self._last_results is None:
            raise RuntimeError("spectrum_in_angular_range: run() must be "
                               "called at least once first")
        res = self._last_results
        tx_lo, tx_hi = theta_x_range
        ty_lo, ty_hi = theta_y_range
        mask = ((res.ph_thx_lab >= tx_lo) & (res.ph_thx_lab <= tx_hi) &
                (res.ph_thy_lab >= ty_lo) & (res.ph_thy_lab <= ty_hi))
        n_in_range = int(mask.sum())
        spectrum = SampledSpectrum(E_eV=res.ph_E_eV[mask], weight=res.weight)
        return AngularRangeSpectrumResult(
            spectrum=spectrum, theta_x_range=theta_x_range,
            theta_y_range=theta_y_range,
            n_photons_in_range=n_in_range * res.weight)
