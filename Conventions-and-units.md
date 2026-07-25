# Parameter Semantics & Unit Normalization Module

## Overview

This document specifies a Python module that enforces **consistent physical parameter semantics** across multiple simulation codes with differing conventions.

The system solves two independent problems:

1. **Units consistency** → handled via `pint`
2. **Semantic consistency (definitions/conventions)** → handled via this module

The module acts as an **intermediate canonical layer** between GUI inputs and model-specific implementations.

---

## Goals

* Eliminate ambiguity in physical parameter definitions (e.g. RMS vs FWHM vs 1/e²)
* Provide automatic conversion between conventions
* Ensure model codes explicitly declare parameter semantics
* Enable GUI to dynamically adapt to model requirements
* Prevent silent mismatches

---

## Architecture

```
[ GUI ]
   ↓
[ Input (Pint + semantic tags) ]
   ↓
[ Canonical parameter representation ]
   ↓
[ Conversion engine ]
   ↓
[ Model adapter (based on model spec) ]
   ↓
[ Simulation code ]
```

---

## Module Structure

Create a module:

```
physics_params/
    __init__.py
    enums.py
    quantities.py
    converters.py
    canonical.py
    validation.py
    schema.py
```

---

## 1. Enums (enums.py)

Define shared vocabulary.

```python
from enum import Enum, auto

class PhysicalMeaning(Enum):
    LASER_WIDTH = auto()
    PULSE_DURATION = auto()
    LASER_AMPLITUDE = auto()

class WidthConvention(Enum):
    SIGMA_INTENSITY_RMS = auto()
    SIGMA_FIELD_RMS = auto()
    FWHM_INTENSITY = auto()
    W0_1E2 = auto()

class TimeConvention(Enum):
    SIGMA_INTENSITY_RMS = auto()
    FWHM_INTENSITY = auto()
    SIGMA_FIELD_RMS = auto()

class AmplitudeConvention(Enum):
    A0_PEAK = auto()
    A0_RMS = auto()
```

---

## 2. Quantity Wrapper (quantities.py)

Encapsulates value + unit + meaning + convention.

```python
from dataclasses import dataclass

@dataclass
class PhysicalQuantity:
    value: float
    unit: str
    meaning: PhysicalMeaning
    convention: Enum
```

Must support Pint Quantity internally.

---

## 3. Canonical Representation (canonical.py)

Define a **single canonical convention per physical meaning**.

Example:

```python
CANONICAL_CONVENTIONS = {
    PhysicalMeaning.LASER_WIDTH: WidthConvention.SIGMA_INTENSITY_RMS,
    PhysicalMeaning.PULSE_DURATION: TimeConvention.SIGMA_INTENSITY_RMS,
    PhysicalMeaning.LASER_AMPLITUDE: AmplitudeConvention.A0_PEAK,
}
```

Provide:

```python
def to_canonical(quantity: PhysicalQuantity) -> PhysicalQuantity
def from_canonical(quantity: PhysicalQuantity, target_convention) -> PhysicalQuantity
```

---

## 4. Conversion Engine (converters.py)

Implement explicit transformations.

### Gaussian width conversions

```python
import numpy as np

def fwhm_to_sigma_intensity(fwhm):
    return fwhm / (2 * np.sqrt(2 * np.log(2)))

def sigma_field_to_sigma_intensity(sigma_field):
    return sigma_field / np.sqrt(2)

def w0_to_sigma_intensity(w0):
    return w0 / 2
```

Provide unified interface:

```python
def convert_width(value, from_conv, to_conv):
    # route via canonical
```

Same for time and amplitude.

---

## 5. Schema Definition (schema.py)

Each model must expose a schema.

```python
from dataclasses import dataclass

@dataclass
class ParameterSpec:
    name: str
    meaning: PhysicalMeaning
    convention: Enum
    unit: str
    description: str
```

A model defines:

```python
MODEL_SPEC = {
    "sigma": ParameterSpec(...),
    "tau": ParameterSpec(...),
    "a0": ParameterSpec(...),
}
```

---

## 6. Validation (validation.py)

