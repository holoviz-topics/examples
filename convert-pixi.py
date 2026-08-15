#!/usr/bin/env python
"""Convert an anaconda-project (spec + lock) to pixi (pixi.toml + pixi.lock).

Strategy: direct translation (no re-solve).
  * pixi.toml  <- anaconda-project.yml   (loose spec / matchspecs)
  * pixi.lock  <- anaconda-project-lock.yml (exact name=version=build pins)

The anaconda lock only stores ``name=version=build`` per platform.  A valid
pixi.lock additionally needs each package's URL + sha256/md5 + depends metadata.
That gap is filled by fetching ``repodata.json`` once per channel+subdir: the
compressed download is kept verbatim on disk (these are frozen legacy projects,
so the snapshot never needs refreshing) and each run walks it with simdjson,
converting only the few hundred records the lock actually pins.

After writing pixi.lock, it is cross-checked against the anaconda lock's
name=version=build pins (pass --no-verify to skip).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import posixpath
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import orjson
import simdjson
import tomllib
import yaml
import zstandard

if sys.stdout.isatty():
    GREEN, RED, YELLOW, RESET, CLEAR = (
        "\033[0;32m",
        "\033[0;31m",
        "\033[0;33m",
        "\033[0m",
        "\033[F\033[K",
    )
else:
    GREEN = RED = YELLOW = RESET = CLEAR = ""


CHANNEL_MAP = {
    "defaults": ["main", "msys2"],  # also "r" but not added
    "nodefaults": [],
}


def resolve_channels(names: list[str]) -> list[str]:
    """Expand anaconda-project channel names to pixi channel URLs."""
    urls: list[str] = []
    for name in names:
        for url in CHANNEL_MAP.get(name, [name]):
            if url not in urls:
                urls.append(url)
    return urls


def _lock_channel_url(c: str) -> str:
    """Return the full URL for a channel as it appears in pixi.lock."""
    c = c.rstrip("/")
    if not c.startswith(("https://", "http://")):
        c = f"https://conda.anaconda.org/{c}"
    return c + "/"


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
    if rest[0] in "<>!~":  # explicit operator
        op_len = 2 if rest[1:2] == "=" else 1
        return name, rest[:op_len] + rest[op_len:].strip()
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


def pip_requirement_to_pypi(entry: str) -> tuple[str, str, list[str]]:
    """``fastcluster>=1.3.0`` -> ('fastcluster', '>=1.3.0', []);
    ``mne[hdf5]>=1.8.0`` -> ('mne', '>=1.8.0', ['hdf5'])."""
    entry = entry.strip()
    m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*(.*)$", entry)
    if not m:
        raise ValueError(f"cannot parse pip requirement: {entry!r}")
    name, extras_str, rest = m.group(1), m.group(2), m.group(3).strip()
    extras = [e.strip() for e in extras_str[1:-1].split(",")] if extras_str else []
    if not rest:
        return name, "*", extras
    if rest.startswith("=") and not rest.startswith("=="):  # conda-style single '='
        rest = "=" + rest
    return name, rest, extras


def _dep_line(name: str, ver: str) -> str:
    key = name if re.match(r"^[A-Za-z0-9_-]+$", name) else f'"{name}"'
    return f"{key} = {json.dumps(ver)}"


def _pypi_dep_line(name: str, ver: str, extras: list[str]) -> str:
    key = name if re.match(r"^[A-Za-z0-9_-]+$", name) else f'"{name}"'
    if not extras:
        return f"{key} = {json.dumps(ver)}"
    extras_toml = ", ".join(json.dumps(e) for e in extras)
    return f"{key} = {{ version = {json.dumps(ver)}, extras = [{extras_toml}] }}"


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
            blocks.append(f"[tasks.{name}]\ncmd = {json.dumps(cmd)}\ndepends-on = [{deps}]")
        return "\n\n".join(blocks) + "\n"
    lines = ["[tasks]"]
    for name, spec in commands.items():
        cmd = _command_str(spec)
        if cmd is None:
            continue
        lines.append(f"{name} = {json.dumps(cmd)}")
    return "\n".join(lines) + "\n"


def build_activation_env(variables: dict) -> str:
    """Render ``[activation.env]`` from anaconda-project's ``variables`` block.

    anaconda-project accepts two forms per variable: a bare scalar
    (``INTAKE_CACHE_DIR: data``) and a mapping carrying a ``description`` and an
    optional ``default`` (``DS_DATASET: {description: ..., default: nyc_taxi_50k}``).
    Only the ``default`` holds a value, so the mapping form collapses to it -
    matching ``proj_env_vars`` in dodo.py. A mapping *without* a ``default`` is
    anaconda-project's way of declaring a variable the user must supply, so there
    is nothing to pre-set and the entry is skipped.

    Values are always emitted as strings: these are environment variables, and
    the libraries reading them (e.g. ``DASK_DATAFRAME__QUERY_PLANNING=False``)
    expect the string, not a TOML boolean.
    """
    lines = []
    for name, value in variables.items():
        if isinstance(value, dict):
            if "default" not in value:
                continue
            value = value["default"]
        if value is None:
            continue
        lines.append(f"{name} = {json.dumps(str(value))}")
    if not lines:
        return ""
    return "[activation.env]\n" + "\n".join(lines) + "\n"


def build_download_tasks(downloads: dict) -> tuple[list[str], list[str]]:
    """Render ``[tasks.download...]`` entries from anaconda-project's ``downloads`` block.

    Each entry fetches ``url`` to ``filename``; ``outputs`` lets pixi skip the
    task once the file already exists, so it is safe to wire in as a
    ``depends-on`` of every other task. ``unzip: true`` mirrors
    anaconda-project's own unzip behaviour (``ziputils.unpack_zip``): the
    archive is extracted straight into a directory at ``filename`` rather than
    into its parent, since these datasets are typically written out as a
    directory of parts (e.g. a dask-written ``*.parq``) rather than a single
    file matching that name. Extraction goes through ``python -m zipfile -e``
    rather than ``unzip`` so the task only needs the environment's python, which
    pixi guarantees, instead of an ``unzip`` binary on the host. A single
    download is just named ``download``;
    multiple downloads are disambiguated as ``download-<name>`` and joined by an
    aggregate ``download`` task depending on all of them. That way ``download``
    is the one entry point every other task (and dodo.py) can depend on,
    whatever the number of downloads.

    The returned names are what other tasks should depend on - i.e. just
    ``["download"]`` when there is anything to fetch - not every task rendered.
    """
    if not downloads:
        return [], []
    blocks: list[str] = []
    subtasks: list[str] = []
    single = len(downloads) == 1
    for key, spec in downloads.items():
        task = "download" if single else f"download-{key}"
        subtasks.append(task)
        url, filename = spec["url"], spec["filename"]
        dest_dir = posixpath.dirname(filename) or "."
        env_line = f"env = {{ FILENAME = {json.dumps(filename)} }}\n"
        if spec.get("unzip"):
            archive = f".{key}.zip"
            cmd = f"mkdir -p $FILENAME && curl -fsSL -o {archive} {url} && python -m zipfile -e {archive} $FILENAME && rm {archive}"
        else:
            cmd = f"mkdir -p {dest_dir} && curl -fsSL -o $FILENAME {url}"
        blocks.append(
            f"[tasks.{task}]\n{env_line}cmd = {json.dumps(cmd)}\noutputs = [{json.dumps(filename)}]"
        )
    if single:
        return blocks, subtasks
    deps = ", ".join(json.dumps(t) for t in subtasks)
    return [f"[tasks.download]\ndepends-on = [{deps}]", *blocks], ["download"]


# --------------------------------------------------------------------------- #
# project metadata: examples_config (anaconda-project.yml) -> [tool.metadata]
# --------------------------------------------------------------------------- #
# Emission order of the keys carried over to [tool.metadata]: dodo.py's
# required_config + optional_config whitelist, plus ``description``, which used
# to sit at the root of the YAML rather than inside examples_config.  Keys are
# left in snake_case so every lookup and validation message in dodo.py keeps
# working verbatim.
TOOL_METADATA_KEYS = (
    "created",
    "last_updated",
    "maintainers",
    "categories",
    "labels",
    "title",
    "description",
    "no_data_ingestion",
    "skip_notebooks_evaluation",
    "skip_test",
    "notebooks_to_skip",
    "gh_runner",
)

# Keys deliberately not carried over: AE5 deployments are retired, so the
# website and CI no longer read them.
TOOL_METADATA_DROPPED = ("deployments",)


def _toml_value(value) -> str:
    """Render one metadata value as TOML.

    ``created`` / ``last_updated`` come out as *quoted* ISO strings
    (``created = "2018-09-17"``).  A bare TOML local date would be more
    idiomatic, but pixi 0.76.1's manifest parser rejects TOML dates outright -
    ``created = 2018-09-17`` fails the whole manifest with "invalid number",
    even inside an otherwise inert ``[tool.*]`` table.
    """
    if isinstance(value, bool):  # before int: bool is an int subclass
        return "true" if value else "false"
    if isinstance(value, datetime.datetime):
        value = value.date()
    if isinstance(value, datetime.date):
        return json.dumps(value.isoformat())
    if isinstance(value, (int, float, str)):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise ValueError(f"cannot render metadata value as TOML: {value!r}")


def build_tool_metadata(metadata: dict) -> str:
    """Render ``[tool.metadata]``, the project metadata CI and the website read.

    pixi accepts arbitrary ``[tool.*]`` tables and ignores them for dependency
    solving, so this block is inert for locking.  Unknown keys are still
    emitted (dropping them would lose metadata silently) but reported, since
    dodo.py validates the key set.
    """
    if not metadata:
        return ""
    unknown = [k for k in metadata if k not in TOOL_METADATA_KEYS + TOOL_METADATA_DROPPED]
    if unknown:
        print(f"{YELLOW}unrecognised metadata keys kept as-is: {', '.join(unknown)}{RESET}")
    dropped = [k for k in TOOL_METADATA_DROPPED if k in metadata]
    if dropped:
        print(f"{YELLOW}dropping retired metadata keys: {', '.join(dropped)}{RESET}")
    keys = [k for k in TOOL_METADATA_KEYS if k in metadata] + unknown
    lines = ["[tool.metadata]"]
    for key in keys:
        lines.append(f"{key} = {_toml_value(metadata[key])}")
    return "\n".join(lines) + "\n"


def load_tool_metadata(project: dict, pixi_toml: Path) -> dict:
    """The metadata to emit, from ``pixi.toml`` if it has it, else from the YAML.

    ``examples_config`` in anaconda-project.yml is the pre-migration home of
    this metadata; once it has moved, ``[tool.metadata]`` in pixi.toml is the
    single source of truth and the YAML no longer carries it, so a regeneration
    must read back what is already there rather than silently drop it.

    ``description`` is the one key that was never part of ``examples_config``:
    it lives at the root of the YAML (and used to be emitted as ``[workspace]
    description``), so it is folded in here.
    """
    metadata: dict = {}
    if pixi_toml.exists():
        parsed = tomllib.loads(pixi_toml.read_text())
        metadata = dict(parsed.get("tool", {}).get("metadata") or {})
    if not metadata:
        metadata = dict(project.get("examples_config") or {})
    if "description" not in metadata and project.get("description"):
        metadata["description"] = project["description"]
    return metadata


def build_pixi_toml(
    project,
    channels,
    conda_specs,
    pip_specs,
    conda_global_extras,
    target_extras,
    pypi_global_extras,
    metadata=None,
) -> str:
    """Render pixi.toml.

    ``conda_global_extras`` / ``target_extras`` / ``pypi_global_extras`` are
    packages present in the lock but not reachable from the declared deps;
    they are added as dependencies so the lock's contents equal the
    dependency closure (else pixi rewrites the lock).

    ``metadata`` is the project metadata emitted as ``[tool.metadata]`` (see
    ``load_tool_metadata``).  ``[workspace]`` deliberately carries nothing but
    what pixi itself needs (``name`` / ``channels`` / ``platforms``): the
    ``description``, ``authors`` and ``version`` keys it used to hold were just
    copies of ``description``, ``maintainers`` and ``created``, and a second
    home for a value only invites the two drifting apart.
    """
    platforms = project.get("platforms", [])
    metadata = metadata or {}
    deps = [matchspec_to_pixi(p) for p in conda_specs]
    seen_dep_names: set[str] = set()
    deps = [(n, v) for n, v in deps if not (n in seen_dep_names or seen_dep_names.add(n))]
    pip_deps = [pip_requirement_to_pypi(p) for p in pip_specs]

    lines = ["[workspace]", f"name = {json.dumps(project['name'])}"]
    lines.append("channels = [" + ", ".join(json.dumps(c) for c in channels) + "]")
    lines.append("platforms = [" + ", ".join(json.dumps(p) for p in platforms) + "]")
    tool_metadata = build_tool_metadata(metadata)
    if tool_metadata:
        lines.append("")
        lines.append(tool_metadata.rstrip("\n"))
    lines.append("")
    lines.append("[dependencies]")
    for name, ver in deps:
        lines.append(_dep_line(name, ver))
    for name in sorted(conda_global_extras):
        lines.append(_dep_line(name, "*") + "  # promoted from anaconda-project lock")
    for plat in platforms:
        names = sorted(target_extras.get(plat, ()))
        if names:
            lines.append("")
            lines.append(f"[target.{plat}.dependencies]")
            for name in names:
                lines.append(_dep_line(name, "*") + "  # promoted from anaconda-project lock")
    if pip_deps or pypi_global_extras:
        lines.append("")
        lines.append("[pypi-dependencies]")
        for name, ver, extras in pip_deps:
            lines.append(_pypi_dep_line(name, ver, extras))
        for name in sorted(pypi_global_extras):
            lines.append(_dep_line(name, "*") + "  # promoted from anaconda-project lock")
    download_blocks, download_names = build_download_tasks(project.get("downloads") or {})
    activation = build_activation_env(project.get("variables") or {})
    if activation:
        lines.append("")
        lines.append(activation.rstrip("\n"))
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
    """Return ({platform: [(name, version, build), ...]}, [(pip_name, pip_version), ...]).

    Which subdir a bucket implies is deliberately not recorded: a package is
    resolved from its platform's own subdir or from ``noarch`` regardless of
    the bucket it was listed under (anaconda-project's buckets are not always
    truthful - a concrete ``win-64`` bucket can hold a package that only ships
    for linux).
    """
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
        targets = (NONARCH_BUCKETS[bucket] or platforms) if bucket in NONARCH_BUCKETS else [bucket]
        for entry in entries:
            name, version, build = entry.split("=")
            for plat in targets:
                if plat in per_platform:
                    per_platform[plat].append((name, version, build))
    return per_platform, pip_entries


# --------------------------------------------------------------------------- #
# enrichment via repodata.json (downloaded once per channel+subdir, then cached)
# --------------------------------------------------------------------------- #
def _plain(value):
    """Detach a lazily parsed simdjson value from the parser that owns it."""
    if isinstance(value, simdjson.Array):
        return value.as_list()
    if isinstance(value, simdjson.Object):
        return value.as_dict()
    return value


def _filename_key(filename: str) -> tuple[str, str, str] | None:
    """``zlib-1.3.1-h4bc722e_2.conda`` -> ('zlib', '1.3.1', 'h4bc722e_2')."""
    stem = filename.removesuffix(".conda").removesuffix(".tar.bz2")
    try:
        name, version, build = stem.rsplit("-", 2)
    except ValueError:
        return None
    return name, version, build


class Enricher:
    """Resolve the lock's ``name=version=build`` pins to full repodata records.

    A channel+subdir holds up to a few hundred thousand packages while a lock
    pins a few hundred, so repodata is never deserialised wholesale: simdjson
    parses the document lazily and only records whose *filename* matches a pin
    are converted to Python objects.  Two levels of cache keep repeat runs off
    that path entirely - the compressed download is kept verbatim, and the
    resolved records are memoised per pin set.  Neither is ever invalidated:
    these projects are frozen, so re-fetching could only introduce drift.
    """

    def __init__(
        self,
        cache_dir: Path,
        channels: list[str],
        pins_by_platform: dict[str, set[tuple[str, str, str]]],
    ):
        self.cache_dir = cache_dir / "repodata"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.channels = [_lock_channel_url(c).rstrip("/") for c in channels]
        # (subdir, name, version, build) -> record-with-url, filled in as repodata
        # is read.  The subdir belongs in the key: a pin can exist in several
        # subdirs (e.g. _openmp_mutex=4.5=2_gnu ships for both linux-64 and
        # win-64), and without it the first subdir read would answer for every
        # platform, putting a foreign URL in the lock.
        self._index: dict[tuple[str, str, str, str], dict] = {}
        self._loaded: set[tuple[str, str]] = set()  # (channel, subdir) already read
        self._pins_by_platform = pins_by_platform
        self._pins = {pin for pins in pins_by_platform.values() for pin in pins}
        # the only filenames worth converting
        self._wanted = {
            f"{n}-{v}-{b}.{ext}": (n, v, b)
            for n, v, b in self._pins
            for ext in ("conda", "tar.bz2")
        }
        # pins that no subdir they are needed in could supply (see _resolve_drift)
        self._pending: set[tuple[str, str, str]] = set()

    # Fields needed by record_to_locked() and lookup()'s fallback sort.
    _KEEP = frozenset(
        (
            "name",
            "version",
            "build",
            "build_number",
            "subdir",
            "depends",
            "constrains",
            "license",
            "license_family",
            "md5",
            "sha256",
            "size",
            "timestamp",
        )
    )

    def _cache_path(self, channel: str, subdir: str) -> Path:
        slug = hashlib.sha1(f"{channel}/{subdir}".encode()).hexdigest()[:16]
        return self.cache_dir / f"{slug}.json.zst"

    def _memo_path(self) -> Path:
        """Cache file for the records this exact set of pins resolves to."""
        sig = "\n".join(
            ["v2-subdir-keyed", *sorted(self._KEEP), *self.channels]
            + [
                f"{plat}:{n}={v}={b}"
                for plat in sorted(self._pins_by_platform)
                for n, v, b in sorted(self._pins_by_platform[plat])
            ]
        )
        slug = hashlib.sha1(sig.encode()).hexdigest()[:16]
        return self.cache_dir.parent / "resolved" / f"{slug}.json"

    def _repodata(self, channel: str, subdir: str) -> bytes | None:
        """repodata.json for one channel+subdir, downloaded at most once ever.

        Returns None for a subdir the channel does not publish; that 404 is
        remembered as an empty cache file so later runs stay offline.
        """
        cache_file = self._cache_path(channel, subdir)
        if cache_file.exists():
            blob = cache_file.read_bytes()
        else:
            url = f"{channel}/{subdir}/repodata.json.zst"
            print(f"fetching {url}...")
            try:
                with urllib.request.urlopen(url) as resp:
                    blob = resp.read()
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                blob = b""
            print(CLEAR, end="")
            cache_file.write_bytes(blob)
        return zstandard.decompress(blob) if blob else None

    def _read(self, channel: str, subdir: str, stems: tuple[str, ...] | None = None) -> None:
        """Index one channel+subdir, converting only the records we asked for.

        Without ``stems`` a record is taken when its filename is exactly one of
        the pins; with ``stems`` any build of those ``name-version-`` prefixes
        is taken instead (see _resolve_drift).
        """
        raw = self._repodata(channel, subdir)
        if raw is None:
            return
        # A parser owns the document it parsed, so keep it local: nothing may
        # outlive this call except the plain dicts built below.
        doc = simdjson.Parser().parse(raw)
        # ``packages`` (.tar.bz2) before ``packages.conda``, and first match
        # wins, so channel order decides which URL a pin resolves to.
        for section in ("packages", "packages.conda"):
            packages = doc.get(section)
            if packages is None:
                continue
            for filename in packages.keys():
                if stems is None:
                    key = self._wanted.get(filename)
                else:
                    key = _filename_key(filename) if filename.startswith(stems) else None
                if key is None:
                    continue
                subdir_key = (subdir, *key)
                if subdir_key in self._index:
                    continue
                rec = packages[filename]
                entry = {f: _plain(rec[f]) for f in self._KEEP if f in rec}
                entry["url"] = f"{channel}/{subdir}/{filename}"
                self._index[subdir_key] = entry
                self._pending.discard(key)

    def _load(self, channel: str, subdir: str) -> None:
        if (channel, subdir) in self._loaded:
            return
        self._loaded.add((channel, subdir))
        self._read(channel, subdir)

    def _resolve_drift(self) -> None:
        """Re-read for pins whose exact build has left the channel.

        Rare, so it is only paid for when the filename-exact pass came up
        short: the outstanding ``name-version`` are searched again, this time
        accepting any build, which is what lookup()'s fallback picks from.
        """
        if not self._pending:
            return
        stems = tuple(sorted({f"{n}-{v}-" for n, v, _ in self._pending}))
        for channel, subdir in list(self._loaded):
            self._read(channel, subdir, stems)

    def _unresolved(self) -> set[tuple[str, str, str]]:
        """Pins that no subdir they are pinned for can supply.

        A pin is only satisfied by a record in its own platform's subdir or in
        ``noarch``; finding it under some *other* platform proves nothing, so
        the check is per platform rather than over the index as a whole.
        """
        return {
            pin
            for plat, pins in self._pins_by_platform.items()
            for pin in pins
            if (plat, *pin) not in self._index and ("noarch", *pin) not in self._index
        }

    def prefetch(self) -> None:
        """Resolve every pin, reading each channel+subdir at most once.

        The result is memoised, so converting the same project again costs one
        small JSON read instead of a walk over every channel's repodata.
        """
        memo = self._memo_path()
        if memo.exists():
            self._index = {tuple(key): entry for key, entry in orjson.loads(memo.read_bytes())}
            self._pending.clear()
            return
        for plat in self._pins_by_platform:
            for ch in self.channels:
                self._load(ch, plat)
                self._load(ch, "noarch")
        self._pending = self._unresolved()
        self._resolve_drift()
        memo.parent.mkdir(parents=True, exist_ok=True)
        memo.write_bytes(orjson.dumps(list(self._index.items())))

    def lookup(self, name, version, build, platform) -> dict:
        """Record for one pin on one platform, from that platform's own subdir.

        Only ``platform``'s subdir and ``noarch`` may answer: a record from
        another platform's subdir would put a URL in the lock that cannot be
        installed there (and whose ``depends`` belong to that other platform).
        """
        subdirs = (platform, "noarch")
        for subdir in subdirs:
            if (subdir, name, version, build) in self._index:
                return self._index[(subdir, name, version, build)]
        # Fallback: exact build is gone from the channel. Prefer the newest
        # build_number among the builds still published for this platform.
        cands = [
            r
            for (sd, n, v, _), r in self._index.items()
            if (n, v) == (name, version) and sd in subdirs
        ]
        if not cands:
            available = sorted(
                f"{sd}/{r.get('build')}"
                for (sd, n, v, _), r in self._index.items()
                if (n, v) == (name, version)
            )
            raise LookupError(
                f"no record for {name}=={version}=={build} in subdir {platform} or noarch; "
                "available builds: " + (", ".join(available) or "none")
            )
        cands.sort(key=lambda r: r.get("build_number", 0), reverse=True)
        return cands[0]


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


def _platform_tags_ok(tag: str, platform: str) -> bool:
    """A wheel may carry several platform tags (``a.b``); any match will do."""
    return any(_platform_tag_ok(t, platform) for t in tag.split("."))


def _cpython_version(tag: str) -> tuple[int, int] | None:
    """``cp311`` -> (3, 11).  The major is always the first digit."""
    if not re.fullmatch(r"cp\d\d+", tag):
        return None
    return int(tag[2]), int(tag[3:])


def _abi3_version(python_tag: str, abi_tag: str) -> tuple[int, int] | None:
    """Lowest cpython an ``abi3`` wheel supports, or None if it is not abi3.

    ``cp39-abi3`` is built against the stable ABI, so pip installs it on 3.9
    *and every later* cpython - the exact python-tag match below never sees
    these, which is how such packages used to end up locked as sdists.
    """
    if abi_tag != "abi3":
        return None
    versions = [v for t in python_tag.split(".") if (v := _cpython_version(t))]
    return min(versions) if versions else None


def _is_pure_python(python_tag: str) -> bool:
    return all(t.startswith("py") for t in python_tag.split("."))


def _pick_wheel(files: list[dict], platform: str, py_tag: str) -> dict | None:
    """Pick the wheel matching ``platform``/``py_tag``, preferring pure-python wheels."""
    target = _cpython_version(py_tag)
    exact: list[dict] = []
    abi3: list[tuple[tuple[int, int], dict]] = []
    pure_platform: list[dict] = []
    for f in files:
        python_tag, abi_tag, platform_tag = _wheel_tags(f["filename"])
        if platform_tag == "any":
            if _is_pure_python(python_tag):
                return f
            continue
        if not _platform_tags_ok(platform_tag, platform):
            continue
        if py_tag in python_tag.split("."):
            exact.append(f)
        elif (v := _abi3_version(python_tag, abi_tag)) and target and v <= target:
            abi3.append((v, f))
        elif _is_pure_python(python_tag):
            pure_platform.append(f)
    if exact:
        return exact[0]
    if abi3:
        return max(abi3, key=lambda t: t[0])[1]  # newest stable-ABI build
    if pure_platform:
        return pure_platform[0]
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
            return orjson.loads(resp.read())

    def _release(self, name: str, version: str) -> dict:
        key = f"{name}=={version}"
        if key in self.mem:
            return self.mem[key]
        cache_file = self._cache_file(name, version)
        if cache_file.exists():
            data = orjson.loads(cache_file.read_bytes())
        else:
            data = self._fetch(name, version)
            cache_file.write_bytes(orjson.dumps(data))
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


def _python_tag_for(per_platform_entries: list[tuple[str, str, str]]) -> str:
    for name, version, _build in per_platform_entries:
        if name == "python":
            major, minor = version.split(".")[:2]
            return f"cp{major}{minor}"
    raise ValueError("no 'python' package found in lock; cannot pick pypi wheels")


def _canonical_pypi(name: str) -> str:
    """PEP 503 normalisation: ``Zope.Interface`` -> 'zope-interface'."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _pypi_req_name(req: str) -> str:
    """Name of a PEP 508 requirement: ``h5io; extra == "hdf5"`` -> 'h5io'."""
    head = req.split(";", 1)[0].strip()
    return _canonical_pypi(re.split(r"[\s<>=!~,()\[\]]", head, maxsplit=1)[0])


