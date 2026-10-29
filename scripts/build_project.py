"""Evaluate the notebooks of an example project into doc/gallery/<project>/.

Usage:
    python scripts/build_project.py attractors

Run it outside of the project environment: it calls ``pixi run`` to prepare
the project and to execute each notebook with the project's own ``python3``
kernel.

    - The ``download`` and ``pre`` tasks are run when defined.
    - Notebooks listed in ``[tool.metadata].notebooks_to_skip`` are ignored.
    - With ``[tool.metadata].skip_notebooks_evaluation = true`` the notebooks
      are copied without being evaluated.
"""

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent

PROJECT_FILE = "pixi.toml"

GALLERY = ROOT / "doc" / "gallery"

PREPARE_TASKS = ["download", "pre"]

NOTEBOOK_EVALUATION_TIMEOUT = 3600  # in seconds.


def find_notebooks(project_dir, metadata):
    skip = set(metadata.get("notebooks_to_skip", []))
    return sorted(p for p in project_dir.glob("*.ipynb") if p.name not in skip)


def pixi_run(project_dir, *args):
    cmd = ["pixi", "run", "--manifest-path", str(project_dir / PROJECT_FILE), *args]
    print("+", " ".join(cmd), flush=True)
    # Progress bars render badly on the website.
    env = {**os.environ, "INTAKE_CACHE_PROGRESS": "false"}
    subprocess.run(cmd, cwd=project_dir, env=env, check=True)


def build_project(name):
    project_dir = ROOT / name
    with open(project_dir / PROJECT_FILE, "rb") as f:
        spec = tomllib.load(f)
    metadata = spec.get("tool", {}).get("metadata", {})
    tasks = spec.get("tasks", {})

    notebooks = find_notebooks(project_dir, metadata)
    out_dir = GALLERY / name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    if metadata.get("skip_notebooks_evaluation", False):
        for notebook in notebooks:
            print(f"Copying notebook {notebook} to {out_dir}")
            shutil.copyfile(notebook, out_dir / notebook.name)
        return

    for task in PREPARE_TASKS:
        if task in tasks:
            pixi_run(project_dir, task)

    for notebook in notebooks:
        pixi_run(
            project_dir,
            "jupyter",
            "nbconvert",
            "--to=notebook",
            "--execute",
            f"--ExecutePreprocessor.timeout={NOTEBOOK_EVALUATION_TIMEOUT}",
            "--ExecutePreprocessor.kernel_name=python3",
            f"--output-dir={out_dir}",
            notebook.name,
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="Project name to build.")
    args = parser.parse_args(argv)

    if not (ROOT / args.project / PROJECT_FILE).is_file():
        parser.error(f"Missing {PROJECT_FILE} file in {args.project!r}")
    build_project(args.project)


if __name__ == "__main__":
    sys.exit(main())
