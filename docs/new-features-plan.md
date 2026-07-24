# New GUI observables: status per model

Scope: four new GUI observables layered on top of the existing energy
spectrum / electron-energy views -- **temporal envelope**, **spatial
(transverse-plane) distribution**, **angular distribution**, and an
**angular-range-restricted spectrum** -- evaluated against the two physics
engines currently pluggable into the GUI: **kascade** (`kascade.py`, an
event-generator Monte Carlo) and **xigma-i** (`xigma_i.core.Compton`, a
semi-analytic GPU-only calculation).

Status legend: **Ready** (implemented, no further engine work needed),
**Needs Adapter Change** (data exists in the engine, just needed wiring
through the adapter/contract layer), **Needs Core Change** (the engine
itself needs new computation it doesn't do today).

## Temporal Envelope

| | kascade | xigma-i |
|---|---|---|
| Status | **Ready** (implemented) | **Ready** (implemented) |
| Data already available | `run_multiphoton_chain` already computes `t_emit` per photon (`kascade.py`, was already collected into the per-chunk `photons["t"]` dict) | `Compton.calculate_intersection()` already computes `self.time_envelope` (rate vs. time) and `self.env_ts` (time axis) as public attributes (`core.py:608/620/624`) |
| What was missing | `run_simulation`'s accumulation loop never appended `photons["t"]` to an outer list, so it never reached `Results` | Nothing in `core.py` -- `gui_adapter.py`'s `run_simulation` just never read the two attributes off `compton` after calling `calculate_intersection()` |
| Fix applied | Threaded `ph_t` through `run_multiphoton_chain` -> `run_simulation` -> `Results`, mirroring the existing `ph_thx_lab` pattern | Read `compton.time_envelope`/`compton.env_ts` right after `calculate_intersection()`, packaged into `BinnedTemporalEnvelope` |
| Files | `MC-Kost/kascade.py` (`run_multiphoton_chain`, `run_simulation`, `Results`) | `xigma_i/gui_adapter.py` (`run_simulation`) |
| Risk | Low (additive) | None (zero core.py changes) |

## Spatial (Transverse-Plane) Distribution

| | kascade | xigma-i |
|---|---|---|
| Status | **Ready** (implemented) | **Ready** (implemented) |
| Data already available | `run_multiphoton_chain` already computes `x_e, y_e` (transverse position at emission, used internally for `laser_a0sq`) but never collected anywhere | `particle_kernel` already computes each macroparticle's real x,y internally (previously only to weight the local laser field, then discarded) |
| What was missing | `x_e, y_e` weren't even added to the `photons` dict, let alone threaded to `Results` | A dedicated deposition/accumulation grid over real transverse position -- the existing "deposition" GPU path (`deposition.py`) bins over (gamma, theta_x, theta_y, a0), which is angle/energy space, not position, so it couldn't be reused |
| Fix applied | Threaded `ph_x`, `ph_y` through `run_multiphoton_chain` -> `run_simulation` -> `Results`, same pattern as `ph_t` | Added a new bilinear atomic-add 2D (x,y) deposition grid inside `particle_kernel` (`spatial` argument, `N_SPATIAL=64` per axis), mirroring the existing `time_envelope` mechanism; exposed as `self.spatial_envelope`/`spatial_x_edges`/`spatial_y_edges` on `Compton`, read by `gui_adapter.py` into `BinnedSpatialDistribution` (SI units). Normalization is tied to `calculate_total()`'s already-trusted total yield (self-consistent rescale) rather than re-deriving a new physical prefactor, since `coef`'s angular Gaussian-profile normalization doesn't carry over to a spatial density. Verified on real GPU hardware: integrates back to `total_yield` to within float32 precision, and the measured spread matches the expected beam-laser overlap convolution width to ~5%. |
| Files | `MC-Kost/kascade.py` | `xigma_i/core.py` (`particle_kernel`, `calculate_intersection`), `xigma_i/gui_adapter.py` (wiring) |
| Risk | Low (additive) | Was flagged higher-risk (new CUDA kernel code); implemented and validated against real GPU hardware via `compton-gui/scripts/headless_test.py` (includes a normalization sanity check) |

## Angular Distribution (energy-integrated)

| | kascade | xigma-i |
|---|---|---|
| Status | **Ready** (implemented) | **Ready** (implemented) |
| Data already available | `ph_thx_lab`, `ph_thy_lab` already per-photon in `Results` | `BinnedAngularSpectrum.d2NdEdOmega` (shape theta_x x theta_y x E) already cached from the one precomputed grid `run_simulation` builds |
| What was missing | Nothing engine-side; the GUI just didn't have a dedicated angle-only plot | Nothing engine-side; needed to integrate out the energy axis of an already-cached grid |
| Fix applied | GUI-side 2D weighted histogram of `ph_thx_lab`/`ph_thy_lab` | GUI-side `d2NdEdOmega` summed/`gradient`-weighted over the energy axis |
| Files | `compton_guide/app.py` (`_render_angular_distribution`) only | `compton_guide/app.py` (`_render_angular_distribution`) only |
| Risk | None (pure aggregation of existing data) | None (pure aggregation of existing data) |

## Angular-Range-Restricted Spectrum

| | kascade | xigma-i |
|---|---|---|
| Status | **Ready** (implemented) | **Ready** (implemented) |
| Data already available | `ph_thx_lab`, `ph_thy_lab`, `ph_E_eV` all per-photon in `Results`; `run_simulation` even has a working precedent mask (`in_window`, kascade.py ~lines 984-990) | `Compton.calculate_angular_spectrum()` (`core.py:650`) already accepts **arbitrary** `theta_x`/`theta_y` device arrays as direct arguments -- not limited to any precomputed grid |
| What was missing | Nothing engine-side; needed an adapter method to mask+histogram on demand | `gui_adapter.py` only ever called `calculate_angular_spectrum` once, against one fixed generous 33-point window (`_theta_grid()`); no path existed for a live, user-picked (possibly narrower/off-axis/finer) range |
| Fix applied | `KascadeAdapter.spectrum_in_angular_range()`: mask `ph_thx_lab`/`ph_thy_lab` against the picked range, histogram `ph_E_eV[mask]` | `_theta_grid()` refactored to optionally take an explicit range; new `spectrum_in_angular_range()` does a **fresh** `calculate_angular_spectrum` kernel call against a purpose-built grid (not a reslice of the coarse cache) |
| Files | `compton_guide/adapters/kascade_adapter.py` | `xigma_i/gui_adapter.py` (`_theta_grid`, `spectrum_in_angular_range`) |
| Risk | Low (additive) | None (zero core.py changes -- `calculate_angular_spectrum`'s signature already supports this) |

## Sequencing

1. **Phase 0** -- extract the GUI into its own project (`compton-gui/`), decoupled from `MC-Kost/` and the XIGMA repo, coupled to both engines only through the adapter layer.
2. **Phase 1** -- contract/adapter additions in `model_api.py` and both adapters (new optional dataclasses/fields/capability flags, `spectrum_in_angular_range`).
3. **Phase 2** -- `kascade.py` additive engine changes (`ph_t`, `ph_x`, `ph_y` threaded through `Results`).
4. **Phase 3** -- new GUI tabs (Temporal Envelope, Spatial Distribution, Angular Distribution, Angular-Range Spectrum).
5. **Phase 4** -- xigma-i spatial-distribution kernel work in `core.py`.

All five phases are now implemented. Phases 0-3 are additive-only with respect to both physics engines: `kascade.py` gained three new `Results` fields (`ph_t`, `ph_x`, `ph_y`) with no change to any existing field or function signature. Phase 4 required real `core.py` kernel changes (a new deposition grid inside `particle_kernel`, plus two new fields on `Compton`), the one item in this whole effort that wasn't purely additive wiring -- it was implemented and validated against real GPU hardware (`compton-gui/scripts/headless_test.py`, which checks the spatial density integrates back to `calculate_total()`'s yield).

## Headless testing

`compton-gui/scripts/headless_test.py` exercises every model through the exact same call sequence the GUI makes (`discover_models -> params_to_config -> run -> validate_results`, plus the new temporal/spatial/angular fields and `spectrum_in_angular_range`), with no tkinter/matplotlib import at all -- useful for testing on a GPU machine over SSH without a display, or in CI. Run it in whatever environment has cupy installed for the xigma-i checks to actually execute (e.g. `conda run -n core python3 scripts/headless_test.py`); xigma-i showing "unavailable" elsewhere is expected and not a failure.

This test is also what caught a real bug during integration: `validate_results` (and a few `app.py` render methods) used `isinstance` checks against this package's `SampledSpectrum`/`BinnedSpectrum`/etc., but `xigma_i.gui_adapter` deliberately defines its own structurally-identical local dataclasses (so it doesn't have to depend on this GUI package) -- `isinstance` rejected them as "unexpected type" even though they were perfectly valid. Fixed by switching those checks to duck-typing (attribute presence) instead of nominal `isinstance`.
