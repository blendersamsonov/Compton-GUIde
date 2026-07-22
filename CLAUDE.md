# compton-gui

Standalone, model-agnostic Tkinter GUI for Compton-scattering physics
engines. Plugs in physics packages through a shared `ModelAdapter`
contract (`model_api.py`) instead of a hardcoded import, so this project
and the physics packages it drives don't depend on each other's
internals — only on the adapter shape.

Two engines are currently registered (`compton_gui/models.py`):
- `dfe5` → `../MC-Kost` (`dfe5_compton_mc.py`), an event-generator MC, always available (CPU only).
- `xigma-i` → the `xigma_i` package (GPU/cupy-only `Compton` class), shown greyed-out in the Model menu if cupy/CUDA isn't usable.

## Layout

```
src/compton_gui/
  app.py              # DFE4App(tk.Tk) — the actual GUI. ~1150 lines.
  models.py           # discover_models() — model registry setup. Deliberately
                       # has NO tkinter/matplotlib import, so it (and anything
                       # built on it) can be exercised headlessly.
  model_api.py         # The contract: CommonResults, ModelCapabilities,
                       # ModelAdapter protocol, SampledSpectrum/BinnedSpectrum
                       # and their temporal/spatial/angular-range counterparts,
                       # validate_results(), MODEL_REGISTRY.
  bootstrap.py          # sys.path wiring for the two physics repos (see below).
  physics_constants.py  # Local CODATA constants (C_LIGHT, HBAR, MEC2_EV, ...) —
                         # duplicated here rather than imported from dfe5, on
                         # purpose (mirrors xigma_i/gui_adapter.py's own
                         # precedent of local constant duplication).
  adapters/dfe5_adapter.py  # Dfe5Adapter — wraps dfe5_compton_mc with zero
                             # changes to that package's own code.
scripts/
  run_gui.py           # Entry point: python3 scripts/run_gui.py
  headless_test.py     # No-display smoke test — see "Testing" below.
docs/new-features-plan.md  # Status table of which observable is ready /
                            # needs-adapter-change / needs-core-change, per
                            # model. Keep updated when adding new observables.
```

Note: `xigma_i`'s adapter (`gui_adapter.py`) lives in the `xigma_i` repo itself,
not here — it was already-completed integration work at the time this repo
was split out, and moving it would have touched that repo more than
necessary. `compton-gui` only ever does `from xigma_i import gui_adapter`;
decoupling is achieved without relocating that file.

## The ModelAdapter contract, and the bug it caused

`model_api.py` defines `SampledSpectrum`/`BinnedSpectrum`/`BinnedTemporalEnvelope`/
etc. `xigma_i/gui_adapter.py` (in the *other* repo) deliberately defines its
own **structurally-identical but not-the-same-class** local dataclasses,
rather than importing these — so that `xigma_i` doesn't have to depend on
this GUI project. This is intentional and documented in both files.

**Consequence: never use `isinstance(x, SampledSpectrum)` / `isinstance(x, BinnedSpectrum)`
etc. to distinguish "sampled" from "binned" results if both branches check a
specific class.** A single `isinstance(x, SampledSpectrum)` check with an
`else` for everything else is fine (real for dfe5, and correctly false for
anything from xigma-i). But `if isinstance(x, A): ... elif isinstance(x, B): ...`
against *both* `model_api` classes will silently do nothing for xigma-i's
duck-typed equivalents. This exact bug hit `validate_results()` (raised a
bogus "unexpected type" error, reported by the user as "error on unexpected
BinnedSpectrum") and three `app.py` render methods (silently rendered blank
tabs). Fixed by switching to duck-typing: check `hasattr(x, "weight")` (sampled)
vs. `hasattr(x, "dNdE_per_eV"/"rate"/"density")` (binned) instead. If you add
a new paired Sampled/Binned dataclass, follow the same pattern.

## Running it

```bash
python3 scripts/run_gui.py
```

Needs `numpy`, `matplotlib`, system Tk (`tkinter`), and — only if you want
`xigma-i` enabled rather than greyed-out — `cupy` + a working CUDA setup.
`bootstrap.py` inserts `../MC-Kost` and the `xigma_i` repo's `src/` onto
`sys.path` automatically; override with `COMPTON_GUI_DFE5_PATH` /
`COMPTON_GUI_XIGMA_SRC` env vars if your checkout layout differs from
plain sibling directories under the same parent.

On this dev machine specifically: system Python has no pip/cupy/matplotlib.
There's a conda env (`miniforge3`, env name `core`) that already has
cupy 14.0.1 + numpy + matplotlib + tkinter working against the local GPU:

```bash
conda run -n core --no-capture-output python3 scripts/run_gui.py
```

(`conda run` without `--no-capture-output` silently swallows stdout — always
pass it when you want to see anything.)

## Testing (headless, no display needed)

```bash
python3 scripts/headless_test.py                       # dfe5 only, cupy not required
conda run -n core --no-capture-output python3 scripts/headless_test.py   # + xigma-i, needs GPU
```

This calls the *exact* sequence the GUI's `on_start()` calls:
`discover_models() → params_to_config() → run() → validate_results()`, plus
the temporal/spatial/angular-distribution fields and
`spectrum_in_angular_range()`. It's the tool that caught the isinstance bug
above — run it after touching either adapter or either physics engine.
`xigma-i` reporting "unavailable" is expected and not a failure on a machine
without cupy/GPU.

## Adding a new GUI observable

Pattern established by the existing four (temporal envelope, spatial
distribution, angular distribution, angular-range spectrum):
1. Add a `Sampled*`/`Binned*` dataclass pair to `model_api.py` if the shape
   differs between an event-generator model (dfe5) and a semi-analytic one
   (xigma-i); add a `supports_*` flag to `ModelCapabilities` (default `False`).
2. Populate it in `Dfe5Adapter.run()` (usually cheap — dfe5 already has the
   raw per-photon arrays) and in `xigma_i/gui_adapter.py`'s `run_simulation`
   (check whether `core.Compton` already computes what you need internally
   before assuming a new kernel is required — `time_envelope` and the
   angular-range spectrum both turned out to need zero `core.py` changes;
   only spatial distribution genuinely needed new kernel work).
3. Add a tab in `app.py`'s `_build_plot_area`, a `_render_*` method following
   the existing duck-typing convention (not `isinstance` against both variants),
   and gate it via `_apply_model_capabilities`'s tab-disabling loop.
4. Extend `headless_test.py`'s `test_model()` to check the new field.
5. Update `docs/new-features-plan.md`'s status table.

## Known gaps

- `xigma_i`'s spatial-distribution normalization is self-consistently
  rescaled against `calculate_total()` rather than derived from first
  principles (see that repo's CLAUDE.md) — fine for visualization, not
  independently validated as an absolute physical calibration.
- No automated test for `app.py`'s actual Tkinter rendering (only the
  adapter/model layer is covered by `headless_test.py`) — testing the real
  widget tree needs a display (or Xvfb), which hasn't been set up.
