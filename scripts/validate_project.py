"""Validate the pixi.toml file of one or more example projects.

Usage:
    python scripts/validate_project.py attractors boids
        Validate the given projects.

    python scripts/validate_project.py
        Validate every project.

Ported from the ``validate_project_file`` doit task, adapted to pixi:
    - ``name``/``channels``/``platforms``  -> ``[workspace]``
    - ``packages``/``dependencies``        -> ``[dependencies]``
    - ``commands``                         -> ``[tasks]``
    - ``examples_config`` + ``description`` -> ``[tool.metadata]``

By default a problem is reported as a WARNING and does not fail the run.
Set the ``EXAMPLES_HOLOVIZ_WARNING_AS_ERROR`` environment variable to turn
WARNING-level problems into failures (INFO-level messages never fail).
"""

import argparse
import datetime
import os
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent

PROJECT_FILE = "pixi.toml"

# Allowed website categories (from CATNAME_TO_CAT_MAP in dodo.py).
ALLOWED_CATEGORIES = [
    "Featured",
    "Geospatial",
    "Finance",
    "Economics",
    "Mathematics",
    "Neuroscience",
    "Cybersecurity",
    "Networks",
    "Other Sciences",
    "Sports",
]

ALLOWED_RUNNERS = ["ubuntu-latest", "macos-latest", "windows-latest"]

REQUIRED_METADATA = ["created", "maintainers", "labels", "categories", "description"]
OPTIONAL_METADATA = [
    "title",
    "data_version",
    "gh_runner",
    "no_data_ingestion",
    "skip_notebooks_evaluation",
    "skip_test",
    "notebooks_to_skip",
]


class ValidationError(Exception):
    """A project failed validation (only raised in warning-as-error mode)."""


def _warning_as_error():
    return os.getenv("EXAMPLES_HOLOVIZ_WARNING_AS_ERROR") is not None