def base_package_purls(
    conda_names: set[str], pypi_req_names: set[str], locked_pypi: set[str]
) -> dict[str, str]:
    """Map conda ``<x>-base`` package name -> the pypi name ``x`` it provides.

    conda-forge often ships "<name>" (full) and "<name>-base" (core only,
    e.g. mne/mne-base, matplotlib/matplotlib-base) and registers the "-base"
    package with its hash-mapping service as already providing the plain pypi
    name - which is why anaconda-project's solver found ``mne[hdf5]`` and
    pydeseq2's ``matplotlib>=3.6.2`` satisfied without a pip install.  pixi
    matches conda packages to pypi requirements by name, so only this renaming
    needs stating explicitly: a real ``pixi lock`` does it with a ``purls``
    entry (``pkg:pypi/mne?source=hash-mapping``), and since the anaconda lock
    already tells us the "-base" package and its version are present, that fact
    can be reproduced without invoking pixi.  Without it pixi reports the
    requirement as unsatisfiable and rewrites the lock.
    """
    purls: dict[str, str] = {}
    for cname in conda_names:
        if not cname.endswith("-base"):
            continue
        pypi_name = _canonical_pypi(cname[: -len("-base")])
        if pypi_name in pypi_req_names and pypi_name not in locked_pypi:
            purls[cname] = pypi_name
    return purls


