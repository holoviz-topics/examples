"""List pixi example projects as JSON, for use in CI matrices.

A project is any top-level directory that contains a ``pixi.toml`` file.

Usage:
    python scripts/list_projects.py
        Print all projects as a JSON array.

    python scripts/list_projects.py --projects attractors,boids
        Print the given comma-separated projects, after checking each exists.

    python scripts/list_projects.py --changed
        Print {"changed": [...], "removed": [...]} for projects that changed
        compared to origin/main. New projects appear in "changed"; projects
        whose pixi.toml no longer exists appear in "removed".

        --last-commit
            Compare HEAD with HEAD^ instead of origin/main (used on main
            after a PR is merged).
        --exclude-website-metadata
            Ignore display-only [tool.metadata] changes in pixi.toml, so a
            project is not marked changed when only website metadata changed.
        --exclude-deployments-metadata
            Ignore changes to [tasks] in pixi.toml, except the tasks needed to
            test or build the project (see BUILD_TASKS).
        --only-project-file
            Only consider changes to pixi.toml files (ignore other files).
        --exclude-test-data
            Do not mark a project changed when only test_data/<project> changed.
"""

import argparse
import json
import pathlib
import subprocess
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent

PROJECT_FILE = "pixi.toml"

# Display-only [tool.metadata] keys: changing them affects the website but not
# the test/build of a project.
IGNORE_KEYS_WEBSITE = [
    "tool.metadata.description",
    "tool.metadata.created",
    "tool.metadata.maintainers",
    "tool.metadata.labels",
    "tool.metadata.title",
    "tool.metadata.categories",
]

# Tasks run by CI to test/build a project. They, and the tasks they depend
# on, are never treated as deployment-only metadata.
BUILD_TASKS = ["download", "pre", "pre-build"]

TEST_DATA_DIR = "test_data"


def all_project_names():
    projects = [
        path.name
        for path in ROOT.iterdir()
        if path.is_dir() and (path / PROJECT_FILE).is_file()
    ]
    return sorted(projects)


def _git(args):
    result = subprocess.run(
        ["git", *args], stdout=subprocess.PIPE, cwd=ROOT, check=True
    )
    return result.stdout.decode()


def _remove_nested_key(mapping, ref):
    """Delete a dotted key path from a nested dict, in place.

    >>> d = {'a': 1, 'b': {'c': 3, 'd': 4}}
    >>> _remove_nested_key(d, 'b.d')
    {'a': 1, 'b': {'c': 3}}
    """
    parts = ref.split(".")
    obj = mapping
    for i, key in enumerate(parts, 1):
        if not isinstance(obj, dict) or key not in obj:
            break
        if i == len(parts):
            del obj[key]
        else:
            obj = obj[key]
    return mapping


def _strip_keys(mapping, ignored_keys):
    for key in ignored_keys:
        _remove_nested_key(mapping, key)
    return mapping


def _task_dependencies(task):
    if not isinstance(task, dict):
        return []
    deps = task.get("depends-on", [])
    if isinstance(deps, str):
        deps = [deps]
    return [dep["task"] if isinstance(dep, dict) else dep for dep in deps]


def _strip_deployment_tasks(spec):
    """Drop the tasks not reachable from BUILD_TASKS, in place.

    >>> spec = {"tasks": {
    ...     "download": {"cmd": "curl", "depends-on": ["mkdir"]},
    ...     "mkdir": "mkdir -p data",
    ...     "dashboard": {"cmd": "panel serve", "depends-on": ["download"]},
    ... }}
    >>> sorted(_strip_deployment_tasks(spec)["tasks"])
    ['download', 'mkdir']
    """
    tasks = spec.get("tasks", {})
    keep = set()
    todo = [name for name in BUILD_TASKS if name in tasks]
    while todo:
        name = todo.pop()
        if name in keep:
            continue
        keep.add(name)
        todo.extend(dep for dep in _task_dependencies(tasks.get(name)) if dep in tasks)
    for name in list(tasks):
        if name not in keep:
            del tasks[name]
    return spec


