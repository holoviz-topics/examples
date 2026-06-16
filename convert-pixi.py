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
import hashlib
import json
import posixpath
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

if sys.stdout.isatty():
    GREEN, RED, RESET, CLEAR = "\033[0;32m", "\033[0;31m", "\033[0m", "\033[F\033[K"
else:
    GREEN = RED = RESET = CLEAR = ""


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


def split_packages(packages: list) -> tuple[list[str], list[str]]:
    """Split anaconda-project's ``packages`` list into (conda specs, pip specs).

    Pip requirements are nested as a single ``- pip: [...]`` entry among the
    otherwise flat list of conda matchspecs.
    """
    conda, pip = [], []
    for p in packages:
        if isinstance(p, dict) and "pip" in p:
            pip.extend(p["pip"])
        else:
            conda.append(p)
    return conda, pip


def pip_requirement_to_pypi(entry: str) -> tuple[str, str]:
    """``fastcluster>=1.3.0`` -> ('fastcluster', '>=1.3.0'); bare name -> '*'."""
    entry = entry.strip()
    m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(.*)$", entry)
    if not m:
        raise ValueError(f"cannot parse pip requirement: {entry!r}")
    name, rest = m.group(1), m.group(2).strip()
    if not rest:
        return name, "*"
    if rest.startswith("=") and not rest.startswith("=="):  # conda-style single '='
        rest = "=" + rest
    return name, rest


def _dep_line(name: str, ver: str) -> str:
    key = name if re.match(r"^[A-Za-z0-9_-]+$", name) else f'"{name}"'
    return f'{key} = "{ver}"'


def _command_str(spec: dict) -> str | None:
    if "notebook" in spec:
        return f"jupyter notebook {spec['notebook']}"
    if "unix" in spec:
        return spec["unix"].strip()
    return None


def build_pixi_tasks(commands: dict, depends_on: list[str] | None = None) -> str:
    """Render [tasks] from anaconda-project's ``commands`` block.

    ``notebook: <file>`` commands have no direct pixi equivalent, so they are
    translated to ``jupyter notebook <file>``. ``supports_http_options`` is dropped:
    pixi already forwards trailing args (``pixi run <task> --port ...``) to
    the underlying command, so there is nothing extra to represent.

    When ``depends_on`` is given (the project's download tasks), each command
    is rendered as a ``[tasks.<name>]`` table with a ``depends-on`` so the data
    is fetched before the command runs.
    """
    if depends_on:
        deps = ", ".join(f'"{d}"' for d in depends_on)
        blocks = []
        for name, spec in commands.items():
            cmd = _command_str(spec)
            if cmd is None:
                continue
            blocks.append(f'[tasks.{name}]\ncmd = "{cmd}"\ndepends-on = [{deps}]')
        return "\n\n".join(blocks) + "\n"
    lines = ["[tasks]"]
    for name, spec in commands.items():
        cmd = _command_str(spec)
        if cmd is None:
            continue
        lines.append(f'{name} = "{cmd}"')
    return "\n".join(lines) + "\n"


def build_download_tasks(downloads: dict) -> tuple[list[str], list[str]]:
    """Render ``[tasks.download...]`` entries from anaconda-project's ``downloads`` block.

    Each entry fetches ``url`` to ``filename``; ``outputs`` lets pixi skip the
    task once the file already exists, so it is safe to wire in as a
    ``depends-on`` of every other task. ``unzip: true`` downloads to a
    throwaway archive next to the target and extracts it there instead of
    keeping the archive itself. A single download is just named ``download``;
    multiple downloads are disambiguated as ``download-<name>``.
    """
    blocks: list[str] = []
    names: list[str] = []
    single = len(downloads) == 1
    for key, spec in downloads.items():
        task = "download" if single else f"download-{key}"
        names.append(task)
        url, filename = spec["url"], spec["filename"]
        dest_dir = posixpath.dirname(filename) or "."
        if spec.get("unzip"):
            archive = f"{dest_dir}/.{key}.zip"
            cmd = f"mkdir -p {dest_dir} && curl -fsSL -o {archive} {url} && unzip -o {archive} -d {dest_dir} && rm {archive}"
        else:
            cmd = f"mkdir -p {dest_dir} && curl -fsSL -o {filename} {url}"
        blocks.append(f'[tasks.{task}]\ncmd = "{cmd}"\noutputs = ["{filename}"]')
    return blocks, names


