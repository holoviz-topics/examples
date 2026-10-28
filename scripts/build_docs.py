"""Prepare doc/gallery/ for the Sphinx build.

Usage:
    python scripts/build_docs.py

Expects the evaluated notebooks in ``doc/gallery/<project>/`` (from the
``evaluated`` branch and/or the build artifacts). For every project there:

    - write the downloadable archive to ``doc/gallery/<project>/_archive/<project>.zip``,
      made of the project's git-tracked files plus a README;
    - copy the project's other tracked files (thumbnails, assets, data, ...),
      except notebooks and project files, so Sphinx can reference them.

Folders in doc/gallery/ without an evaluated notebook are removed, and so are
folders that are not a project anymore.

Tracked files are used, so data downloaded locally and ``.pixi/`` never end up
in the archive or website.
"""

import fnmatch
import pathlib
import shutil
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

GALLERY = ROOT / "doc" / "gallery"

PROJECT_FILE = "pixi.toml"

README_TEMPLATE = ROOT / "readme_template.md"

DOC_DIRS = ["_static", "_templates"]

CONTENT_EXCLUDE = [
    "*.ipynb",
    ".gitignore",
    "pixi.toml",
    "pixi.lock",
]


def tracked_files(name):
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", name],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.decode()
    return [pathlib.Path(p) for p in out.split("\0") if p]


def _excluded(path, patterns):
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in patterns)


def archive_project(name, files):
    archive_dir = GALLERY / name / "_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / f"{name}.zip"
    print(f"Archiving {name} to {archive.relative_to(ROOT)}")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(ROOT / path, path.as_posix())
        if not any(path.name == "README.md" and len(path.parts) == 2 for path in files):
            zf.write(README_TEMPLATE, f"{name}/README.md")


def copy_content(name, files):
    for path in files:
        if _excluded(path, CONTENT_EXCLUDE):
            continue
        dst = GALLERY / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, dst)


def main():
    if not GALLERY.is_dir():
        sys.exit(f"{GALLERY.relative_to(ROOT)} not found, fetch the evaluated notebooks first")

    for gallery_dir in sorted(GALLERY.iterdir()):
        name = gallery_dir.name
        if not gallery_dir.is_dir() or name in DOC_DIRS:
            continue
        if not (ROOT / name / PROJECT_FILE).is_file():
            print(f"Removing {gallery_dir.relative_to(ROOT)}: not a project")
            shutil.rmtree(gallery_dir)
            continue
        if not any(gallery_dir.glob("*.ipynb")):
            print(f"Removing {gallery_dir.relative_to(ROOT)}: no evaluated notebook")
            shutil.rmtree(gallery_dir)
            continue
        files = tracked_files(name)
        archive_project(name, files)
        copy_content(name, files)


if __name__ == "__main__":
    main()