```python
def validate_quantity(q: PhysicalQuantity):
    assert q.meaning is not None
    assert q.convention is not None

def validate_against_spec(params, spec):
    for key, pspec in spec.items():
        assert key in params
        assert params[key].meaning == pspec.meaning
```

Fail fast on any mismatch.

---

## 7. GUI Integration

### GUI must:

1. Accept user input with:

   * value
   * unit
   * convention (dropdown)

2. Construct `PhysicalQuantity`

Example:

```python
PhysicalQuantity(
    value=5,
    unit="micrometer",
    meaning=PhysicalMeaning.LASER_WIDTH,
    convention=WidthConvention.FWHM_INTENSITY
)
```

3. Convert to canonical:

```python
q_canonical = to_canonical(q)
```

4. When model selected:

   * Load `MODEL_SPEC`
   * Convert canonical → model convention

---

## 8. Model Code Changes

Each model MUST:

### A. Provide schema

```python
def get_model_spec():
    return MODEL_SPEC
```

OR:

```python
class Model:
    spec = MODEL_SPEC
```

---

### B. Accept normalized inputs only

```python
def run(params):
    sigma = params["sigma"]  # already converted
```

No internal conversion logic allowed.

---

### C. Document parameters (mandatory)

Each parameter must include:

* Physical meaning
* Mathematical definition
* Convention
* Units

Example:

```
sigma:
    RMS width of intensity profile:
    I(r) ∝ exp(-r² / (2σ²))
```

---

## 9. Adapter Layer

Implement per-model adapter:

```python
def adapt_to_model(canonical_params, model_spec):
    result = {}
    for name, spec in model_spec.items():
        q = canonical_params[name]
        result[name] = from_canonical(q, spec.convention)
    return result
```

---

## 10. Error Handling

Raise explicit errors for:

* Missing convention
* Unknown conversion
* Unit mismatch
* Meaning mismatch

Never silently convert.

---

## 11. Extensibility

To add new parameter types:

1. Add new `PhysicalMeaning`
2. Add corresponding conventions enum
3. Implement conversions
4. Register canonical mapping

---

## 12. Non-Goals

* No implicit guessing of conventions
* No reliance on variable names
* No parsing of docstrings for logic

---

## Summary

This system enforces:

* **Explicit semantics**
* **Centralized conversions**
* **Canonical normalization**
* **Self-describing models**

Result: no ambiguity, no hidden mismatches, and safe interoperability between independently developed simulation codes.

---

## Implementation Priority

1. Enums + Quantity class
2. Canonical mapping
3. Conversion engine
4. Model schema
5. Adapter
6. GUI integration
7. Validation

---

## Expected Outcome

* GUI can safely drive any model
* Models become plug-and-play
* Physical correctness is enforced at runtime
* Convention mismatches are eliminated

---

## Implementation note (post-hoc)

Implemented in two layers now, not one. The framework itself (enums,
quantities, canonical, converters, validation, schema, adapter, units --
sections 1-10 above) plus physical constants live in a separate shared
sibling repo, `compton_suite`, imported by every consumer (this GUI,
`xigma_i`, and -- for constants only so far -- `kascade`) via the same
content-based sys.path bootstrap this repo already used for `kascade`/
`xigma_i` discovery. `src/compton_guide/physics_params/` and
`physics_constants.py` are now thin re-export shims over
`compton_suite`, not independent definitions.

Section 8A's "each model MUST provide a schema" has been taken further
than a `get_model_spec()` function: xigma-i's `ModelSpec` (`XIGMA_SPEC`)
lives inside that model's own repo, as `xigma_i.params` -- the model owns
its schema directly rather than the GUI declaring it on the model's
behalf, built on top of `compton_suite`'s shared framework rather than a
copy of it. `kascade` hasn't had the same schema-ownership move yet, so
`schemas/kascade.py`'s `KASCADE_SPEC` still lives here (also built on
`compton_suite` directly, not a local copy).

This resolves an earlier intermediate state where `xigma_i` had its own
full copy of the framework (structurally identical to this repo's, but
not the same Python classes) -- `compton_suite` exists specifically so
that never has to happen again. See this repo's `CLAUDE.md` ("Parameter
semantics & units") and `compton_suite`'s own `CLAUDE.md` for the
up-to-date picture.
