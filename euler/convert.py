#!/usr/bin/env python
"""Convert an anaconda-project (spec + lock) to pixi (pixi.toml + pixi.lock).

Strategy: direct translation (no re-solve).
  * pixi.toml  <- anaconda-project.yml   (loose spec / matchspecs)
  * pixi.lock  <- anaconda-project-lock.yml (exact name=version=build pins)

The anaconda lock only stores ``name=version=build`` per platform.  A valid
pixi.lock additionally needs each package's URL + sha256/md5 + depends metadata.
That gap is filled with ``pixi search --json`` against the ``defaults`` repo,
cached on disk so reruns are offline/cheap.

After writing pixi.lock, it is cross-checked against the anaconda lock's
name=version=build pins (pass --no-verify to skip).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

# anaconda-project channel name -> explicit pixi channel URLs.  ``defaults`` is a
# conda metachannel that pixi does not expand on its own (it would resolve to the
# non-existent conda.anaconda.org/defaults), so we map it to the real repo URLs.
CHANNEL_MAP = {
    "defaults": [
        "https://repo.anaconda.com/pkgs/main",
        "https://repo.anaconda.com/pkgs/r",
        "https://repo.anaconda.com/pkgs/msys2",
    ],
}


def resolve_channels(names: list[str]) -> list[str]:
    """Expand anaconda-project channel names to pixi channel URLs."""
    urls: list[str] = []
    for name in names:
        for url in CHANNEL_MAP.get(name, [name]):
            if url not in urls:
                urls.append(url)
    return urls


# anaconda-project lock buckets that are not real subdirs -> the platforms they
# apply to.  Their packages are ``noarch``.  Concrete subdir buckets map to the
# matching platform only.
NONARCH_BUCKETS = {
    "all": None,  # filled with every project platform at runtime
    "unix": ["linux-64", "osx-64", "osx-arm64"],
    "osx": ["osx-64", "osx-arm64"],
    "linux": ["linux-64"],
    "win": ["win-64"],
}


# --------------------------------------------------------------------------- #
# parsing the anaconda-project files
# --------------------------------------------------------------------------- #
def load_yaml(path: Path) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh)


def matchspec_to_pixi(entry: str) -> tuple[str, str]:
    """``python=3.10`` -> ('python', '3.10.*'); ``notebook <7`` -> (.., '<7')."""
    entry = entry.strip()
    m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(.*)$", entry)
    if not m:
        raise ValueError(f"cannot parse package spec: {entry!r}")
    name, rest = m.group(1), m.group(2).strip()
    if not rest:
        return name, "*"
    if rest.startswith("=="):
        return name, rest
    if rest.startswith("="):  # conda single '=' -> fuzzy match
        ver = rest[1:].strip()
        return name, ver if ver.endswith("*") else f"{ver}.*"
    if rest[0] in "<>!~":  # explicit operator, keep verbatim
        return name, rest
    return name, rest if rest.endswith("*") else f"{rest}.*"  # bare version


def _dep_line(name: str, ver: str) -> str:
    key = name if re.match(r"^[A-Za-z0-9_-]+$", name) else f'"{name}"'
    return f'{key} = "{ver}"'


def build_pixi_tasks(commands: dict) -> str:
    """Render [tasks] from anaconda-project's ``commands`` block.

    ``notebook: <file>`` commands have no direct pixi equivalent, so they are
    translated to ``jupyter notebook <file>``. ``supports_http_options`` is dropped:
    pixi already forwards trailing args (``pixi run <task> --port ...``) to
    the underlying command, so there is nothing extra to represent.
    """
    lines = ["[tasks]"]
    for name, spec in commands.items():
        if "notebook" in spec:
            cmd = f"jupyter notebook {spec['notebook']}"
        elif "unix" in spec:
            cmd = spec["unix"].strip()
        else:
            continue
        lines.append(f'{name} = "{cmd}"')
    return "\n".join(lines) + "\n"


def build_pixi_toml(project, channels, global_extras, target_extras) -> str:
    """Render pixi.toml.

    ``global_extras`` / ``target_extras`` are packages present in the lock but
    not reachable from the declared deps; they are added as dependencies so the
    lock's contents equal the dependency closure (else pixi rewrites the lock).
    """
    platforms = project.get("platforms", [])
    deps = [matchspec_to_pixi(p) for p in project.get("packages", [])]

    lines = ["[workspace]", f'name = "{project["name"]}"']
    if project.get("description"):
        lines.append(f'description = "{project["description"]}"')
    lines.append("channels = [" + ", ".join(f'"{c}"' for c in channels) + "]")
    lines.append("platforms = [" + ", ".join(f'"{p}"' for p in platforms) + "]")
    lines.append("")
    lines.append("[dependencies]")
    for name, ver in deps:
        lines.append(_dep_line(name, ver))
    for name in sorted(global_extras):
        lines.append(_dep_line(name, "*"))
    for plat in platforms:
        names = sorted(target_extras.get(plat, ()))
        if names:
            lines.append("")
            lines.append(f"[target.{plat}.dependencies]")
            for name in names:
                lines.append(_dep_line(name, "*"))
    if project.get("commands"):
        lines.append("")
        lines.append(build_pixi_tasks(project["commands"]).rstrip("\n"))
    return "\n".join(lines) + "\n"


def parse_lock(lock: dict, platforms: list[str]) -> dict[str, list[tuple[str, str, str]]]:
    """Return {platform: [(name, version, build), ...]} from the lock buckets."""
    env = lock["env_specs"]
    # single env spec named 'default' expected, but be tolerant
    spec = env.get("default") or next(iter(env.values()))
    buckets = spec["packages"]

    per_platform: dict[str, list[tuple[str, str, str]]] = {p: [] for p in platforms}
    for bucket, entries in buckets.items():
        if bucket in NONARCH_BUCKETS:
            targets = NONARCH_BUCKETS[bucket] or platforms
            subdir = "noarch"
        else:
            targets = [bucket]
            subdir = bucket
        for entry in entries:
            name, version, build = entry.split("=")
            for plat in targets:
                if plat in per_platform:
                    per_platform[plat].append((name, version, build, subdir))
    return per_platform


# --------------------------------------------------------------------------- #
# enrichment via ``pixi search``
# --------------------------------------------------------------------------- #
class Enricher:
    def __init__(self, cache_dir: Path, channels: list[str]):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.channels = channels
        self.mem: dict[tuple[str, str, str], list[dict]] = {}

    def _records(self, name: str, version: str, platform: str) -> list[dict]:
        key = (name, version, platform)
        if key in self.mem:
            return self.mem[key]
        cache_file = self.cache_dir / f"{name}@{version}@{platform}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
        else:
            cmd = ["pixi", "search", "--json", "-p", platform]
            for ch in self.channels:
                cmd += ["-c", ch]
            cmd.append(f"{name}=={version}")
            out = subprocess.run(cmd, capture_output=True, text=True)
            if out.returncode != 0:
                raise RuntimeError(f"pixi search failed for {name}=={version}: {out.stderr}")
            data = _flatten_search(json.loads(out.stdout))
            cache_file.write_text(json.dumps(data))
        self.mem[key] = data
        return data

    def lookup(self, name, version, build, platform, subdir) -> dict:
        records = self._records(name, version, platform)
        # The build string encodes the arch, so an exact build match is unique
        # regardless of which lock bucket the package was listed under (some
        # noarch packages are filed under a concrete-platform bucket).
        exact = [r for r in records if r.get("build") == build]
        if exact:
            return exact[0]
        # Fallback: exact build is gone from the channel. Prefer the matching
        # subdir (or noarch) and the newest build_number.
        cands = [r for r in records if r.get("subdir") in (subdir, "noarch")]
        if not cands:
            raise LookupError(
                f"no record for {name}=={version}=={build} on {platform} "
                f"(subdir {subdir}); available builds: "
                + ", ".join(sorted(f"{r.get('subdir')}/{r.get('build')}" for r in records))
            )
        cands.sort(key=lambda r: r.get("build_number", 0), reverse=True)
        return cands[0]


def _flatten_search(data) -> list[dict]:
    """pixi search --json may emit a list or {name: [records]}; normalise."""
    if isinstance(data, dict):
        records = []
        for v in data.values():
            records.extend(v if isinstance(v, list) else [v])
        return records
    return list(data)


# --------------------------------------------------------------------------- #
# emit pixi.lock (v6)
# --------------------------------------------------------------------------- #
def record_to_locked(rec: dict) -> dict:
    url = rec.get("url")
    entry = {"conda": url}
    for field in (
        "sha256",
        "md5",
        "depends",
        "constrains",
        "license",
        "license_family",
        "size",
        "timestamp",
    ):
        if rec.get(field) not in (None, [], ""):
            entry[field] = rec[field]
    return entry


def build_pixi_lock(per_platform, enricher, platforms, channels):
    pkg_by_url: dict[str, dict] = {}
    env_pkgs: dict[str, list[str]] = {p: [] for p in platforms}
    graph: dict[str, list[dict]] = {p: [] for p in platforms}

    for plat in platforms:
        for name, version, build, subdir in per_platform[plat]:
            rec = enricher.lookup(name, version, build, plat, subdir)
            url = rec["url"]
            env_pkgs[plat].append(url)
            graph[plat].append({"name": rec["name"], "depends": rec.get("depends") or []})
            if url not in pkg_by_url:
                pkg_by_url[url] = record_to_locked(rec)

    # Mirror the manifest channel set/order so pixi considers the lock current.
    # v7 adds the top-level ``platforms`` block; package ordering is cosmetic
    # (pixi re-sorts on write) and does not affect the up-to-date check.
    lock = {
        "version": 7,
        "platforms": [{"name": p} for p in platforms],
        "environments": {
            "default": {
                "channels": [{"url": c.rstrip("/") + "/"} for c in channels],
                "packages": {
                    p: [{"conda": u} for u in sorted(set(env_pkgs[p]))] for p in platforms
                },
            }
        },
        "packages": [pkg_by_url[u] for u in sorted(pkg_by_url)],
    }
    return lock, graph


def verify_lock(project_dir: Path, pixi_lock: dict, platforms: list[str]) -> bool:
    """Cross-check the generated pixi.lock against the anaconda lock pins."""
    alock = load_yaml(project_dir / "anaconda-project-lock.yml")
    spec = alock["env_specs"].get("default") or next(iter(alock["env_specs"].values()))

    expected: dict[str, set[tuple[str, str, str]]] = {p: set() for p in platforms}
    for bucket, entries in spec["packages"].items():
        targets = (NONARCH_BUCKETS[bucket] or platforms) if bucket in NONARCH_BUCKETS else [bucket]
        for entry in entries:
            name, version, build = entry.split("=")
            for plat in targets:
                if plat in expected:
                    expected[plat].add((name, version, build))

    got: dict[str, set[tuple[str, str, str]]] = {p: set() for p in platforms}
    for plat, items in pixi_lock["environments"]["default"]["packages"].items():
        for item in items:
            fn = item["conda"].rsplit("/", 1)[1]
            fn = fn.removesuffix(".conda").removesuffix(".tar.bz2")
            name, version, build = fn.rsplit("-", 2)
            got[plat].add((name, version, build))

    ok = True
    for plat in platforms:
        missing = expected[plat] - got[plat]
        extra = got[plat] - expected[plat]
        print(
            f"{plat}: expected={len(expected[plat])} got={len(got[plat])} "
            f"missing={len(missing)} extra={len(extra)}"
        )
        for m in sorted(missing):
            ok = False
            print(f"   MISSING {m[0]}={m[1]}={m[2]}")
        for x in sorted(extra):
            ok = False
            print(f"   EXTRA   {x[0]}={x[1]}={x[2]}")

    print("\nRESULT:", "exact match" if ok else "MISMATCH")
    return ok


def _dep_name(spec: str) -> str:
    return re.split(r"[\s<>=!~|]", spec.strip(), maxsplit=1)[0]


def unreachable_roots(graph, declared, platforms):
    """Per platform, packages in the lock not reachable from ``declared`` deps.

    pixi treats a lock as outdated if it contains packages outside the closure
    of the manifest's dependencies, so these must be promoted to dependencies.
    Returns (global_extras, target_extras) where global_extras are present on
    every platform and target_extras maps platform -> names for the rest.
    """
    extra_platforms: dict[str, set[str]] = {}
    locked_platforms: dict[str, set[str]] = {}
    for plat in platforms:
        by_name = {p["name"]: p for p in graph[plat]}
        seen: set[str] = set()
        stack = [d for d in declared if d in by_name]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            for dep in by_name[n]["depends"]:
                dn = _dep_name(dep)
                if dn in by_name and dn not in seen:
                    stack.append(dn)
        for name in by_name:
            locked_platforms.setdefault(name, set()).add(plat)
            if name not in seen:
                extra_platforms.setdefault(name, set()).add(plat)

    nplat = set(platforms)
    global_extras, target_extras = set(), {p: set() for p in platforms}
    for name in extra_platforms:
        if locked_platforms[name] == nplat:
            global_extras.add(name)  # safe everywhere -> single global dep
        else:
            for plat in locked_platforms[name]:
                target_extras[plat].add(name)
    return global_extras, target_extras


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project_dir", type=Path, nargs="?", default=Path.cwd())
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="where to write pixi.toml/pixi.lock (default: project_dir)",
    )
    ap.add_argument("--cache-dir", type=Path, default=Path(__file__).resolve().parent / "cache")
    ap.add_argument(
        "--no-verify",
        action="store_true",
        help="skip cross-checking the generated pixi.lock against the anaconda lock pins",
    )
    args = ap.parse_args()

    project_dir = args.project_dir.resolve()
    out_dir = (args.out_dir or project_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    project = load_yaml(project_dir / "anaconda-project.yml")
    lock = load_yaml(project_dir / "anaconda-project-lock.yml")
    platforms = project["platforms"]
    channels = resolve_channels(project.get("channels", []))

    # Build the lock first: it yields the dependency graph used to detect which
    # locked packages must be promoted to manifest dependencies.
    per_platform = parse_lock(lock, platforms)
    enricher = Enricher(args.cache_dir, channels)
    pixi_lock, graph = build_pixi_lock(per_platform, enricher, platforms, channels)
    with (out_dir / "pixi.lock").open("w") as fh:
        yaml.safe_dump(pixi_lock, fh, sort_keys=False, default_flow_style=False)
    print(f"wrote {out_dir / 'pixi.lock'}")

    declared = [matchspec_to_pixi(p)[0] for p in project.get("packages", [])]
    global_extras, target_extras = unreachable_roots(graph, declared, platforms)
    if global_extras or any(target_extras.values()):
        print(
            "promoted unreachable lock packages to dependencies:",
            ", ".join(sorted(global_extras | {n for v in target_extras.values() for n in v})),
        )
    toml_text = build_pixi_toml(project, channels, global_extras, target_extras)
    (out_dir / "pixi.toml").write_text(toml_text)
    print(f"wrote {out_dir / 'pixi.toml'}")

    if not args.no_verify:
        print()
        if not verify_lock(project_dir, pixi_lock, platforms):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
