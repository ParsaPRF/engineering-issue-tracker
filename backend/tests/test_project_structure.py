"""Repository-level structural tests.

These are not business tests; they guard a class of mistake that cost real debugging time during this
project: a **directory and a module with the same name in the same package**. Python prefers the
package, so ``apps/workflows/services/`` (even containing only ``__init__.py``) silently shadowed
``apps/workflows/services.py`` and produced ``ImportError: cannot import name ...`` at runtime, with a
traceback pointing at the *caller* rather than the cause.

A one-second test is a cheaper guard than remembering the rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APPS_ROOT = BACKEND_ROOT / "apps"


def _package_dirs() -> list[Path]:
    """Every package directory under ``apps/`` that also has a sibling module of the same name."""
    collisions: list[Path] = []
    for module_file in APPS_ROOT.glob("*/*.py"):
        candidate = module_file.with_suffix("")  # apps/<app>/<name>.py -> apps/<app>/<name>
        init = candidate / "__init__.py"
        if init.exists() and module_file.name != "__init__.py":
            collisions.append(candidate)
    return collisions


def test_no_module_is_shadowed_by_a_same_named_package():
    collisions = _package_dirs()

    assert collisions == [], (
        "These paths exist both as a module and as a package, so the package wins at import time:\n"
        + "\n".join(str(path) for path in collisions)
    )


def test_every_app_has_an_app_config():
    for app_dir in sorted(path for path in APPS_ROOT.iterdir() if path.is_dir()):
        if app_dir.name.startswith("__"):
            continue
        assert (app_dir / "apps.py").exists(), f"{app_dir.name} has no apps.py"


def test_every_app_with_models_has_a_migrations_package():
    for app_dir in sorted(path for path in APPS_ROOT.iterdir() if path.is_dir()):
        if app_dir.name.startswith("__"):
            continue
        has_models = (app_dir / "models.py").exists() or (app_dir / "models").is_dir()
        if has_models:
            assert (app_dir / "migrations" / "__init__.py").exists(), (
                f"{app_dir.name} defines models but has no migrations package"
            )


@pytest.mark.parametrize("app_name", ["accounts", "projects", "tickets", "workflows", "comments", "attachments", "notifications", "audit", "reports"])
def test_expected_apps_exist(app_name):
    assert (APPS_ROOT / app_name / "__init__.py").exists()