def _task_cmd(value):
    """Return the command string of a pixi task (str or table form)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("cmd", "")
    return ""


def validate_project(name):
    """Validate ``<name>/pixi.toml``. Return a list of problem messages.

    Messages are prefixed with ``WARNING:`` or ``INFO:``. In warning-as-error
    mode a WARNING raises ValidationError instead of being collected.
    """
    problems = []

    def complain(msg, level="WARNING"):
        if level == "WARNING" and _warning_as_error():
            raise ValidationError(msg)
        problems.append(f"{level}: {msg}")

    project = ROOT / name / PROJECT_FILE
    if not project.is_file():
        raise FileNotFoundError(f"Missing {PROJECT_FILE} file in {name!r}")

    with open(project, "rb") as f:
        try:
            spec = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValidationError(f"{name}: invalid pixi.toml content") from e

    workspace = spec.get("workspace", {})
    metadata = spec.get("tool", {}).get("metadata", {})
    tasks = spec.get("tasks", {})

    # Required top-level tables.
    if "workspace" not in spec:
        complain("Missing '[workspace]' table")
    for entry in ("channels", "platforms"):
        if entry not in workspace:
            complain(f"Missing 'workspace.{entry}' entry")
    for entry in ("dependencies", "tasks", "environments"):
        if entry not in spec:
            complain(f"Missing '[{entry}]' table")
    if "metadata" not in spec.get("tool", {}):
        complain("Missing '[tool.metadata]' table")

    # Project name.
    project_name = workspace.get("name", "")
    if project_name != name:
        complain(
            f"Project `name` {project_name!r} does not match the directory name {name}"
        )
    if not project_name.replace("_", "").isalnum():
        complain(
            f"Project `name` {project_name!r} must only have lower-cased letters "
            "and underscores"
        )

    # Task conventions.
    if "lint" in tasks:
        complain(
            "Linting is done by the system and should not be defined on "
            "a per-project basis, please remove the `lint` task."
        )
    if "test" in tasks:
        complain(
            "Found a top-level `test` task. Tests are run remotely by nbval, "
            "and a custom test should live under `[feature.test.tasks]`.",
            level="INFO",
        )

    serve_tasks = {
        cmd: _task_cmd(value)
        for cmd, value in tasks.items()
        if any(served in _task_cmd(value) for served in ("panel serve", "lumen serve"))
    }
    if serve_tasks and "dashboard" not in serve_tasks:
        complain(
            f"Tasks serving Panel/Lumen apps must be called `dashboard`, "
            f"not {list(serve_tasks)}"
        )
    dashboard_cmd = serve_tasks.get("dashboard")
    if dashboard_cmd and (
        "--rest-session-info" not in dashboard_cmd
        or "--session-history -1" not in dashboard_cmd
    ):
        complain(
            "dashboard task serving Panel/Lumen apps must set "
            '"--rest-session-info --session-history -1"'
        )

    # Metadata lists.
    for entry in ("maintainers", "labels", "categories"):
        if entry not in metadata:
            complain(f"missing {entry!r} list")
            continue
        value = metadata[entry]
        if not isinstance(value, list):
            complain(f"{entry!r} must be a list")
            continue
        if not all(isinstance(item, str) for item in value):
            complain(f"all values of {value!r} must be a string")
        if entry == "categories":
            allowed = [c.lower() for c in ALLOWED_CATEGORIES]
            for cat in value:
                if cat.lower() not in allowed:
                    complain(
                        "Category must be one of the allowed categories "
                        f"{ALLOWED_CATEGORIES}, not {cat}."
                    )

    # created / description.
    created = metadata.get("created")
    if created is None:
        complain("`created` entry not found")
    elif isinstance(created, datetime.date):
        pass
    elif isinstance(created, str):
        try:
            datetime.date.fromisoformat(created)
        except ValueError:
            complain("`created` value must be a date expressed as YYYY-MM-DD")
    else:
        complain("`created` value must be a date expressed as YYYY-MM-DD")

    if "description" not in metadata:
        complain("`description` entry not found")
    elif not isinstance(metadata["description"], str):
        complain("`description` value must be a string")

    # Optional typed fields.
    title = metadata.get("title")
    if title is not None and not isinstance(title, str):
        complain("`title` value must be a string")

    for entry in ("no_data_ingestion", "skip_notebooks_evaluation", "skip_test"):
        value = metadata.get(entry)
        if value is not None and not isinstance(value, bool):
            complain(f"`{entry}` must be a boolean, not {value}")

    notebooks_to_skip = metadata.get("notebooks_to_skip")
    if notebooks_to_skip is not None and (
        not isinstance(notebooks_to_skip, list)
        or not all(isinstance(item, str) for item in notebooks_to_skip)
    ):
        complain("`notebooks_to_skip` must be a list of strings")

    gh_runner = metadata.get("gh_runner")
    if gh_runner is not None and gh_runner not in ALLOWED_RUNNERS:
        complain(f"`gh_runner` must be one of {ALLOWED_RUNNERS}")

    # Unexpected metadata keys.
    allowed_metadata = REQUIRED_METADATA + OPTIONAL_METADATA
    for key in metadata:
        if key not in allowed_metadata:
            complain(f"Unexpected entry {key!r} found in `[tool.metadata]`")

    return problems


def all_project_names():
    return sorted(
        path.name
        for path in ROOT.iterdir()
        if path.is_dir() and (path / PROJECT_FILE).is_file()
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "projects",
        nargs="*",
        help="Project names to validate (default: all projects).",
    )
    args = parser.parse_args(argv)

    projects = args.projects or all_project_names()

    failed = False
    for name in projects:
        try:
            problems = validate_project(name)
        except (ValidationError, FileNotFoundError) as e:
            print(f"{name}: FAILED\n  {e}")
            failed = True
            continue
        if problems:
            print(f"{name}:")
            for problem in problems:
                print(f"  {problem}")
        else:
            print(f"{name}: OK")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