def build_pixi_toml(
    project,
    channels,
    conda_specs,
    pip_specs,
    conda_global_extras,
    target_extras,
    pypi_global_extras,
) -> str:
    """Render pixi.toml.

    ``conda_global_extras`` / ``target_extras`` / ``pypi_global_extras`` are
    packages present in the lock but not reachable from the declared deps;
    they are added as dependencies so the lock's contents equal the
    dependency closure (else pixi rewrites the lock).
    """
    platforms = project.get("platforms", [])
    deps = [matchspec_to_pixi(p) for p in conda_specs]
    pip_deps = [pip_requirement_to_pypi(p) for p in pip_specs]

    lines = ["[workspace]", f'name = "{project["name"]}"']
    if project.get("description"):
        lines.append(f'description = "{project["description"]}"')
    maintainers = project.get("examples_config", {}).get("maintainers", [])
    if maintainers:
        lines.append("authors = [" + ", ".join(f'"{m}"' for m in maintainers) + "]")
    created = project.get("examples_config", {}).get("created")
    if created:
        lines.append(f'version = "{created}"')
    lines.append("channels = [" + ", ".join(f'"{c}"' for c in channels) + "]")
    lines.append("platforms = [" + ", ".join(f'"{p}"' for p in platforms) + "]")
    lines.append("")
    lines.append("[dependencies]")
    for name, ver in deps:
        lines.append(_dep_line(name, ver))
    for name in sorted(conda_global_extras):
        lines.append(_dep_line(name, "*"))
    for plat in platforms:
        names = sorted(target_extras.get(plat, ()))
        if names:
            lines.append("")
            lines.append(f"[target.{plat}.dependencies]")
            for name in names:
                lines.append(_dep_line(name, "*"))
    if pip_deps or pypi_global_extras:
        lines.append("")
        lines.append("[pypi-dependencies]")
        for name, ver in pip_deps:
            lines.append(_dep_line(name, ver))
        for name in sorted(pypi_global_extras):
            lines.append(_dep_line(name, "*"))
    download_blocks, download_names = build_download_tasks(project.get("downloads") or {})
    if project.get("commands"):
        lines.append("")
        lines.append(build_pixi_tasks(project["commands"], download_names).rstrip("\n"))
    if download_blocks:
        lines.append("")
        lines.append("\n\n".join(download_blocks))
    return "\n".join(lines) + "\n"


def parse_lock(
    lock: dict, platforms: list[str]
) -> tuple[dict[str, list[tuple[str, str, str]]], list[tuple[str, str]]]:
    """Return ({platform: [(name, version, build, subdir), ...]}, [(pip_name, pip_version), ...])."""
    env = lock["env_specs"]
    # single env spec named 'default' expected, but be tolerant
    spec = env.get("default") or next(iter(env.values()))
    buckets = dict(spec["packages"])
    # the ``pip`` bucket lists name==version pairs with no build/subdir and
    # applies to every platform (anaconda-project solves pip deps once, not
    # per-platform), so it is pulled out before the conda bucket loop below.
    pip_entries = [tuple(e.split("==")) for e in buckets.pop("pip", [])]

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
    return per_platform, pip_entries