def build_pixi_lock(
    per_platform,
    pip_specs,
    pip_entries,
    enricher,
    pypi_enricher,
    platforms,
    channels,
    swallowed=frozenset(),
):
    """Emit the pixi.lock document plus the per-platform dependency graph.

    ``swallowed`` names were dropped from the conda side because pip overrides
    them (see ``main``).  Conda packages that still depend on them would leave
    the lock with a requirement nothing can satisfy - pixi reports exactly that
    as "out of date" - so those dependency entries are dropped from the locked
    metadata as well.  The graph keeps them: it is matched by name against the
    pypi package that took over, which is what actually provides the import.
    """
    pkg_by_url: dict[str, dict] = {}
    conda_name_by_url: dict[str, str] = {}
    env_pkgs: dict[str, list[tuple[str, str]]] = {p: [] for p in platforms}
    graph: dict[str, list[dict]] = {p: [] for p in platforms}
    has_pypi = False
    relaxed: set[str] = set()
    # every pypi name something in this environment requires: the declared pip
    # specs plus the requirements of each locked wheel
    pypi_req_names = {_canonical_pypi(pip_requirement_to_pypi(p)[0]) for p in pip_specs}

    enricher.prefetch()
    if pip_entries:
        pypi_enricher.prefetch(pip_entries)

    for plat in platforms:
        for name, version, build in per_platform[plat]:
            rec = enricher.lookup(name, version, build, plat)
            url = rec["url"]
            env_pkgs[plat].append(("conda", url))
            graph[plat].append({"name": rec["name"], "depends": rec.get("depends") or []})
            if url not in pkg_by_url:
                entry = record_to_locked(rec)
                if swallowed and entry.get("depends"):
                    kept = [d for d in entry["depends"] if _dep_name(d) not in swallowed]
                    if len(kept) != len(entry["depends"]):
                        relaxed.add(rec["name"])
                        entry["depends"] = kept
                pkg_by_url[url] = entry
                conda_name_by_url[url] = rec["name"]

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
                pypi_req_names.update(_pypi_req_name(r) for r in rec.get("requires_dist") or [])
                if url not in pkg_by_url:
                    pkg_by_url[url] = record_to_locked_pypi(rec)

    purls = base_package_purls(
        set(conda_name_by_url.values()),
        pypi_req_names,
        {_canonical_pypi(n) for n, _ in pip_entries},
    )
    for url, cname in conda_name_by_url.items():
        if cname in purls:
            pkg_by_url[url]["purls"] = [f"pkg:pypi/{purls[cname]}?source=hash-mapping"]

    # Mirror the manifest channel set/order so pixi considers the lock current.
    # v7 adds the top-level ``platforms`` block; package ordering is cosmetic
    # (pixi re-sorts on write) and does not affect the up-to-date check.
    default_env = {
        "channels": [{"url": _lock_channel_url(c)} for c in channels],
    }
    if has_pypi:
        default_env["indexes"] = ["https://pypi.org/simple"]
    default_env["packages"] = {
        p: [{kind: u} for kind, u in sorted(set(env_pkgs[p]), key=lambda t: t[1])]
        for p in sorted(platforms)
    }
    lock = {
        "version": 7,
        "platforms": [{"name": p} for p in sorted(platforms)],
        "environments": {"default": default_env},
        "packages": [pkg_by_url[u] for u in sorted(pkg_by_url)],
    }
    if relaxed:
        print(
            "dropped conda dependencies on pip-overridden packages from: "
            + ", ".join(sorted(relaxed))
        )
    if purls:
        print(
            "tagging conda '-base' packages as already providing their pypi name: "
            + ", ".join(f"{base} -> {name}" for base, name in sorted(purls.items()))
        )
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


