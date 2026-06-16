"""Cross-check generated pixi.lock against the anaconda lock pins."""
import sys
from pathlib import Path
import yaml

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
out = Path(sys.argv[2]) if len(sys.argv) > 2 else root

alock = yaml.safe_load((root / "anaconda-project-lock.yml").open())
plock = yaml.safe_load((out / "pixi.lock").open())

NONARCH = {"all": None, "unix": ["linux-64", "osx-64", "osx-arm64"],
           "osx": ["osx-64", "osx-arm64"], "linux": ["linux-64"], "win": ["win-64"]}
platforms = ["linux-64", "osx-64", "win-64", "osx-arm64"]

# expected (name, version, build) per platform from anaconda lock
spec = alock["env_specs"].get("default")
expected = {p: set() for p in platforms}
for bucket, entries in spec["packages"].items():
    targets = (NONARCH[bucket] or platforms) if bucket in NONARCH else [bucket]
    for e in entries:
        n, v, b = e.split("=")
        for p in targets:
            if p in expected:
                expected[p].add((n, v, b))

# got per platform from pixi.lock filenames: name-version-build.ext
got = {p: set() for p in platforms}
for p, items in plock["environments"]["default"]["packages"].items():
    for it in items:
        fn = it["conda"].rsplit("/", 1)[1]
        fn = fn.removesuffix(".conda").removesuffix(".tar.bz2")
        n, v, b = fn.rsplit("-", 2)
        got[p].add((n, v, b))

ok = True
for p in platforms:
    missing = expected[p] - got[p]
    extra = got[p] - expected[p]
    print(f"{p}: expected={len(expected[p])} got={len(got[p])} "
          f"missing={len(missing)} extra={len(extra)}")
    for m in sorted(missing):
        ok = False
        print(f"   MISSING {m[0]}={m[1]}={m[2]}")
    for x in sorted(extra):
        ok = False
        print(f"   EXTRA   {x[0]}={x[1]}={x[2]}")

print("\nRESULT:", "exact match" if ok else "MISMATCH")
sys.exit(0 if ok else 1)
