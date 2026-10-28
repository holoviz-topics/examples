"""Project helpers shared by the docs build (``doc/conf.py`` and the local Sphinx extensions)."""

import os
import pathlib
import subprocess
import tomllib

PROJECT_FILE = 'pixi.toml'

# Categories are displayed in this order on the website.
CATNAME_TO_CAT_MAP = {
    '⭐ Featured': ['Featured'],
    'Geospatial': ['Geospatial'],
    'Finance and Economics': ['Finance', 'Economics'],
    'Mathematics': ['Mathematics'],
    'Neuroscience': ['Neuroscience'],
    'Cybersecurity and Networks': ['Cybersecurity', 'Networks'],
    'Other Sciences': ['Other Sciences'],
    'Sports': ['Sports'],
}

CAT_TO_CATNAME_MAP = {
    category: catname
    for catname, categories in CATNAME_TO_CAT_MAP.items()
    for category in categories
}

DOC_EXCLUDE = ['_static', '_templates']
# The template project is only shown on the dev site.
if os.getenv('EXAMPLES_HOLOVIZ_DEV_SITE') is None:
    DOC_EXCLUDE.append('template')

LAST_UPDATED_PATTERNS = [
    # Notably excluded: pixi.toml (website metadata) and thumbnails/.
    '*.ipynb',
    '*.py',
    'pixi.lock',
    'catalog.yml',
    'assets',
    'data',
]


def project_dir_names(root, exclude=()):
    return sorted(
        path.name
        for path in pathlib.Path(root).iterdir()
        if path.is_dir() and path.name not in exclude
    )


def project_spec(name, root):
    with open(pathlib.Path(root, name, PROJECT_FILE), 'rb') as f:
        return tomllib.load(f)


def project_metadata(name, root):
    return project_spec(name, root).get('tool', {}).get('metadata', {})


def projname_to_title(name):
    return name.replace('_', ' ').title()


def find_notebooks(name, root):
    skip = set(project_metadata(name, root).get('notebooks_to_skip', []))
    return sorted(
        nb for nb in pathlib.Path(root, name).glob('*.ipynb') if nb.name not in skip
    )


def ignored_revs(root):
    path = pathlib.Path(root, '.git-blame-ignore-revs')
    if not path.is_file():
        return set()
    revs = (line.split('#', 1)[0].strip() for line in path.read_text().splitlines())
    return {rev for rev in revs if rev}


def last_commit_date(name, root):
    """Last commit date of the project content, as YYYY-MM-DD.

    Commits in .git-blame-ignore-revs (e.g. bulk updates of every project) are skipped.
    """
    paths = []
    for pattern in LAST_UPDATED_PATTERNS:
        paths.extend(pathlib.Path(root, name).glob(pattern))
    result = subprocess.run(
        ['git', 'log', '--pretty=format:%H %cs', '--', *map(str, paths)],
        check=True, capture_output=True, text=True,
    )
    ignored = ignored_revs(root)
    for line in result.stdout.splitlines():
        sha, date = line.split()
        if not any(sha.startswith(rev) for rev in ignored):
            return date
    raise ValueError(f'Last commit date not found for {name}')