# --------------------------------------------------------------------------- #
# enrichment via ``pixi search``
# --------------------------------------------------------------------------- #
class Enricher:
    def __init__(self, cache_dir: Path, channels: list[str]):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.channels = channels
        # Records depend on which channels were searched (e.g. ``defaults`` vs.
        # ``conda-forge`` return different builds for the same name/version), so
        # the channel set must be part of the cache key or two projects with
        # different channels will silently poison each other's cache.
        self.channel_tag = hashlib.sha1("|".join(channels).encode()).hexdigest()[:8]
        self.mem: dict[tuple[str, str, str], list[dict]] = {}

    def _cache_file(self, name: str, version: str, platform: str) -> Path:
        return self.cache_dir / f"{name}@{version}@{platform}@{self.channel_tag}.json"

    def _search(self, name: str, version: str, platform: str) -> list[dict]:
        cmd = ["pixi", "search", "--json", "-p", platform]
        for ch in self.channels:
            cmd += ["-c", ch]
        cmd.append(f"{name}=={version}")
        out = subprocess.run(cmd, capture_output=True, text=True)
        if out.returncode != 0:
            raise RuntimeError(f"pixi search failed for {name}=={version}: {out.stderr}")
        return _flatten_search(json.loads(out.stdout))

    def _records(self, name: str, version: str, platform: str) -> list[dict]:
        key = (name, version, platform)
        if key in self.mem:
            return self.mem[key]
        cache_file = self._cache_file(name, version, platform)
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
        else:
            data = self._search(name, version, platform)
            cache_file.write_text(json.dumps(data))
        self.mem[key] = data
        return data

    def prefetch(self, keys: list[tuple[str, str, str]]) -> None:
        """Warm the cache for many (name, version, platform) keys via ``pixi search``,
        run concurrently since each is an independent subprocess call."""
        todo = [
            k
            for k in dict.fromkeys(keys)
            if k not in self.mem and not self._cache_file(*k).exists()
        ]
        if not todo:
            return
        print(f"searching {len(todo)} packages...")
        with ThreadPoolExecutor() as ex:
            futures = {ex.submit(self._records, *k): k for k in todo}
            for fut in as_completed(futures):
                fut.result()
        print(CLEAR, end="")

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
# enrichment via the PyPI JSON API (for the anaconda-project ``pip:`` bucket)
# --------------------------------------------------------------------------- #
def _wheel_tags(filename: str) -> tuple[str, str, str]:
    """``name-1.0-py3-none-any.whl`` -> ('py3', 'none', 'any')."""
    stem = filename[: -len(".whl")]
    python_tag, abi_tag, platform_tag = stem.split("-")[-3:]
    return python_tag, abi_tag, platform_tag


def _platform_tag_ok(tag: str, platform: str) -> bool:
    if platform == "linux-64":
        return "manylinux" in tag and "x86_64" in tag
    if platform == "linux-aarch64":
        return "manylinux" in tag and "aarch64" in tag
    if platform == "osx-64":
        return tag.startswith("macosx") and ("x86_64" in tag or "universal2" in tag)
    if platform == "osx-arm64":
        return tag.startswith("macosx") and ("arm64" in tag or "universal2" in tag)
    if platform == "win-64":
        return tag == "win_amd64"
    return False


def _pick_wheel(files: list[dict], platform: str, py_tag: str) -> dict | None:
    """Pick the wheel matching ``platform``/``py_tag``, preferring pure-python wheels."""
    universal = [f for f in files if _wheel_tags(f["filename"])[0] in ("py3", "py2.py3")]
    if universal:
        return universal[0]
    for f in files:
        python_tag, _abi_tag, platform_tag = _wheel_tags(f["filename"])
        if python_tag == py_tag and _platform_tag_ok(platform_tag, platform):
            return f
    return None


