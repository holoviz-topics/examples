#!/usr/bin/env python
"""Post-process a converted pixi.toml (see convert-pixi.py): drop the osx-64
platform and add an nbval `test` environment (`pixi run -e test test`).

Edits are text surgery, not a TOML round-trip, to preserve convert-pixi's
inline `# promoted from ...` comments (and tomlkit is unavailable here).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import tomllib

if sys.stdout.isatty():
    GREEN, YELLOW, RESET = "\033[0;32m", "\033[0;33m", "\033[0m"
else:
    GREEN = YELLOW = RESET = ""

OSX64 = "osx-64"


def _table_header(line: str) -> bool:
    s = line.strip()
    return s.startswith("[") and s.endswith("]")


def _table_end(lines: list[str], start: int) -> int:
    # convert-pixi never puts a blank line inside a table.
    j = start + 1
    while j < len(lines) and lines[j].strip() != "" and not _table_header(lines[j]):
        j += 1
    return j


def _find_header(lines: list[str], header: str) -> int | None:
    for i, line in enumerate(lines):
        if line.strip() == header:
            return i
    return None


def remove_osx64_platform(lines: list[str]) -> bool:
    in_workspace = False
    for i, line in enumerate(lines):
        if _table_header(line):
            in_workspace = line.strip() == "[workspace]"
            continue
        if in_workspace and line.lstrip().startswith("platforms"):
            m = re.match(r"(\s*platforms\s*=\s*)\[(.*)\](.*)$", line)
            if not m:
                return False
            items = [x.strip() for x in m.group(2).split(",") if x.strip()]
            kept = [x for x in items if x.strip().strip('"') != OSX64]
            if len(kept) == len(items):
                return False
            lines[i] = f"{m.group(1)}[{', '.join(kept)}]{m.group(3)}"
            return True
    return False


def remove_table(lines: list[str], header: str) -> bool:
    i = _find_header(lines, header)
    if i is None:
        return False
    j = i + 1
    while j < len(lines) and not _table_header(lines[j]):
        j += 1
    del lines[i:j]
    return True


def project_has_test_data(project_dir: Path) -> bool:
    test_data = project_dir.parent / "test_data" / project_dir.name
    return test_data.is_dir() and any(test_data.iterdir())


def find_notebooks(project_dir: Path, notebooks_to_skip: list[str]) -> list[str]:
    skip = set(notebooks_to_skip)
    return sorted(p.name for p in project_dir.glob("*.ipynb") if p.name not in skip)


TEST_CMD = "pytest --nbval-lax --nbval-cell-timeout=3600 -x *.ipynb"


def _download_test_data_line(project_name: str) -> str:
    # Named `download` so it overrides the real download in the test env, while
    # `data/**` outputs let pixi cache it like the real download tasks.
    cmd = json.dumps(f"mkdir -p data && cp -r ../test_data/{project_name}/. data/")
    outputs = json.dumps(["data/**"])
    return f"download = {{ cmd = {cmd}, outputs = {outputs} }}"


def _test_task_line(has_download: bool, has_test_data: bool) -> str:
    if has_download or has_test_data:
        return f'test = {{ cmd = {json.dumps(TEST_CMD)}, depends-on = ["download"] }}'
    return f"test = {json.dumps(TEST_CMD)}"


CF_CHANNEL_LINE = 'channels = [{ channel = "conda-forge", priority = -1 }]'

SOLVE_GROUP = "default"
DEFAULT_ENV_LINE = f"default = {{ solve-group = {json.dumps(SOLVE_GROUP)} }}"
TEST_ENV_LINE = f'test = {{ features = ["test"], solve-group = {json.dumps(SOLVE_GROUP)} }}'


# nbval isn't on defaults/main; pin it to conda-forge unless that channel is
# already present, so only nbval is drawn from it.
def _nbval_line(has_conda_forge: bool) -> str:
    if has_conda_forge:
        return 'nbval = "*"'
    return 'nbval = { version = "*", channel = "conda-forge" }'


def build_test_blocks(
    has_download: bool, has_conda_forge: bool, project_name: str, has_test_data: bool
) -> list[str]:
    # solve-group ties test to default's versions; conda-forge is added as a
    # feature channel (pixi rejects a dep channel no environment lists).
    channel_block = [] if has_conda_forge else ["[feature.test]", CF_CHANNEL_LINE, ""]
    task_lines = []
    if has_test_data:
        task_lines.append(_download_test_data_line(project_name))
    task_lines.append(_test_task_line(has_download, has_test_data))
    return [
        *channel_block,
        "[feature.test.dependencies]",
        'pytest = "*"',
        _nbval_line(has_conda_forge),
        "",
        "[feature.test.tasks]",
        *task_lines,
        "",
        "[environments]",
        DEFAULT_ENV_LINE,
        TEST_ENV_LINE,
    ]


def _ensure_feature_channel(lines: list[str], has_conda_forge: bool) -> bool:
    if has_conda_forge:
        return False
    if _find_header(lines, "[feature.test]") is None:
        i = _find_header(lines, "[feature.test.dependencies]")
        if i is None:
            return False
        lines[i:i] = ["[feature.test]", CF_CHANNEL_LINE, ""]
        return True
    return bool(_replace_key_line(lines, "[feature.test]", "channels", CF_CHANNEL_LINE))


def _replace_key_line(lines: list[str], header: str, key: str, new_line: str) -> bool | None:
    # True: changed/inserted; False: already correct; None: table missing.
    i = _find_header(lines, header)
    if i is None:
        return None
    end = _table_end(lines, i)
    for k in range(i + 1, end):
        if re.match(rf"\s*{re.escape(key)}\s*=", lines[k]):
            if lines[k].strip() == new_line.strip():
                return False
            lines[k] = new_line
            return True
    lines.insert(end, new_line)
    return True


def _remove_key_line(lines: list[str], header: str, key: str) -> bool:
    # Drop `key = ...` from a table (used to clear a now-stale copy task).
    i = _find_header(lines, header)
    if i is None:
        return False
    end = _table_end(lines, i)
    for k in range(i + 1, end):
        if re.match(rf"\s*{re.escape(key)}\s*=", lines[k]):
            del lines[k]
            return True
    return False


def _reconcile_environments(lines: list[str]) -> bool:
    i = _find_header(lines, "[environments]")
    if i is None:
        return False
    changed = bool(_replace_key_line(lines, "[environments]", "test", TEST_ENV_LINE))
    i = _find_header(lines, "[environments]")
    end = _table_end(lines, i)
    if any(re.match(r"\s*default\s*=", lines[k]) for k in range(i + 1, end)):
        changed |= bool(_replace_key_line(lines, "[environments]", "default", DEFAULT_ENV_LINE))
    else:
        lines.insert(i + 1, DEFAULT_ENV_LINE)  # default first, matching a fresh add
        changed = True
    return changed


def add_test_env(
    lines: list[str], data: dict, notebooks: list[str], project_name: str, has_test_data: bool
) -> str | None:
    has_download = "download" in (data.get("tasks") or {})
    has_conda_forge = "conda-forge" in ((data.get("workspace") or {}).get("channels") or [])
    task_line = _test_task_line(has_download, has_test_data)

    # Already migrated: reconcile with the canonical form rather than re-add.
    if data.get("feature", {}).get("test") is not None:
        changed = False
        changed |= _ensure_feature_channel(lines, has_conda_forge)
        changed |= bool(
            _replace_key_line(
                lines, "[feature.test.dependencies]", "nbval", _nbval_line(has_conda_forge)
            )
        )
        # Drop the legacy copy-test-data task; it is now the `download` override.
        changed |= _remove_key_line(lines, "[feature.test.tasks]", "copy-test-data")
        if has_test_data:
            changed |= bool(
                _replace_key_line(
                    lines, "[feature.test.tasks]", "download", _download_test_data_line(project_name)
                )
            )
        else:
            # Drop a stale test-data download override if test data was removed.
            changed |= _remove_key_line(lines, "[feature.test.tasks]", "download")
        changed |= bool(_replace_key_line(lines, "[feature.test.tasks]", "test", task_line))
        changed |= _reconcile_environments(lines)
        return "updated test env" if changed else None

    if not notebooks:
        print(f"{YELLOW}no notebooks found; skipping test environment{RESET}")
        return None
    if "test" in (data.get("tasks") or {}):
        print(
            f"{YELLOW}a 'test' task already exists in [tasks]; the test env may shadow it{RESET}"
        )

    existing_envs = _find_header(lines, "[environments]")
    blocks = build_test_blocks(has_download, has_conda_forge, project_name, has_test_data)
    if existing_envs is not None:
        if "test" not in (data.get("environments") or {}):
            end = _table_end(lines, existing_envs)
            lines.insert(end, 'test = ["test"]')
        blocks = blocks[: blocks.index("[environments]")]

    while lines and lines[-1].strip() == "":
        lines.pop()
    lines.append("")
    lines.extend(blocks)
    return f"added test environment ({len(notebooks)} notebook(s))"


def process(pixi_toml: Path, project_dir: Path) -> None:
    text = pixi_toml.read_text()
    data = tomllib.loads(text)
    lines = text.splitlines()

    changed = []

    if remove_osx64_platform(lines):
        changed.append("dropped osx-64 platform")
    if remove_table(lines, f"[target.{OSX64}.dependencies]"):
        changed.append("removed [target.osx-64.dependencies]")

    metadata = (data.get("tool") or {}).get("metadata") or {}
    notebooks = find_notebooks(project_dir, metadata.get("notebooks_to_skip") or [])
    has_test_data = project_has_test_data(project_dir)
    test_msg = add_test_env(lines, data, notebooks, project_dir.name, has_test_data)
    if test_msg:
        changed.append(test_msg)

    # Table removals can leave adjacent blank lines.
    out: list[str] = []
    for line in lines:
        if line.strip() == "" and out and out[-1].strip() == "":
            continue
        out.append(line)
    while out and out[-1].strip() == "":
        out.pop()
    result = "\n".join(out) + "\n"

    tomllib.loads(result)  # fail loudly rather than write a broken manifest
    pixi_toml.write_text(result)

    if changed:
        print(f"{GREEN}{pixi_toml}: {', '.join(changed)}{RESET}")
    else:
        print(f"{pixi_toml}: no changes needed")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project_dir", type=Path, nargs="?", default=Path.cwd())
    args = ap.parse_args()

    project_dir = args.project_dir.resolve()
    pixi_toml = project_dir / "pixi.toml"
    if not pixi_toml.exists():
        print(f"no pixi.toml in {project_dir}", file=sys.stderr)
        return 1
    process(pixi_toml, project_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
