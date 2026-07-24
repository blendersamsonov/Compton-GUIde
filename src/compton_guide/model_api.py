"""Model-agnostic contract between app.py and physics-engine adapters.

This module knows nothing about ``kascade`` or ``xigma_i`` -- adapters
for those packages return plain, locally-defined dataclasses that are merely
*shape-compatible* with the ones below (duck typing), so neither physics
package needs to import this module or the GUI.

Two physics engines currently target this contract:

  * kascade (``adapters/kascade_adapter.py``) is an event-generator Monte Carlo: it
    samples individual macro-electrons and returns unbinned per-macro-photon
    and per-macro-electron arrays (``SampledSpectrum``, ``ElectronFinalState``,
    ``PhotonMultiplicity``, ``SampledTemporalEnvelope``,
    ``SampledSpatialDistribution`` are all populated).
  * xigma-i (``xigma_i.gui_adapter``) is a semi-analytic, GPU-only calculation
    that returns smooth binned spectral-density arrays with no per-electron
    final state and no photon-multiplicity statistics (``BinnedSpectrum``/
    ``BinnedAngularSpectrum``/``BinnedTemporalEnvelope`` populated; the
    unbinned/per-electron fields and ``spatial_distribution`` are ``None``).

The GUI must branch on which of these are present rather than assume kascade's
exact shape -- see ``CommonResults`` field docs below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Union

import numpy as np


# ---------------------------------------------------------------------------
# Spectrum representations
# ---------------------------------------------------------------------------
@dataclass
class SampledSpectrum:
    """Unbinned per-macro-photon energies (kascade-style event generator)."""

    E_eV: np.ndarray            # per-macro-photon energy [eV]
    weight: float                # macro->real particle weight (multiply counts by this)


@dataclass
class BinnedSpectrum:
    """Pre-integrated angle-integrated spectral density (xigma-i-style)."""

    E_eV: np.ndarray            # energy grid, bin centres [eV]
    dNdE_per_eV: np.ndarray     # absolute, already-weighted dN/dE [photons / eV]


@dataclass
class BinnedAngularSpectrum:
    """Pre-integrated angle x angle x energy spectral density."""

    theta_x: np.ndarray          # [rad]
    theta_y: np.ndarray          # [rad]
    E_eV: np.ndarray             # [eV]
    d2NdEdOmega: np.ndarray      # shape (theta_x.size, theta_y.size, E_eV.size), [1/(eV*sr)]


@dataclass
class ElectronFinalState:
    """Initial vs. final electron energy (only meaningful for models that
    track per-electron recoil/emission kinematics)."""

    eps_i: np.ndarray            # initial Lorentz gamma per macro-electron
    eps_f: np.ndarray            # final Lorentz gamma per macro-electron
    weight: float


@dataclass
class PhotonMultiplicity:
    """Per-electron photon-count statistics (only meaningful for models that
    track discrete emission events per electron)."""

    mean_n_phot: float
    frac_n0: float
    frac_n1: float
    frac_n2: float
    frac_n3plus: float


@dataclass
class SampledTemporalEnvelope:
    """Unbinned per-macro-photon emission times (kascade-style)."""

    t_seconds: np.ndarray        # per-macro-photon emission time [s]
    weight: float


@dataclass
class BinnedTemporalEnvelope:
    """Pre-integrated emission-rate-vs-time density (xigma-i-style)."""

    t_seconds: np.ndarray        # time grid [s]
    rate: np.ndarray             # emission rate at each time point


@dataclass
class SampledSpatialDistribution:
    """Unbinned per-macro-photon transverse position at emission (kascade-style)."""

    x: np.ndarray                # per-macro-photon transverse x at emission [m]
    y: np.ndarray
    weight: float


@dataclass
class BinnedSpatialDistribution:
    """Pre-integrated transverse-position density (only populated by models
    with a dedicated spatial-deposition kernel; xigma-i does not have one
    yet -- see docs/new-features-plan.md)."""

    x_centers: np.ndarray
    y_centers: np.ndarray
    density: np.ndarray           # shape (x_centers.size, y_centers.size)


@dataclass
class AngularRangeSpectrumResult:
    """Result of an on-demand spectrum computed over a user-picked angular
    sub-range (``ModelAdapter.spectrum_in_angular_range``)."""

    spectrum: Union[SampledSpectrum, BinnedSpectrum]
    theta_x_range: tuple[float, float]
    theta_y_range: tuple[float, float]
    n_photons_in_range: float | None = None


@dataclass
class CommonResults:
    """What every adapter's ``run()`` must return (shape-compatibly).

    Only ``model_name``, ``cfg``, ``n_mc``, ``total_yield``, ``spectrum`` and
    ``summary`` are guaranteed present and non-None. Everything else is
    optional and ``None`` when the model doesn't compute it -- the GUI must
    check before using it.
    """

    model_name: str
    cfg: Any                     # exposes eps0, sigma_eps_rel, omega_L, emit_x/y,
                                  # beta_x/y, sigma_par_L, N_e, crossing_angle, quantum
    n_mc: int
    total_yield: float           # physical (weighted) total photon count
    spectrum: SampledSpectrum | BinnedSpectrum
    summary: dict                # free-form, model-specific scalar diagnostics (kascade and
                                  # xigma-i both happen to include "crossing_angle_rad" and
                                  # "quantum" keys, by convention, not by contract); use the
                                  # top-level CommonResults fields (total_yield, n_mc, ...)
                                  # for anything that must be read in a model-agnostic way
    angular_spectrum: BinnedAngularSpectrum | None = None
    photon_samples: Any | None = None          # kascade's raw Results, else None
    electron_state: ElectronFinalState | None = None
    photon_multiplicity: PhotonMultiplicity | None = None
    temporal_envelope: SampledTemporalEnvelope | BinnedTemporalEnvelope | None = None
    spatial_distribution: SampledSpatialDistribution | BinnedSpatialDistribution | None = None
    final_distribution_path: str | None = None
    warnings: list[str] = field(default_factory=list)


def validate_results(res: Any) -> list[str]:
    """Defensive duck-type check, run right after ``adapter.run()`` returns.

    Returns a list of problem descriptions; empty means OK. Never raises --
    the GUI decides whether a non-empty list is fatal.

    Deliberately checks *shape* (attribute presence), not ``isinstance``
    against this module's ``SampledSpectrum``/``BinnedSpectrum``: adapters
    for physics packages that shouldn't depend on this GUI project (e.g.
    ``xigma_i.gui_adapter``) define their own structurally-identical local
    dataclasses rather than importing these -- an isinstance check would
    reject every one of those as "unexpected type" even though they're
    perfectly valid.
    """
    problems: list[str] = []
    required = ("model_name", "cfg", "n_mc", "total_yield", "spectrum", "summary")
    for name in required:
        if getattr(res, name, None) is None:
            problems.append(f"missing required field: {name!r}")
    spectrum = getattr(res, "spectrum", None)
    if spectrum is not None:
        looks_sampled = hasattr(spectrum, "E_eV") and hasattr(spectrum, "weight")
        looks_binned = hasattr(spectrum, "E_eV") and hasattr(spectrum, "dNdE_per_eV")
        if not (looks_sampled or looks_binned):
            problems.append(f"spectrum has unexpected type: {type(spectrum)!r}")
    return problems


# ---------------------------------------------------------------------------
# Model capabilities and adapter protocol
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ModelCapabilities:
    name: str
    display_name: str
    requires_gpu: bool
    supports_crossing_angle: bool
    supports_quantum_toggle: bool
    supports_nonlinearity_emulation: bool   # xigma-i-only axis, orthogonal to quantum toggle
    supports_electron_final_state: bool
    supports_photon_multiplicity: bool
    supports_ele_file_io: bool
    supports_seed_reproducibility: bool
    requires_recompute_on_collimation_change: bool
    trust_level: str            # "production" | "experimental-C" | "experimental-D" | ...
    trust_note: str
    supports_temporal_envelope: bool = False
    supports_spatial_distribution: bool = False
    supports_angular_distribution: bool = False
    supports_angular_range_spectrum: bool = False


class ModelAdapter(Protocol):
    def capabilities(self) -> ModelCapabilities: ...

    def available(self) -> tuple[bool, str]:
        """Return (True, "") if the model can actually be run right now, else
        (False, reason). Must never raise."""
        ...

    def extra_params(self) -> list[tuple[str, float, str]]:
        """Model-specific numeric fields with no shared-panel analogue
        (kascade's Electrons/Laser/Compton panels), as (label, default, key)
        triples -- the same shape app.py's add_field_grid already consumes.
        The GUI renders these in a dedicated pane that's rebuilt whenever the
        active model changes, and feeds the resulting values into the same
        flat ``fields`` dict passed to ``params_to_config``. Return ``[]`` if
        the model has none (e.g. kascade today)."""
        ...

    def params_to_config(self, fields: dict, quantum: bool) -> tuple[Any, dict]: ...

    def run(self, cfg: Any, n_mc: int, seed: int,
            electrons: dict | None = None) -> CommonResults: ...

    def load_ele_file(self, path: str) -> dict:
        """Raise NotImplementedError if capabilities().supports_ele_file_io is False."""
        ...

    def ele_file_summary(self, bunch: dict) -> dict:
        """Raise NotImplementedError if capabilities().supports_ele_file_io is False."""
        ...

    def spectrum_in_angular_range(
            self, theta_x_range: tuple[float, float],
            theta_y_range: tuple[float, float],
            **kwargs) -> AngularRangeSpectrumResult:
        """Optional capability -- check
        capabilities().supports_angular_range_spectrum before calling.
        Raise NotImplementedError if unsupported."""
        ...


@dataclass
class UnavailableAdapter:
    """Stub registered when a model's real adapter couldn't be imported/used
    (e.g. cupy missing). Keeps the model visible-but-disabled in the GUI menu
    instead of silently omitting it."""

    _name: str
    _reason: str
    _display_name: str | None = None

    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            name=self._name, display_name=self._display_name or self._name,
            requires_gpu=True, supports_crossing_angle=False,
            supports_quantum_toggle=False, supports_nonlinearity_emulation=False,
            supports_electron_final_state=False, supports_photon_multiplicity=False,
            supports_ele_file_io=False, supports_seed_reproducibility=False,
            requires_recompute_on_collimation_change=False,
            trust_level="unavailable", trust_note=self._reason,
        )

    def available(self) -> tuple[bool, str]:
        return False, self._reason

    def extra_params(self) -> list[tuple[str, float, str]]:
        return []

    def params_to_config(self, fields, quantum):
        raise NotImplementedError(f"{self._name}: {self._reason}")

    def run(self, cfg, n_mc, seed, electrons=None):
        raise NotImplementedError(f"{self._name}: {self._reason}")

    def load_ele_file(self, path):
        raise NotImplementedError(f"{self._name}: {self._reason}")

    def ele_file_summary(self, bunch):
        raise NotImplementedError(f"{self._name}: {self._reason}")

    def spectrum_in_angular_range(self, theta_x_range, theta_y_range, **kwargs):
        raise NotImplementedError(f"{self._name}: {self._reason}")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
MODEL_REGISTRY: dict[str, ModelAdapter] = {}


def register(name: str, adapter: ModelAdapter) -> None:
    MODEL_REGISTRY[name] = adapter


def registered_models() -> dict[str, ModelAdapter]:
    return dict(MODEL_REGISTRY)