def _project_file_meaningfully_changed(
    rel_path, base, ignored_keys, exclude_deployments_metadata
):
    """Whether pixi.toml changed vs base, ignoring the given keys."""
    with open(ROOT / rel_path, "rb") as fh:
        current = tomllib.load(fh)
    previous = tomllib.loads(_git(["show", f"{base}:{rel_path}"]))
    current = _strip_keys(current, ignored_keys)
    previous = _strip_keys(previous, ignored_keys)
    if exclude_deployments_metadata:
        current = _strip_deployment_tasks(current)
        previous = _strip_deployment_tasks(previous)
    return current != previous


def changed_projects(
    last_commit,
    exclude_website_metadata,
    exclude_deployments_metadata,
    only_project_file,
    exclude_test_data,
):
    if last_commit:
        base = _git(["rev-parse", "HEAD^"]).strip()
    else:
        _git(["fetch", "origin", "main"])
        base = _git(["merge-base", "origin/main", "HEAD"]).strip()

    files = _git(["diff", "--name-only", base]).splitlines()
    prev_files = set(_git(["ls-tree", "-r", base, "--name-only"]).splitlines())

    current_projects = set(all_project_names())
    prev_projects = {
        pathlib.Path(f).parts[0]
        for f in prev_files
        if pathlib.Path(f).name == PROJECT_FILE and len(pathlib.Path(f).parts) == 2
    }

    ignored_keys = []
    if only_project_file:
        exclude_deployments_metadata = False
    elif exclude_website_metadata:
        ignored_keys.extend(IGNORE_KEYS_WEBSITE)

    changed = set()
    for f in files:
        path = pathlib.Path(f)
        if not path.parts:
            continue
        root = path.parts[0]
        if root == TEST_DATA_DIR and len(path.parts) > 2:
            if not (exclude_test_data or only_project_file):
                if path.parts[1] in current_projects:
                    changed.add(path.parts[1])
            continue
        if root not in current_projects:
            continue
        is_project_file = path.name == PROJECT_FILE and len(path.parts) == 2
        if only_project_file and not is_project_file:
            continue
        if is_project_file:
            if f not in prev_files or _project_file_meaningfully_changed(
                f, base, ignored_keys, exclude_deployments_metadata
            ):
                changed.add(root)
        else:
            changed.add(root)

    removed = prev_projects - current_projects

    return {"changed": sorted(changed), "removed": sorted(removed)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--projects",
        help="Comma-separated list of project names to output (validated against existing projects).",
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Print projects changed/removed compared to origin/main.",
    )
    parser.add_argument(
        "--last-commit",
        action="store_true",
        help="With --changed, compare with HEAD^ instead of origin/main.",
    )
    parser.add_argument(
        "--exclude-website-metadata",
        action="store_true",
        help="With --changed, ignore display-only [tool.metadata] changes.",
    )
    parser.add_argument(
        "--exclude-deployments-metadata",
        action="store_true",
        help="With --changed, ignore [tasks] changes not needed to test/build.",
    )
    parser.add_argument(
        "--only-project-file",
        action="store_true",
        help="With --changed, only consider changes to pixi.toml files.",
    )
    parser.add_argument(
        "--exclude-test-data",
        action="store_true",
        help="With --changed, ignore changes in test_data/<project>.",
    )
    args = parser.parse_args(argv)

    if args.changed:
        if args.projects:
            parser.error("--projects cannot be combined with --changed")
        print(
            json.dumps(
                changed_projects(
                    args.last_commit,
                    args.exclude_website_metadata,
                    args.exclude_deployments_metadata,
                    args.only_project_file,
                    args.exclude_test_data,
                )
            )
        )
        return

    known = all_project_names()

    if args.projects:
        requested = [p.strip() for p in args.projects.split(",") if p.strip()]
        if not requested:
            parser.error("--projects was given but contained no project names")
        unknown = [p for p in requested if p not in known]
        if unknown:
            parser.error(
                f"Unknown project(s): {', '.join(unknown)}. "
                f"A project must be a top-level directory containing a {PROJECT_FILE}."
            )
        projects = requested
    else:
        projects = known

    print(json.dumps(projects))


if __name__ == "__main__":
    sys.exit(main())