class PypiEnricher:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.mem: dict[str, dict] = {}

    def _cache_file(self, name: str, version: str) -> Path:
        return self.cache_dir / f"{name}@{version}.json"

    def _fetch(self, name: str, version: str) -> dict:
        url = f"https://pypi.org/pypi/{name}/{version}/json"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def _release(self, name: str, version: str) -> dict:
        key = f"{name}=={version}"
        if key in self.mem:
            return self.mem[key]
        cache_file = self._cache_file(name, version)
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
        else:
            data = self._fetch(name, version)
            cache_file.write_text(json.dumps(data))
        self.mem[key] = data
        return data

    def prefetch(self, entries: list[tuple[str, str]]) -> None:
        """Warm the cache for many (name, version) pairs via the PyPI JSON API,
        run concurrently since each is an independent HTTP request."""
        todo = [
            e
            for e in dict.fromkeys(entries)
            if f"{e[0]}=={e[1]}" not in self.mem and not self._cache_file(*e).exists()
        ]
        if not todo:
            return
        print(f"fetching pypi metadata for {len(todo)} packages...")
        with ThreadPoolExecutor() as ex:
            futures = {ex.submit(self._release, *e): e for e in todo}
            for fut in as_completed(futures):
                fut.result()
        print(CLEAR, end="")

    def lookup(self, name: str, version: str, platform: str, py_tag: str) -> dict:
        data = self._release(name, version)
        files = [f for f in data["urls"] if f["packagetype"] == "bdist_wheel"]
        chosen = _pick_wheel(files, platform, py_tag)
        if chosen is None:
            # No wheel for this release at all (some old releases only ever
            # shipped an sdist) - fall back to it; pip builds it at install time.
            sdists = [f for f in data["urls"] if f["packagetype"] == "sdist"]
            if not sdists:
                raise LookupError(
                    f"no compatible wheel for {name}=={version} on {platform} ({py_tag})"
                )
            chosen = sdists[0]
        return {
            "name": data["info"]["name"],
            "version": version,
            "url": chosen["url"],
            "sha256": chosen["digests"]["sha256"],
            "requires_dist": data["info"].get("requires_dist") or [],
            "requires_python": data["info"].get("requires_python") or "",
        }


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


def record_to_locked_pypi(rec: dict) -> dict:
    entry = {
        "pypi": rec["url"],
        "name": rec["name"],
        "version": rec["version"],
        "sha256": rec["sha256"],
    }
    if rec.get("requires_dist"):
        entry["requires_dist"] = rec["requires_dist"]
    if rec.get("requires_python"):
        entry["requires_python"] = rec["requires_python"]
    return entry


def _python_tag_for(per_platform_entries: list[tuple[str, str, str, str]]) -> str:
    for name, version, _build, _subdir in per_platform_entries:
        if name == "python":
            major, minor = version.split(".")[:2]
            return f"cp{major}{minor}"
    raise ValueError("no 'python' package found in lock; cannot pick pypi wheels")


def build_pixi_lock(per_platform, pip_entries, enricher, pypi_enricher, platforms, channels):
    pkg_by_url: dict[str, dict] = {}
    env_pkgs: dict[str, list[tuple[str, str]]] = {p: [] for p in platforms}
    graph: dict[str, list[dict]] = {p: [] for p in platforms}
    has_pypi = False

    enricher.prefetch(
        [(name, version, plat) for plat in platforms for name, version, _, _ in per_platform[plat]]
    )
    if pip_entries:
        pypi_enricher.prefetch(pip_entries)

    for plat in platforms:
        for name, version, build, subdir in per_platform[plat]:
            rec = enricher.lookup(name, version, build, plat, subdir)
            url = rec["url"]
            env_pkgs[plat].append(("conda", url))
            graph[plat].append({"name": rec["name"], "depends": rec.get("depends") or []})
            if url not in pkg_by_url:
                pkg_by_url[url] = record_to_locked(rec)

        if pip_entries:
            has_pypi = True
            py_tag = _python_tag_for(per_platform[plat])
            for name, version in pip_entries:
                rec = pypi_enricher.lookup(name, version, plat, py_tag)
                url = rec["url"]
                env_pkgs[plat].append(("pypi", url))
                graph[plat].append(
                    {"name": rec["name"], "depends": rec.get("requires_dist") or []}
                )
                if url not in pkg_by_url:
                    pkg_by_url[url] = record_to_locked_pypi(rec)

    # Mirror the manifest channel set/order so pixi considers the lock current.
    # v7 adds the top-level ``platforms`` block; package ordering is cosmetic
    # (pixi re-sorts on write) and does not affect the up-to-date check.
    default_env = {
        "channels": [{"url": c.rstrip("/") + "/"} for c in channels],
    }
    if has_pypi:
        default_env["indexes"] = ["https://pypi.org/simple"]
    default_env["packages"] = {
        p: [{kind: u} for kind, u in sorted(set(env_pkgs[p]), key=lambda t: t[1])]
        for p in platforms
    }
    lock = {
        "version": 7,
        "platforms": [{"name": p} for p in platforms],
        "environments": {"default": default_env},
        "packages": [pkg_by_url[u] for u in sorted(pkg_by_url)],
    }
    return lock, graph