def check_pixi_manifest(pixi_lock: dict, enricher: Enricher) -> bool:
    """Validate the generated lock by cross-checking every locked conda package
    against the repodata index already loaded by ``enricher``.

    Each locked package URL must resolve to an entry in the repodata for the
    *same subdir*, with matching name, version, and build — catching any
    corruption or URL drift introduced during lock generation, including a
    package pointing at another platform's copy.
    """
    ok = True
    for pkg in pixi_lock["packages"]:
        if "conda" not in pkg:
            continue
        url = pkg["conda"]
        _channel, subdir, filename = url.rsplit("/", 2)
        stem = filename.removesuffix(".conda").removesuffix(".tar.bz2")
        try:
            name, version, build = stem.rsplit("-", 2)
        except ValueError:
            print(f"{RED}  MALFORMED URL  {url}{RESET}")
            ok = False
            continue
        key = (subdir, name, version, build)
        if key not in enricher._index:
            print(f"{RED}  NOT IN REPODATA  {subdir}/{name}={version}={build}{RESET}")
            ok = False
        elif enricher._index[key]["url"] != url:
            print(f"{YELLOW}  URL DRIFT  {name}={version}={build}: {url}{RESET}")
    if ok:
        print(f"{GREEN}repodata check passed{RESET}")
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
    pypi_names_lower = {name.casefold() for name, _ in pip_entries}

    # A package locked by both conda (usually transitively) and pip is a pip
    # override: anaconda-project installs the pip wheel on top, but pixi's
    # solver pins the conda version and conflicts with the pypi requirement.
    # Swallow the conda side so only the pypi package is locked.
    # Comparison is case-insensitive (e.g. conda "markdown" vs pip "Markdown").
    swallowed = {
        name
        for plat in platforms
        for name, *_ in per_platform[plat]
        if name.casefold() in pypi_names_lower
    }
    if swallowed:
        print(f"swallowing conda packages overridden by pip: {', '.join(sorted(swallowed))}")
        per_platform = {
            plat: [e for e in entries if e[0] not in swallowed]
            for plat, entries in per_platform.items()
        }

    enricher = Enricher(
        args.cache_dir,
        channels,
        {plat: {(n, v, b) for n, v, b in entries} for plat, entries in per_platform.items()},
    )
    pypi_enricher = PypiEnricher(args.cache_dir / "pypi")
    pixi_lock, graph = build_pixi_lock(
        per_platform,
        pip_specs,
        pip_entries,
        enricher,
        pypi_enricher,
        platforms,
        channels,
        swallowed,
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
    pypi_global_extras = {n for n in global_extras if n.casefold() in pypi_names_lower}
    conda_global_extras = {n for n in global_extras if n.casefold() not in pypi_names_lower}
    toml_text = build_pixi_toml(
        project,
        channels,
        conda_specs,
        pip_specs,
        conda_global_extras,
        target_extras,
        pypi_global_extras,
        load_tool_metadata(project, project_dir / "pixi.toml"),
    )
    (out_dir / "pixi.toml").write_text(toml_text)
    print(f"{GREEN}wrote {out_dir / 'pixi.toml'}{RESET}")

    if not check_pixi_manifest(pixi_lock, enricher):
        return 1

    if not args.no_verify:
        print()
        if not verify_lock(project_dir, pixi_lock, platforms, swallowed):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
