"""sys.path wiring so ``compton_guide`` can import ``kascade``, ``xigma_i``,
and ``compton_suite`` without any of them being pip-installed.

These packages currently live in locations that aren't stable
package-manager paths: ``kascade`` is a loose script directory
(``MC-Kost/``, sibling of this project) with no packaging at all,
``xigma_i`` lives in a sibling checkout whose directory name and exact
path are not stable across machines -- e.g. it may be a plain repo clone
on one machine and a git-worktree checkout on another, under whatever
name that machine's checkout happens to have (this has already changed
once, when ``xigma_i``'s GUI adapter moved out of a git worktree and into
that repo's ``main`` branch) -- and ``compton_suite`` (shared physical
constants, pint registry, parameter-convention framework) is a newer
sibling repo with the same instability risk despite being deliberately
created rather than historically drifted. A hardcoded ``pyproject.toml``
path-dependency, or even a hardcoded sibling directory *name*, would
break on the next machine or the next reorganization -- so this is a
runtime ``sys.path`` bootstrap that autodiscovers all three locations by
content (looking for a marker file inside each candidate sibling
directory) rather than by name, with all three still overridable via
environment variables for anyone whose checkout layout doesn't match
autodiscovery at all (e.g. it lives outside ``_XIGMA_ROOT`` entirely).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
# .../compton-gui/src/compton_guide -> .../compton-gui -> .../XIGMA (sibling dir)
_XIGMA_ROOT = _THIS_DIR.parents[2]

# Marker files used to recognize each physics package among _XIGMA_ROOT's
# sibling directories, relative to the sibling directory itself.
_KASCADE_MARKER = "kascade.py"
_XIGMA_MARKER = "src/xigma_i/gui_adapter.py"
_COMPTON_SUITE_MARKER = "src/compton_suite/constants.py"


def _find_siblings(root: Path, marker: str) -> list[Path]:
    """Sibling directories of this project (children of ``root``) that
    contain ``marker``, sorted by name for a deterministic pick among
    ties."""
    if not root.is_dir():
        return []
    return sorted(
        entry for entry in root.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
        and (entry / marker).exists()
    )


def _discover(root: Path, marker: str, env_var: str) -> Path | None:
    """A candidate sibling directory containing ``marker``, or ``None``.
    Warns (but does not fail) if more than one match is found -- pin the
    right one via ``env_var`` in that case."""
    matches = _find_siblings(root, marker)
    if not matches:
        return None
    if len(matches) > 1:
        print(
            f"compton_guide.bootstrap: multiple candidates found under {root} "
            f"(all contain {marker!r}): {[str(m) for m in matches]}; using "
            f"{matches[0]} -- set {env_var} to pin a specific one.",
            file=sys.stderr,
        )
    return matches[0]


def setup_paths() -> None:
    """Insert the kascade, xigma_i, and compton_suite source directories
    into ``sys.path`` if they aren't already importable. Safe to call more
    than once.

    Resolution order for each, highest priority first:
      1. The relevant ``COMPTON_GUIDE_*`` environment variable, if set --
         used verbatim, no autodiscovery, for checkouts autodiscovery
         can't find (e.g. outside ``_XIGMA_ROOT``).
      2. Autodiscovery: the (alphabetically first, if several) sibling of
         this project containing the package's marker file.

    Never raises -- kascade/xigma_i are optional physics engines (a
    missing one just greys out a GUI menu entry), so a warning to stderr
    is enough. ``compton_suite`` is *not* optional for anything that
    actually imports it (``physics_params``/``physics_constants``), but
    the natural ``ImportError`` those imports raise on their own if
    ``compton_suite`` isn't on ``sys.path`` already does the "fail loudly"
    job -- this function's contract (never raises) stays uniform across
    all three targets.
    """
    kascade_override = os.environ.get("COMPTON_GUIDE_KASCADE_PATH")
    kascade_path = (
        Path(kascade_override) if kascade_override
        else _discover(_XIGMA_ROOT, _KASCADE_MARKER, "COMPTON_GUIDE_KASCADE_PATH")
    )

    xigma_override = os.environ.get("COMPTON_GUIDE_XIGMA_SRC")
    xigma_src = (
        Path(xigma_override) if xigma_override
        else (lambda d: d / "src" if d is not None else None)(
            _discover(_XIGMA_ROOT, _XIGMA_MARKER, "COMPTON_GUIDE_XIGMA_SRC")
        )
    )

    compton_suite_override = os.environ.get("COMPTON_GUIDE_COMPTON_SUITE_SRC")
    compton_suite_src = (
        Path(compton_suite_override) if compton_suite_override
        else (lambda d: d / "src" if d is not None else None)(
            _discover(_XIGMA_ROOT, _COMPTON_SUITE_MARKER, "COMPTON_GUIDE_COMPTON_SUITE_SRC")
        )
    )

    for p, label, env_var in (
        (kascade_path, "kascade", "COMPTON_GUIDE_KASCADE_PATH"),
        (xigma_src, "xigma_i", "COMPTON_GUIDE_XIGMA_SRC"),
        (compton_suite_src, "compton_suite", "COMPTON_GUIDE_COMPTON_SUITE_SRC"),
    ):
        if p is None:
            print(
                f"compton_guide.bootstrap: could not find {label} under "
                f"{_XIGMA_ROOT} -- set {env_var} to its location if it's "
                f"installed elsewhere.",
                file=sys.stderr,
            )
            continue
        p_str = str(p)
        if p.is_dir() and p_str not in sys.path:
            sys.path.insert(0, p_str)