def verify_lock(
    project_dir: Path, pixi_lock: dict, platforms: list[str], swallowed: set[str] = frozenset()
) -> bool:
    """Cross-check the generated pixi.lock against the anaconda lock pins.

    ``swallowed`` names are dropped from the conda side of the comparison:
    they are intentionally omitted from the conda lock because pip overrides
    them (see ``main``), so the anaconda lock's conda pin for them is expected
    to be absent rather than missing.
    """
    alock = load_yaml(project_dir / "anaconda-project-lock.yml")
    spec = alock["env_specs"].get("default") or next(iter(alock["env_specs"].values()))

    expected: dict[str, set[tuple[str, str, str]]] = {p: set() for p in platforms}
    expected_pypi: set[tuple[str, str]] = set()
    for bucket, entries in spec["packages"].items():
        if bucket == "pip":
            expected_pypi = {(n.lower(), v) for n, v in (e.split("==") for e in entries)}
            continue
        targets = (NONARCH_BUCKETS[bucket] or platforms) if bucket in NONARCH_BUCKETS else [bucket]
        for entry in entries:
            name, version, build = entry.split("=")
            if name in swallowed:
                continue
            for plat in targets:
                if plat in expected:
                    expected[plat].add((name, version, build))

    pypi_meta = {
        p["pypi"]: (p["name"].lower(), p["version"]) for p in pixi_lock["packages"] if "pypi" in p
    }
    got: dict[str, set[tuple[str, str, str]]] = {p: set() for p in platforms}
    got_pypi: dict[str, set[tuple[str, str]]] = {p: set() for p in platforms}
    for plat, items in pixi_lock["environments"]["default"]["packages"].items():
        for item in items:
            if "pypi" in item:
                got_pypi[plat].add(pypi_meta[item["pypi"]])
                continue
            fn = item["conda"].rsplit("/", 1)[1]
            fn = fn.removesuffix(".conda").removesuffix(".tar.bz2")
            name, version, build = fn.rsplit("-", 2)
            got[plat].add((name, version, build))

    ok = True
    for plat in platforms:
        anaconda_only = expected[plat] - got[plat]
        pixi_only = got[plat] - expected[plat]

        # The pinned build can vanish from the channel between when the anaconda
        # lock was generated and now (see Enricher.lookup's fallback). When the
        # only discrepancy for a name=version is the build string, that's
        # expected channel drift, not a real mismatch.
        anaconda_by_nv = {(n, v): b for n, v, b in anaconda_only}
        pixi_by_nv = {(n, v): b for n, v, b in pixi_only}
        drifted = anaconda_by_nv.keys() & pixi_by_nv.keys()
        anaconda_only = {m for m in anaconda_only if (m[0], m[1]) not in drifted}
        pixi_only = {x for x in pixi_only if (x[0], x[1]) not in drifted}

        print(
            f"{plat}: expected={len(expected[plat])} got={len(got[plat])} "
            f"anaconda-only={len(anaconda_only)} pixi-only={len(pixi_only)}"
        )
        for name, version in sorted(drifted):
            print(
                f"   BUILD-DRIFT   {name}={version}: "
                f"{anaconda_by_nv[(name, version)]} -> {pixi_by_nv[(name, version)]}"
            )
        for m in sorted(anaconda_only):
            ok = False
            print(f"{RED}   ANACONDA-ONLY {m[0]}={m[1]}={m[2]}{RESET}")
        for x in sorted(pixi_only):
            ok = False
            print(f"{RED}   PIXI-ONLY     {x[0]}={x[1]}={x[2]}{RESET}")

    if expected_pypi:
        for plat in platforms:
            anaconda_only_pypi = expected_pypi - got_pypi[plat]
            pixi_only_pypi = got_pypi[plat] - expected_pypi
            print(
                f"{plat} (pypi): expected={len(expected_pypi)} got={len(got_pypi[plat])} "
                f"anaconda-only={len(anaconda_only_pypi)} pixi-only={len(pixi_only_pypi)}"
            )
            for m in sorted(anaconda_only_pypi):
                ok = False
                print(f"{RED}   ANACONDA-ONLY {m[0]}=={m[1]}{RESET}")
            for x in sorted(pixi_only_pypi):
                ok = False
                print(f"{RED}   PIXI-ONLY     {x[0]}=={x[1]}{RESET}")

    result = f"{GREEN}exact match{RESET}" if ok else f"{RED}MISMATCH{RESET}"
    print(f"\nRESULT: {result}")
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

    conda_specs, pip_specs = split_packages(project.get("packages", []))

    # Build the lock first: it yields the dependency graph used to detect which
    # locked packages must be promoted to manifest dependencies.
    per_platform, pip_entries = parse_lock(lock, platforms)
    pypi_names = {name for name, _ in pip_entries}

    # A package locked by both conda (usually transitively) and pip is a pip
    # override: anaconda-project just installs the pip wheel on top, but pixi's
    # solver pins the conda version and then conflicts with the pypi
    # requirement. Swallow the conda side so only the pypi package is locked.
    swallowed = {
        name for plat in platforms for name, *_ in per_platform[plat] if name in pypi_names
    }
    if swallowed:
        print(f"swallowing conda packages overridden by pip: {', '.join(sorted(swallowed))}")
        per_platform = {
            plat: [e for e in entries if e[0] not in swallowed]
            for plat, entries in per_platform.items()
        }

    enricher = Enricher(args.cache_dir, channels)
    pypi_enricher = PypiEnricher(args.cache_dir / "pypi")
    pixi_lock, graph = build_pixi_lock(
        per_platform, pip_entries, enricher, pypi_enricher, platforms, channels
    )
    with (out_dir / "pixi.lock").open("w") as fh:
        yaml.safe_dump(pixi_lock, fh, sort_keys=False, default_flow_style=False)
    print(f"{GREEN}wrote {out_dir / 'pixi.lock'}{RESET}")

    declared = [matchspec_to_pixi(p)[0] for p in conda_specs] + [
        pip_requirement_to_pypi(p)[0] for p in pip_specs
    ]
    global_extras, target_extras = unreachable_roots(graph, declared, platforms)
    if global_extras or any(target_extras.values()):
        print(
            "promoted unreachable lock packages to dependencies:",
            ", ".join(sorted(global_extras | {n for v in target_extras.values() for n in v})),
        )
    pypi_global_extras = global_extras & pypi_names
    conda_global_extras = global_extras - pypi_names
    toml_text = build_pixi_toml(
        project,
        channels,
        conda_specs,
        pip_specs,
        conda_global_extras,
        target_extras,
        pypi_global_extras,
    )
    (out_dir / "pixi.toml").write_text(toml_text)
    print(f"{GREEN}wrote {out_dir / 'pixi.toml'}{RESET}")

    if not args.no_verify:
        print()
        if not verify_lock(project_dir, pixi_lock, platforms, swallowed):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
