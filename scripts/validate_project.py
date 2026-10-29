"""Validate one or more example projects.

Usage:
    python scripts/validate_project.py attractors boids
        Validate the given projects.

    python scripts/validate_project.py
        Validate every project.

Checks ``[workspace]`` (name, channels, platforms), ``[dependencies]``,
``[tasks]``, ``[environments]`` and the website metadata in ``[tool.metadata]``
of ``pixi.toml``, that ``pixi.lock`` is tracked, then the notebooks (index
notebook, 1st level heading, cleared outputs), the gallery thumbnail and the
data sources.

By default a problem is reported as a WARNING and does not fail the run.
Set the ``EXAMPLES_HOLOVIZ_WARNING_AS_ERROR`` environment variable to turn
WARNING-level problems into failures (INFO-level messages never fail).
"""

import argparse
import datetime
import json
import os
import pathlib
import struct
import subprocess
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent

PROJECT_FILE = "pixi.toml"

# Allowed website categories, as in CATNAME_TO_CAT_MAP in _extensions/gallery_utils.py.
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

REQUIRED_METADATA = ["created", "maintainers", "labels", "categories", "description"]
OPTIONAL_METADATA = [
    "title",
    "data_version",
    "no_data_ingestion",
    "skip_notebooks_evaluation",
    "notebooks_to_skip",
]

THUMBNAIL_MAX_MB = 1
THUMBNAIL_ASPECT_RATIO = (0.9, 1.5)


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

    if not _tracked_files(ROOT / name / "pixi.lock"):
        complain("Missing tracked pixi.lock file")

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

    for entry in ("no_data_ingestion", "skip_notebooks_evaluation"):
        value = metadata.get(entry)
        if value is not None and not isinstance(value, bool):
            complain(f"`{entry}` must be a boolean, not {value}")

    notebooks_to_skip = metadata.get("notebooks_to_skip")
    if notebooks_to_skip is not None and (
        not isinstance(notebooks_to_skip, list)
        or not all(isinstance(item, str) for item in notebooks_to_skip)
    ):
        complain("`notebooks_to_skip` must be a list of strings")

    # Unexpected metadata keys.
    allowed_metadata = REQUIRED_METADATA + OPTIONAL_METADATA
    for key in metadata:
        if key not in allowed_metadata:
            complain(f"Unexpected entry {key!r} found in `[tool.metadata]`")

    notebooks = _find_notebooks(name, metadata)
    _validate_notebooks(name, notebooks, metadata, complain)
    _validate_thumbnail(name, notebooks, complain)
    _validate_data_sources(name, spec, complain)

    return problems


def _tracked_files(path):
    """Return the files under ``path`` tracked by git, relative to the repo root."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / f for f in out.split("\0") if f]


def _find_notebooks(name, metadata):
    """Return the displayed notebooks of a project, skipping `notebooks_to_skip`."""
    skip = metadata.get("notebooks_to_skip", [])
    return sorted(
        nb for nb in (ROOT / name).glob("*.ipynb") if nb.name not in skip
    )


def _read_notebook(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _cell_source(cell):
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else source


def _validate_notebooks(name, notebooks, metadata, complain):
    """Check the index notebook, the headers and the code cell outputs."""
    if not notebooks:
        complain("Project has no notebooks")
        return
    if len(notebooks) == 1:
        if notebooks[0].stem != name:
            complain(
                f"Unique displayed notebook {notebooks[0].name!r} does not "
                f"match the directory name {name}."
            )
    elif not any(nb.stem == "index" for nb in notebooks):
        complain("Project has multiple notebooks but no index.ipynb")

    skip_evaluation = metadata.get("skip_notebooks_evaluation", False)
    for path in notebooks:
        cells = _read_notebook(path).get("cells", [])
        if not cells or not _cell_source(cells[0]).startswith("# "):
            complain(
                f"{path.name} must start with a 1st level heading e.g. '# A title'"
            )
        code_cells = [cell for cell in cells if cell["cell_type"] == "code"]
        if not code_cells:
            continue
        has_outputs = any(cell.get("outputs") for cell in code_cells)
        if not skip_evaluation and has_outputs:
            complain(
                f"{path.name} must not contain any code cell outputs, please clear it."
            )
        elif skip_evaluation and not has_outputs:
            complain(f"{path.name} should contain code cell outputs.")


def _png_dims(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) != 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">ii", head[16:24])


def _validate_thumbnail(name, notebooks, complain):
    """Check the thumbnail of the notebook shown in the gallery."""
    if len(notebooks) > 1:
        notebooks = [nb for nb in notebooks if nb.stem == "index"]
    if not notebooks:
        return
    thumb = ROOT / name / "thumbnails" / f"{notebooks[0].stem}.png"
    if not thumb.is_file():
        complain(f"Missing PNG thumbnail thumbnails/{thumb.name}")
        return
    size = thumb.stat().st_size * 1e-6
    if size > THUMBNAIL_MAX_MB:
        complain(f"Thumbnail size ({size:.2f} MB) is above {THUMBNAIL_MAX_MB}MB")
    dims = _png_dims(thumb)
    if dims is None:
        complain(f"Thumbnail thumbnails/{thumb.name} is not a valid PNG file")
        return
    aspect_ratio = dims[0] / dims[1]
    low, high = THUMBNAIL_ASPECT_RATIO
    if not low <= aspect_ratio <= high:
        complain(
            f"Thumbnail aspect ratio ({aspect_ratio:.2f}) must be between {low} and {high}"
        )


def _is_intake_catalog(path):
    with open(path, encoding="utf-8") as f:
        return any(line.startswith("sources:") for line in f)


def _validate_data_sources(name, spec, complain):
    """Check that the project declares where its data comes from.

    A project gets its data from a ``download`` task, an Intake catalog or a
    committed ``data/`` folder, or sets ``no_data_ingestion = true``.
    """
    project_dir = ROOT / name
    tasks = spec.get("tasks", {})
    metadata = spec.get("tool", {}).get("metadata", {})

    download_tasks = {
        task: value
        for task, value in tasks.items()
        if task == "download" or task.startswith("download-")
    }
    for task, value in download_tasks.items():
        outputs = value.get("outputs", []) if isinstance(value, dict) else []
        for output in outputs:
            if output != "data" and not output.startswith("data/"):
                complain(f"`{task}` task output {output!r} must be in the data/ folder")

    catalogs = [
        path
        for path in _tracked_files(project_dir)
        if path.suffix in (".yml", ".yaml") and _is_intake_catalog(path)
    ]
    for path in catalogs:
        if path != project_dir / "catalog.yml":
            complain(
                f"Intake catalog must be saved at '{name}/catalog.yml', "
                f"not at '{path.relative_to(ROOT)}'."
            )
    if catalogs and spec.get("activation", {}).get("env", {}).get(
        "INTAKE_CACHE_DIR"
    ) != "data":
        complain(
            "The project has an Intake catalog, it must set INTAKE_CACHE_DIR "
            "to 'data' in `[activation.env]`."
        )

    has_data_folder = bool(_tracked_files(project_dir / "data"))
    has_source = bool(download_tasks or catalogs or has_data_folder)
    no_data_ingestion = metadata.get("no_data_ingestion", False)
    if has_source and no_data_ingestion:
        complain(
            "The project sets `no_data_ingestion` to true but has a download "
            "task, an Intake catalog or a data/ folder."
        )
    if not has_source and not no_data_ingestion:
        complain("The project does not define its data sources.")


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
