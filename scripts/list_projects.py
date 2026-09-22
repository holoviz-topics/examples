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

        --exclude-website-metadata
            Ignore display-only [tool.metadata] changes in pixi.toml, so a
            project is not marked changed when only website metadata changed.
        --exclude-deployments-metadata
            Ignore [tasks] changes in pixi.toml (the deployment commands).
        --only-project-file
            Only consider changes to pixi.toml files (ignore other files).
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

# Deployment commands: changing them should trigger a redeploy but not
# test/build/doc.
IGNORE_KEYS_DEPLOYMENTS = [
    "tasks",
]


def all_project_names():
    projects = [
        path.name
        for path in ROOT.iterdir()
        if path.is_dir() and (path / PROJECT_FILE).is_file()
    ]
    return sorted(projects)


def _git(args):
    result = subprocess.run(
        ["git", *args], stdout=subprocess.PIPE, cwd=ROOT, check=False
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


def _project_file_meaningfully_changed(rel_path, merge_base, ignored_keys):
    """Whether pixi.toml changed vs merge_base, ignoring the given keys."""
    with open(ROOT / rel_path, "rb") as fh:
        current = tomllib.load(fh)
    previous_text = _git(["show", f"{merge_base}:{rel_path}"])
    previous = tomllib.loads(previous_text) if previous_text.strip() else {}
    current = _strip_keys(current, ignored_keys)
    previous = _strip_keys(previous, ignored_keys)
    return current != previous


def changed_projects(
    exclude_website_metadata, exclude_deployments_metadata, only_project_file
):
    _git(["fetch", "origin", "main"])
    merge_base = _git(["merge-base", "origin/main", "HEAD"]).strip()

    files = _git(["diff", "--name-only", merge_base]).splitlines()
    prev_files = set(_git(["ls-tree", "-r", merge_base, "--name-only"]).splitlines())

    current_projects = set(all_project_names())
    prev_projects = {
        pathlib.Path(f).parts[0]
        for f in prev_files
        if pathlib.Path(f).name == PROJECT_FILE and len(pathlib.Path(f).parts) == 2
    }

    ignored_keys = []
    if not only_project_file:
        if exclude_website_metadata:
            ignored_keys.extend(IGNORE_KEYS_WEBSITE)
        if exclude_deployments_metadata:
            ignored_keys.extend(IGNORE_KEYS_DEPLOYMENTS)

    changed = set()
    for f in files:
        path = pathlib.Path(f)
        if not path.parts:
            continue
        root = path.parts[0]
        if root not in current_projects:
            continue
        is_project_file = path.name == PROJECT_FILE and len(path.parts) == 2
        if only_project_file and not is_project_file:
            continue
        if is_project_file:
            if f not in prev_files or _project_file_meaningfully_changed(
                f, merge_base, ignored_keys
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
        "--exclude-website-metadata",
        action="store_true",
        help="With --changed, ignore display-only [tool.metadata] changes.",
    )
    parser.add_argument(
        "--exclude-deployments-metadata",
        action="store_true",
        help="With --changed, ignore [tasks] (deployment command) changes.",
    )
    parser.add_argument(
        "--only-project-file",
        action="store_true",
        help="With --changed, only consider changes to pixi.toml files.",
    )
    args = parser.parse_args(argv)

    if args.changed:
        if args.projects:
            parser.error("--projects cannot be combined with --changed")
        print(
            json.dumps(
                changed_projects(
                    args.exclude_website_metadata,
                    args.exclude_deployments_metadata,
                    args.only_project_file,
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
