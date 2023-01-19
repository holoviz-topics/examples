# Only import from the standard lib, to keep this module easily importable!
# Inline external libraries imports.
import contextlib
import datetime
import glob
import imghdr
import json
import os
import pathlib
import shutil
import struct
import subprocess
import textwrap

##### Globals and default config #####

DEFAULT_EXCLUDE = [
    'doc',
    'envs',
    'test_data',
    'builtdocs',
    'template',
    'assets',
    'jupyter_execute',
    *glob.glob( '.*'),
    *glob.glob( '_*'),
]

DEFAULT_DOC_EXCLUDE = [
    '_static',
    '_templates',
]

NOTEBOOK_EVALUATION_TIMEOUT = 3600  # 1 hour, in seconds.

ENDPOINT_TEMPLATE_NOTEBOOK = 'https://{servername}-notebook.pyviz.demo.anaconda.com'
ENDPOINT_TEMPLATE_DASHBOARD = 'https://{servername}.pyviz.demo.anaconda.com'

#### doit config and shared parameters ####

DOIT_CONFIG = {
    "verbosity": 2,
    "backend": "sqlite3",
}

env_spec_param = {
    'name': 'env_spec',
    'long': 'env-spec',
    'type': str,
    'default': 'default'
}

githubrepo_param = {
    'name': 'githubrepo',
    'type': str,
    'default': 'pyviz-topics/examples'
}

name_param = {
    'name': 'name',
    'long': 'name',
    'type': str,
    'default': 'all'
}

sha_param = {
    'name': 'sha',
    'long': 'sha',
    'type': str,
    'default': ''
}

##### Exceptions ####

class ExamplesError(Exception):
    """Base error"""


class ValidationError(Exception):
    """Validation error"""


#### Utils ####

def all_project_names(root, exclude=DEFAULT_EXCLUDE):
    """
    Return a sorted list of the projects directory names.
    """
    if root == '':
        root = os.getcwd()
    root = os.path.abspath(root)
    projects = []
    for path in pathlib.Path(root).iterdir():
        if not path.is_dir():
            continue
        if path.name in exclude:
            continue
        projects.append(path.name)
    return sorted(projects)


def complain(msg):
    """
    Print a warning, unless the environment variable
    HOLOVIZ_EXAMPLES_WARNING_AS_ERROR is set to anything different than '0'.
    """
    if os.getenv('HOLOVIZ_EXAMPLES_WARNING_AS_ERROR', '0') != '0':
        raise ValidationError(msg)
    else:
        print('WARNING: ' + msg)


def deployment_cmd_to_endpoint(cmd, name):
    """
    Given a project command and a project name returns an endpoint.
    """
    servername = projname_to_servername(name)
    if cmd == 'notebook':
        endpoint = ENDPOINT_TEMPLATE_NOTEBOOK.format(servername=servername)
    elif cmd == 'dashboard':
        endpoint = ENDPOINT_TEMPLATE_DASHBOARD.format(servername=servername)
    else:
        raise ValueError(f'Unexpected command {cmd}')
    return endpoint


def find_notebooks(proj_dir_name, exclude_config=['skip']):
    """
    Find the notebooks in a project.
    """
    proj_dir = pathlib.Path(proj_dir_name)
    spec = project_spec(proj_dir_name)

    excluded = []
    if 'skip' in exclude_config:
        excluded.extend(spec.get('examples_config', {}).get('skip', []))

    notebooks = []
    for notebook in proj_dir.glob('*.ipynb'):
        if notebook.name in excluded:
            continue
        notebooks.append(notebook)
    return notebooks


def get_png_dims(fname):
    """
    From https://stackoverflow.com/a/20380514/10875966
    """
    with open(fname, 'rb') as fhandle:
        head = fhandle.read(24)
        if len(head) != 24:
            raise ValueError
        imgtype = imghdr.what(fname)
        if imghdr.what(fname) == 'png':
            check = struct.unpack('>i', head[4:8])[0]
            if check != 0x0d0a1a0a:
                return
            width, height = struct.unpack('>ii', head[16:24])
        else:
            raise ValueError(f'Only supports PNG, not {imgtype}')
        return width, height


def last_commit_date(name, root='.', verbose=True):
    """
    Return the last committer data as 'YYYY-MM-DD'
    """
    proc = subprocess.run(
        [f'git log -n 1 --pretty=format:%cs {root}/{name}'],
        check=True, capture_output=True, text=True, shell=True,
    )
    last_committer_date = proc.stdout
    if not last_committer_date:
        raise ValueError('Last commit date not found')
    if verbose:
        print(f'Last commit date: {last_committer_date}')
    return last_committer_date


def print_changes_in_dir(filepath='.diff'):
    """Dumps as JSON a dict of the changed projects and removed projects.
    
    New projects are in the changed list.
    """
    paths = pathlib.Path(filepath).read_text().splitlines()
    paths = [pathlib.Path(p) for p in paths]
    all_projects = set(all_project_names(root=''))
    changed_dirs = []
    removed_dirs = []
    for path in paths:
        root = path.parts[0]
        if pathlib.Path(root).is_file():
            continue
        if root in DEFAULT_EXCLUDE:
            pass
        elif root in all_projects:
            changed_dirs.append(root)
        else:
            removed_dirs.append(root)

    changed_dirs = sorted(set(changed_dirs))
    removed_dirs = sorted(set(removed_dirs))
    updates = {
        'changed': changed_dirs,
        'removed': removed_dirs
    }
    print(json.dumps(updates))


def project_has_data_folder(name):
    """Whether a project has a data folder"""
    path = pathlib.Path(name) / 'data'
    if not path.is_dir():
        return False
    has_files = not any(path.iterdir())
    return has_files


def project_has_no_data_ingestion(name):
    """Whether a project defines `no_data_ingestion` to True"""
    spec = project_spec(name)
    return spec.get('examples_config', {}).get('no_data_ingestion', False)


def project_has_downloads(name):
    """Whether a project has a non-empty `downloads` section."""
    spec = project_spec(name)
    downloads = spec.get('downloads', {})
    return bool(downloads)


def project_has_intake_catalog(name):
    """Whether a project has an Intake catalog"""
    path = pathlib.Path(name) / 'catalog.yml'
    return path.is_file()


def project_has_test_catalog(name):
    """Whether a project has a test catalog"""
    path = pathlib.Path('test_data') / name / 'catalog.yml'
    return path.exists()


def project_has_test_data(name):
    """Whether a project has a test data"""
    path = pathlib.Path('test_data') / name
    if not path.is_dir():
        return False
    has_files = not any(path.iterdir())
    return has_files


def remove_empty_dirs(path):
    """
    Remove all the empty dirs in a tree, including the root.
    """
    # Remove children dirs
    for root, dirnames, _ in os.walk(path, topdown=False):
        for dirname in dirnames:
            p = os.path.realpath(os.path.join(root, dirname))
            error = False
            try:
                os.rmdir(p)
            except OSError:
                error = True
            if not error:
                print(f'Removed empty dir {p}')
    # Remove root dir
    error = False
    try:
        os.rmdir(path)
    except OSError:
        error = True
    if not error:
        print(f'Removed empty dir {path}')


@contextlib.contextmanager
def removing_files(paths, verbose=True):
    """
    Context manager to remove a list of files on exit, if they were
    not already there on enter.
    """
    already_there = []
    for path in paths:
        already_there.append(path.is_file())
    yield
    for path in paths:
        if path not in already_there:
            if path.is_file():
                if verbose:
                    print(f'Removing {path}')
                path.unlink()


def _prepare_paths(root, name, test_data, filename='catalog.yml'):
    """
    Return a dict of paths, useful to deal with the test data.
    """
    if root == '':
        root = os.getcwd()
    root = os.path.abspath(root)
    test_data = test_data if os.path.isabs(test_data) else os.path.join(root, test_data)
    test_path = os.path.join(test_data, name)
    project_path = os.path.join(root, name)
    return {
        # Path to the project, e.g. ./projname
        'project': project_path,
        # Path to the real data folder, e.g. ./projname/data
        'real': os.path.join(project_path, 'data'),
        # Path to the test data folder, e.g. ./test_data/projname
        'test': test_path,
        # Path to the real intake catalog, e.g. ./projname/catalog.yml
        'cat_real': os.path.join(project_path, filename),
        # Path to the real intake catalog, e.g. ./test_data/projname/catalog.yml
        'cat_test': os.path.join(test_path, filename),
        # Path to the temporary intake catalog, e.g. ./projname/tmp_catalog.yml
        # This is used to store the original catalog
        'cat_tmp': os.path.join(project_path, 'tmp_' + filename),
    }


def project_spec(projname, filename='anaconda-project.yml'):
    """
    Return the spec of a project.
    """
    from yaml import safe_load

    path = pathlib.Path(projname) / filename
    with open(path, 'r') as f:
        spec = safe_load(f)
    return spec


def projname_to_servername(name):
    """
    Replace '_' by '-'. Assumes projname only has [a-z_]
    """
    return name.replace('_', '-')


def projname_to_title(name):
    """
    Replace '_' by ' ' and apply `.title()`. Assumes projname only has [a-z_]
    """
    return name.replace('_', ' ').title()


def should_skip_notebooks_evaluation(name):
    """
    Get the value of the special config `skip_notebooks_evaluation`.

    Use cases of skip_notebooks_evaluation:
    - notebooks that requires data downloaded only based on indications
    - notebooks that require too long downloads or too much data for the CI
    - notebooks that are too long to run on the CI
    - notebooks that need a special setup to run that is not compatible with the CI
    """
    spec = project_spec(name)
    skip_notebooks_evaluation = spec.get('examples_config', {}).get('skip_notebooks_evaluation', False)
    return skip_notebooks_evaluation


def should_skip_test(name):
    """
    Determines whether testing a project should be skipped.
    """
    skip_test = False
    if skip_test:
        print('skip_test: True')
    return False

    # TODO: remove it if not needed
    # Prepared for when skip_test is added
    spec = project_spec(name)
    skip_test = spec['examples_config'].get('skip_test', False)
    return skip_test



############# TASKS #############

#### Utils tasks ####


def task_util_last_commit_date():
    """
    Print the last committer date.
    """

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(last_commit_date, [name])]
        }


def task_util_list_changed_dirs_with_main():
    """
    Print the projects that changed compared to main
    """ 
    return {
        'actions': [
            'git fetch origin main',
            'git diff origin/main %(sha)s --name-only > .diff',
            print_changes_in_dir,
        ],
        'params': [sha_param],
        'teardown': ['rm -f .diff']
    }


def task_util_list_changed_dirs_with_last_commit():
    """
    Print the projects that changed compared to the last commit.
    """ 
    return {
        'actions': [
            'git diff HEAD^ HEAD --name-only > .diff',
            print_changes_in_dir,
        ],
        'teardown': ['rm -f .diff']
    }


def task_util_list_comma_separated_projects():
    """Print a list of projects found in .projects
    
    They are expected to be comma separated.
    """

    def list_comma_separated_projects(file='.projects'):
        file = pathlib.Path(file)
        if not file.exists():
            raise FileNotFoundError(f'File {file} not found')
        projects = file.read_text().strip()
        if not projects:
            raise ValueError(f'Missing comma separated projects in {file}')
        projects = projects.split(',')
        all_projects = all_project_names(root='')
        for project in projects:
            if project not in all_projects:
                raise ValueError(f'Listed project {project} not found, check its name.')
        print(projects)

    return {
        'actions': [list_comma_separated_projects],
    }


def task_util_list_project_dir_names():
    """Print a list of all the project directory names"""

    def list_project_dir_names():
        print(all_project_names(root=''))

    return {
        'actions': [list_project_dir_names],
    }

#### Validate ####



def task_validate_project_file():
    """Validate the existence and content of the anaconda-project.yml file"""

    def validate_project_file(name):
        from yaml import safe_load, YAMLError

        project = pathlib.Path(name) / 'anaconda-project.yml'
        if not project.exists():
            raise FileNotFoundError('Missing anaconda-project.yml file')

        with open(project, 'r') as f:
            try:
                spec = safe_load(f)
            except YAMLError as e:
                raise YAMLError('invalid file content') from e

        expected = [
            'name',
            'description',
            'examples_config',
            'user_fields',
            'channels',
            'packages',
            'dependencies',
            'commands',
            'platforms',
        ]
        for entry in expected:
            if entry not in spec:
                complain(f"Missing {entry!r} entry")

        project_name = spec.get('name', '')
        if project_name != name:
            complain(
                f'Project `name` {project_name!r} does not match the directory '
                f'name {name}',
            )
        if not all(c.islower() or c == "_" for c in project_name):
            complain(
                f'Project `name` {project_name!r} must only have lower-cased letters '
                'and underscores',
            )
        commands = spec.get('commands', {})
        if not all(expected_command in commands for expected_command in ['test', 'lint']):
            complain('Missing lint or test command')
        
        for cmd, cmd_spec in commands.items():
            if 'notebook' in cmd_spec and cmd != 'notebook':
                complain(
                    f'Command serving notebook must be called `notebook`, not {cmd!r}',
                )
            if ('unix' in cmd_spec and
                any(served in cmd_spec['unix'] for served in ('panel serve', 'lumen serve'))):
                if cmd != 'dashboard':
                    complain(
                        f'Command serving Panel/Lumen apps must be called `dashboard`, not {cmd!r}',
                    )
                if ('-rest-session-info' not in cmd_spec['unix'] and
                    '--session-history -1' not in cmd_spec['unix']):
                    complain(
                        'Command serving Panel/Lumen apps must set "-rest-session-info --session-history -1"',
                    )

        env_specs = spec.get('env_specs', {})
        if not all(expected_es in env_specs for expected_es in ['default', 'test']):
            complain('missing default or test env_spec')
        user_fields = spec.get('user_fields', [])
        if user_fields != ['examples_config']:
            complain('`user_fields` must be [examples_config]')

        config = spec.get('examples_config', [])
        expected = ['maintainers', 'labels']
        for entry in expected:
            if entry not in config:
                complain(f'missing {entry!r} list')
            value = config[entry]
            if not isinstance(value, list):
                complain(f'{entry!r} must be a list')
            if not all(isinstance(item, str) for item in value):
                complain(f'all values of {value!r} must be a string')
            if entry == 'labels':
                labels_path = pathlib.Path('doc') / '_static' / 'labels'
                labels = list(labels_path.glob('*.svg'))
                for label in value:
                    if not any(label_file.stem == label for label_file in labels):
                        complain(f'missing {label}.svg file in doc/_static/labels')

        created = config.get('created')
        if created:
            if not isinstance(created, datetime.date):
                complain('`created` value must be a date expressed as YYYY-MM-DD')
        else:
            complain('`created` entry not found')
        
        last_updated = config.get('last_updated', '')
        if last_updated and not isinstance(last_updated, datetime.date):
            complain('`last_updated` value must be a date expressed as YYYY-MM-DD')

        # TODO: title entry?
        # TODO: infer last updated automatically

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_project_file, [name])],
        }

def task_validate_project_lock():
    """Validate the existence of the anaconda-project-lock.yml file"""

    def validate_project_lock(name):
        from anaconda_project.project import Project

        with removing_files([pathlib.Path(name, '.projectignore')], verbose=False):
            project = Project(directory_path=name, must_exist=True)
            lock_path = pathlib.Path(project.lock_file.filename)
            if not lock_path.exists():
                complain(f'Missing {lock_path} file')
                return

            # Copied from https://github.com/Anaconda-Platform/anaconda-project/blob/a82a02083e9a19e9cfb33ca193737ed47fd7c914/anaconda_project/project.py#L758-L763
            for env_spec_name, env_spec in project.env_specs.items():
                locked_hash = env_spec.lock_set.env_spec_hash
                if locked_hash is not None and locked_hash != env_spec.logical_hash:
                    complain(
                        f"Env spec '{env_spec_name}' has changed since the lock file was last updated."
                    )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_project_lock, [name])],
        }

def task_validate_intake_catalog():
    """
    Validate that when a project has an intake catalog it is named
    catalog.yml and is at the root of project directory.
    """

    def validate_intake_catalog(name):
        import intake
        from intake.catalog.exceptions import ValidationError

        proj_dir = pathlib.Path(name)

        for path in proj_dir.glob('**/*'):
            if path.is_file() and path.suffix in ('.yml', '.yaml'):
                # Check if it's an intake catalog
                try:
                    intake.open_catalog(path)
                except ValidationError:
                    continue
                # If so, check it is at the expacted location.
                expected_path = proj_dir / 'catalog.yml'
                if path != expected_path:
                    complain(
                        f'Intake catalog must be saved at "{expected_path}", '
                        f'not at "{path}".'
                    )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_intake_catalog, [name])],
        }


def task_validate_data_sources():
    """Validate the data sources of a project

    For a project to have valid data sources it must have either:
    - a `downloads` section in its anaconda-project.yml file
    - an intake catalog
    - a `data/` subfolder containing files
    - the `no_data_ingestion` flag set to true in its `examples_config` spec
    """

    def validate_data_sources(name):
        has_downloads = project_has_downloads(name)

        if has_downloads:
            spec = project_spec(name)
            for var, dspec in spec['downloads'].items():
                dfilename = dspec.get('filename', '')
                if not dfilename:
                    complain(
                        f'`downloads` entry {var!r} must define `filename`'
                    )
                if not dfilename.startswith('data'):
                    complain(
                        f'`downloads` entry {var!r} must define `filename` '
                        'starting with "data"'
                    )

        has_intake_catalog = project_has_intake_catalog(name)
        has_data_folder = project_has_data_folder(name)
        has_no_data_ingestion = project_has_no_data_ingestion(name)

        if has_downloads and has_intake_catalog:
            raise NotImplementedError(
                'Relying on `downloads` in anaconda-project.yml and '
                'on an Intake catalog is not supported (may need updates '
                'in task_small_data_setup)'
            )

        # This used to be partially supported but was actually
        # not used by projects so was removed. The old code
        # can be found here:
        # https://github.com/pyviz-topics/examples/blob/d85de1c78f1351047c003cddd0d4b02603f08f2a/dodo.py#L49-L183
        if has_data_folder and (has_downloads or has_intake_catalog):
            raise NotImplementedError(
                'Relying on `downloads` in anaconda-project.yml OR '
                'on an Intake catalog, together with the presence of '
                'a `data/` folder is not supported (need updates in '
                'task_small_data_setup'
            )

        has_explicit_source = has_downloads or has_intake_catalog or has_data_folder
        if has_explicit_source and has_no_data_ingestion:
            complain(
                'The project set `no_data_ingestion` to True but has either '
                'a `downloads` section, an intake catalog or a `data` folder.'
            )
        if not has_explicit_source and not has_no_data_ingestion:
            complain(
                'The project does not define its data sources.',
            )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_data_sources, [name])],
        }


def task_validate_small_test_data():
    """Validate the small test data of a project, if relevant.
    
    Projects that have the following data sources must define small test data:
    - `downloads` defined in the anaconda-project.yml file
    - Intake catalog

    Small test data is added by populating the `./test_data/projname/` folder
    with data. If the project depends on an Intake catalog, a test catalog
    (catalog.yml) must be made available in `./test_data/projname/` too.

    This task just checks the existence of the small test data.
    """

    def validate_small_test_data(name):
        has_downloads = project_has_downloads(name)
        has_intake_catalog = project_has_intake_catalog(name)
        has_test_data = project_has_test_data(name)
        has_test_catalog = project_has_test_catalog(name)
        
        if has_downloads and not has_test_data:
            msg = (
                'Project defined `downloads` but did not provide test data in '
                f'test_data/{name}/'
            )
            complain(msg)
        if has_intake_catalog and not has_test_catalog:
            msg = (
                'Project has an Intake catalog but did not provide a test '
                f'catalog at test_data/{name}/catalog.yml '
            )
            complain(msg)


    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_small_test_data, [name])],
        }

def task_validate_index_notebook():
    """
    Validate that a project with multiple displayed notebooks has an index.ipynb notebook.
    """

    def validate_index_notebook(name):
        # Notebooks in skip don't need a thumbnail.
        notebooks = find_notebooks(name, exclude_config=['skip'])
        if not notebooks:
            raise ValueError('Project has no notebooks')
        # Not index.ipynb file, the project isn't displayed so just complain
        if len(notebooks) == 1:
            notebook = notebooks[0]
            if notebook.stem != name:
                complain(
                    f'Unique displayed notebook {notebook.name!r} does not '
                    f'match the directory name {name}.',
                )
        else:
            if not any(nb.stem == 'index' for nb in notebooks):
                complain(
                    f'{name}: has multiple files but no index.ipynb',
                )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_index_notebook, [name])],
        }

def task_validate_notebook_header():
    """
    Validate that a displayed notebook starts with a first level heading.
    """

    def validate_notebook_header(name):
        import nbformat

        # Notebooks in skip don't need a thumbnail.
        notebooks = find_notebooks(name, exclude_config=['skip'])
        for notebook in notebooks:
            nb = nbformat.read(notebook, as_version=4)
            first_cell = nb['cells'][0]
            if not first_cell['source'].startswith('# '):
                complain(
                    f'{notebook} must start with a 1st level heading e.g. "# A title"',
                )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_notebook_header, [name])],
        }


def task_validate_thumbnails():
    """Validated that the project has a thumbnail and that it's correct.
    
    - size < 1MB
    - 1 < aspect ratio < 1.2
    """

    def validate_thumbnails(name):
        thumb_folder = pathlib.Path(name) / 'thumbnails'
        if not thumb_folder.exists():
            complain("has no 'thumbnails/' folder")
            return
        # Notebooks in skip  don't need a thumbnail.
        notebooks = find_notebooks(name, exclude_config=['skip'])
        # Not index.ipynb file, the project isn't displayed so just complain
        if len(notebooks) > 1:
            if not any(nb.stem == 'index' for nb in notebooks):
                complain(
                    'has multiple files but no index.ipynb, thumbnails validation skipped',
                )
                return
            else:
                notebooks = [nb for nb in notebooks if nb.stem == 'index']

        notebook = notebooks[0]
        if not any(
            thumb.stem == notebook.stem
            for thumb in thumb_folder.glob('*.png')
        ):
            complain(f'has no PNG thumbnail for notebook {notebook.name}')
        thumb = thumb_folder / (notebook.stem + '.png')
        size = thumb.stat().st_size * 1e-6
        if size > 1:
            complain(f'thumbnail size ({size:.2f} MB) is above 1MB')
        w, h = get_png_dims(thumb)
        aspect_ratio = w / h
        if not (1.0 <= aspect_ratio <= 1.2):
            complain(
                f'thumbnail aspect ratio ({aspect_ratio:.2f}) must be between 1 and 1.2',
            )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_thumbnails, [name])],
        }


#### Test ###

def task_test_small_data_setup():
    """Copy small versions of the data from test_data/
    
    Small test data is available when a folder with the same name as the
    project's folder name is found in the `./test_data/` folder (it must
    include some files).

    If the project depends on an Intake catalog, and `./test_data/` contains
    an Intake catalog, the project's catalog will be temporarily replaced
    by the test catalog.

    All the data found in the `./test_data/projname/` folder, but the Intake
    catalog if any,  will be copied over to the `./projname/data/` folder.

    IMPORTANT: Test data for one project can depend on test data of another
    project (e.g. via relative links in the intake catalog). This does not
    affect the implementation of this task, but is worth noting.
    """

    def copy_test_data(name, root='', test_data='test_data', cat_filename='catalog.yml'):
        paths = _prepare_paths(root, name, test_data, cat_filename)

        # Not small test data found, nothing to copy.
        if not os.path.exists(paths['test']):
            return

        has_test_catalog = os.path.exists(paths['cat_test'])

        if has_test_catalog:
            print('* Copying intake catalog ...')

            # move real catalog file to tmp if tmp doesn't exist
            if os.path.exists(paths['cat_tmp']):
                raise ValueError(
                    "Fail: Temp file already exists - try "
                    f"'doit clean small_data_setup:{name}'"
                )
            os.rename(paths['cat_real'], paths['cat_tmp'])

            # move test catalog to project directory
            shutil.copyfile(paths['cat_test'], paths['cat_real'])
            print(f"  Intake catalog successfully copied from {paths['cat_test']} to {paths['cat_real']}")

        if (os.path.exists(paths['test'])
            and os.listdir(paths['test']) == ['catalog.yml']):
            # The only data was the catalog, that has already been processed.
            return

        print('* Copying test data ...')
        if os.path.exists(paths['real']):
            raise FileExistsError(
                f"Found unexpected {paths['real']}, run "
                f"'doit clean small_data_setup:{name}'"
            )

        ignore_catalog = shutil.ignore_patterns('catalog.yml')
        shutil.copytree(paths['test'], paths['real'], ignore=ignore_catalog)
        print(f"  Test data sucessfully copied from {paths['test']} to {paths['real']}")

    def remove_test_data(name, root='', test_data='test_data', cat_filename='catalog.yml'):
        paths = _prepare_paths(root, name, test_data, cat_filename)

        # No small test data found, no need to clean anything.
        if not os.path.exists(paths['test']):
            return

        if os.path.exists(paths['cat_real']):
            print("* Replacing intake catalog ...")

            if not os.path.exists(paths['cat_tmp']):
                print("Nothing to do: No temp file found. Use git status to "
                      f"check that you have the real catalog at {paths['cat_real']}")
            else:
                os.remove(paths['cat_real'])
                os.rename(paths['cat_tmp'], paths['cat_real'])
                print('  Intake catalog successfully cleaned')

        print('* Removing test data ...')

        if not os.path.exists(paths['real']):
            print('  No data to remove')
            return
        elif not os.listdir(paths['real']):
            os.rmdir(paths['real'])
            print(f"  No data found in {paths['real']}, just removed empty dir")
        else:
            shutil.rmtree(paths['real'])
            print(f"  Test data successfully removed from {paths['real']}")

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(copy_test_data, [name])],
            'clean': [(remove_test_data, [name])],
        }


def task_test_prepare_project():
    """
    Run `anaconda-project prepare --directory name --env-spec test`

    `anaconda-project prepare ...` doesn't download the data is already there.
    Instead it prints "Previously downloaded file located at {abs/to/data}"
    This is why it makes sense to setup the small test data before running
    `anaconda-project prepare/run`.

    # TODO: remove if not needed
    This doesn't run if `skip_test` is set to True.
    """

    def prepare_project_test(name):

        data_already_there = []
        data_path = pathlib.Path(name, 'data')
        if data_path.is_dir() and any(data_path.iterdir()):
            data_already_there = list(data_path.rglob('*'))
        with removing_files([pathlib.Path(name, '.projectignore')]):
            subprocess.run(
                ['anaconda-project', 'prepare', '--directory', name, '--env-spec', 'test'],
                check=True
            )
        if data_path.is_dir() and any(data_path.iterdir()):
            for p in data_path.rglob('*'):
                if p not in data_already_there and p.is_file():
                    p.unlink()
            remove_empty_dirs(data_path)

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(prepare_project_test, [name])],
            'uptodate': [(should_skip_test, [name])],
            'clean': [f'rm -rf {name}/envs'],
        }


def task_test_lint_project():
    """Run the lint command of a project
    
    Alternatively we could run nbqa installed globally instead of having
    to rely on a specific version of nbsmoke installed in each project. E.g.:

        nbqa flake8 network_packets/network_packets.ipynb
    """
    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [
                f'anaconda-project run --directory {name} lint',
            ],
            'uptodate': [(should_skip_test, [name])],
        }


def task_test_project():
    """Run the test command of a project
    
    Potential alternatives to run the tests with nbmake or nbval, from outside
    the environment. E.g.

        pytest --nbmake --nbmake-kernel=test-kernel network_packets/network_packets.ipynb
    """
    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [
                f'anaconda-project run --directory {name} test',
            ],
            'uptodate': [(should_skip_test, [name])]
        }


#### Build ####


def task_build_prepare_project():
    """
    Run `anaconda-project prepare --directory 

    This doesn't run if `skip_notebooks_evaluation` is set to True.
    """
    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [
                f'anaconda-project prepare --directory {name}',
            ],
            'uptodate': [(should_skip_notebooks_evaluation, [name])],
            # TODO
            'clean': [f'git clean -fxd {name}'],
        }


def task_build_process_notebooks():
    """
    Process notebooks.

    If the project has not set `skip_notebooks_evaluation` to True then
    run notebooks and save their evaluated version in doc/{projname}/.
    This is expected to be executed from an environment outside of the 
    target environment.
    Otherwise simply copy the notebooks to doc/{projname}/.
    """

    def run_notebook(src_path, dst_path, kernel_name, dir_name):
        """
        Run a notebook using nbclient.
        """
        import nbformat
        from nbclient import NotebookClient

        print(f'Reading notebook {src_path}')
        nb = nbformat.read(src_path, as_version=4)
        client = NotebookClient(
            nb,
            timeout=NOTEBOOK_EVALUATION_TIMEOUT,
            kernel_name=kernel_name,
            resources={'metadata': {'path': f'{dir_name}/'}},
        )
        print(f'Executing notebook {src_path} with kernel {kernel_name} in dir {dir_name}')
        client.execute()
        print(f'Saving notebook at {dst_path}')
        # nbsite takes care of copying json files generated by HoloViews/Panel.
        # TODO: make sure this is doing the same thing.
        nbformat.write(nb, dst_path)

    def run_notebooks(name):
        """
        Run notebooks found in the project folder with the {name}-kernel
        IPykernel and save them in the doc/{name} folder.
        """
        notebooks = find_notebooks(name)
        for notebook in notebooks:
            out_dir = pathlib.Path('doc') / name
            if not out_dir.exists():
                out_dir.mkdir()
            run_notebook(
                src_path=notebook,
                dst_path=out_dir / notebook.name,
                kernel_name=f'{name}-kernel',
                dir_name=name,
            )
    
    def copy_notebooks(name):
        """
        Copy notebooks from the project folder to the doc/{name} folder.
        """
        # TODO: should it also copy .json files?
        notebooks = find_notebooks(name)
        for notebook in notebooks:
            out_dir = pathlib.Path('doc') / name
            if not out_dir.exists():
                out_dir.mkdir()
            dst = out_dir / notebook.name
            print(f'Copying notebook {notebook} to {dst}')
            shutil.copyfile(notebook, dst)

    for name in all_project_names(root=''):
        skip_notebooks_evaluation = should_skip_notebooks_evaluation(name)
        if not skip_notebooks_evaluation:
            actions = [
                f'echo "install kernel {name}-kernel"',
                # Setup Kernel
                f'conda run --prefix {name}/envs/default python -m ipykernel install --user --name={name}-kernel',
                # Run notebooks with that kernel
                (run_notebooks, [name]),
            ]
            teardown = [
                f'echo "remove kernel {name}-kernel"',
                # Remove Kernel
                f'conda run --prefix {name}/envs/default jupyter kernelspec remove {name}-kernel -f',
            ]
        else:
            actions = [
                f'echo "Skipping running notebooks of {name}"',
                (copy_notebooks, [name]),
            ]
            teardown = []
        yield {
            'name': name,
            'actions': actions,
            'teardown': teardown,
            # TODO
            'clean': [f'git clean -fxd doc/{name}'],
        }


#### Doc ####


def task_doc_archive_projects():
    """Archive projects to assets/_archives"""

    def archive_project(root='', name='all'):
        projects = all_project_names(root) if name == 'all'  else [name]
        for project in projects:
            _archive_project(project)

    def _archive_project(project):
        from yaml import safe_dump


        has_project_ignore = False
        projectignore_path = pathlib.Path(project, '.projectignore')
        if projectignore_path.exists():
            has_project_ignore = True

        has_readme = False
        readme_path = pathlib.Path(project, 'README.md')
        if readme_path.exists():
            has_readme = True

        print(f'Archiving {project}...')
        if not os.path.exists(readme_path):
            shutil.copyfile('README.md', readme_path)

        # stripping extra fields out of anaconda_project to make them more legible
        path = os.path.join(project, 'anaconda-project.yml')
        tmp_path = f'{project}_anaconda-project.yml'
        shutil.copyfile(path, tmp_path)
        spec = project_spec(project)

        # special field that anaconda-project doesn't know about
        spec.pop('examples_config', '')
        spec.pop('user_fields', '')

        # commands and envs that users don't need
        spec['commands'].pop('test', '')
        spec['commands'].pop('lint', '')
        spec['env_specs'].pop('test', '')

        # get rid of any empty fields
        spec = {k: v for k, v in spec.items() if bool(v)}

        with open(path, 'w') as f:
            safe_dump(spec, f, default_flow_style=False, sort_keys=False)

        archives_path = os.path.join('assets', '_archives')
        if not os.path.exists(archives_path):
            os.makedirs(archives_path)

        subprocess.run(
            ["anaconda-project", "archive", "--directory", f"{project}", f"assets/_archives/{project}.zip"],
            check=True
        )
        shutil.copyfile(tmp_path, path)
        os.remove(tmp_path)

        if not has_project_ignore:
            print(f'Removing temp {projectignore_path}')
            projectignore_path.unlink()
        if not has_readme:
            print(f'Removing temp {readme_path}')
            readme_path.unlink()

    def clean_archive():
        projects = all_project_names(root='')
        for project in projects:
            _clean_archive(project)
        assets_path = pathlib.Path('assets')
        remove_empty_dirs(assets_path)

    def _clean_archive(project):
        _archives_path = pathlib.Path('assets', '_archives')
        if not _archives_path.exists():
            return
        archive_path = _archives_path / f'{project}.zip'
        print(f'Removing {archive_path}')
        archive_path.unlink(archive_path)

    return {
        'actions': [archive_project],
        'params': [name_param],
        'clean': [clean_archive]
    }


def task_doc_move_thumbnails():
    """Move thumbnails from the project dir to the project doc dir"""

    def move_thumbnails(root='', name='all'):
        projects = all_project_names(root) if name == 'all'  else [name]
        for project in projects:
            _move_thumbnails(project)

    def _move_thumbnails(name):
        src_dir = os.path.join(name, 'thumbnails')
        dst_dir = os.path.join('doc', name, 'thumbnails')
        if os.path.exists(src_dir):
            if not os.path.exists(dst_dir):
                print(f'Creating directories {dst_dir}')
                os.makedirs(dst_dir)
            for item in os.listdir(src_dir):
                src = os.path.join(src_dir, item)
                dst = os.path.join(dst_dir, item)
                print(f'Copying thumbnail {src} to {dst}')
                shutil.copyfile(src, dst)
    
    def clean_thumbnails():
        projects = all_project_names(root='')
        for project in projects:
            path = pathlib.Path('doc') / project / 'thumbnails'
            if path.is_dir():
                print(f'Removing thumbnails folder {path}')
                shutil.rmtree(path)
        remove_empty_dirs('doc')

    return {
        'actions': [move_thumbnails],
        'params': [name_param],
        'clean': [clean_thumbnails],
    }


def task_doc_move_assets():
    """Copy the projects assets to assets/projname/assets/
    
    This includes:
    - the project archive (output of anaconda-project archive)
      that is in the ./doc/projname/ folder
    - all the files found in the ./projename/assets/ folder, if it exists.

    TODO
    nbsite corrects the links to the assets in nbsite_fix_links.py
    it should not have to do that, instead the assets should be pushed to the
    docs folder
    """

    def move_assets(root='', name='all'):
        if not os.path.exists('assets'):
            print('Creating assets/ dir')
            os.mkdir('assets')
        projects = all_project_names(root) if name == 'all'  else [name]
        for project in projects:
            _move_assets(project)

    def _move_assets(name):
        # Copy all the files in ./projname/assets to ./assets/projname/assets/
        proj_assets_path = pathlib.Path(name, 'assets')
        if proj_assets_path.exists():
            dest_assets_path = pathlib.Path('assets', name, 'assets')
            if not dest_assets_path.exists():
                print(f'Creating dirs {dest_assets_path}')
                os.makedirs(dest_assets_path)
            print(f'Copying tree {proj_assets_path} to {dest_assets_path}')
            shutil.copytree(proj_assets_path, dest_assets_path, dirs_exist_ok=True)

    def clean_assets():
        projects = all_project_names(root='')
        for project in projects:
            _clean_assets(project)
        assets_dir = pathlib.Path('assets')
        remove_empty_dirs(assets_dir)
        if assets_dir.exists() and not any(assets_dir.iterdir()):
            print(f'Removing empty dir {assets_dir}')
            assets_dir.rmdir()

    def _clean_assets(name):
        assets_dir = pathlib.Path('assets')
        if not assets_dir.exists():
            return
        _archives_dir = pathlib.Path('assets', '_archives')
        if _archives_dir.exists():
            archive_path = _archives_dir / f'{name}.zip'
            if archive_path.exists():
                print(f'Removing {archive_path}')
                archive_path.unlink()
        proj_dir = assets_dir / name
        if not proj_dir.exists():
            return
        project_assets_dir = assets_dir / name / 'assets'
        if not project_assets_dir.exists():
            return
        for asset in project_assets_dir.iterdir():
            if asset.is_file():
                print(f'Removing asset {asset}')
                asset.unlink()
            elif asset.is_dir():
                print(f'Removing empty dir {asset}')
                shutil.rmtree(asset)

    return {
        'actions': [move_assets],
        'params': [name_param],
        'clean': [clean_assets],
    }


def task_doc_get_evaluated():
    """Fetch the evaluated branch and checkout the /doc folder"""

    def clean_doc():
        doc_dir = pathlib.Path('doc')
        for subdir in doc_dir.iterdir():
            if not subdir.is_dir():
                continue
            if subdir.name in DEFAULT_DOC_EXCLUDE:
                continue
            print(f'Removing tree {subdir}')
            shutil.rmtree(subdir)

    return {
        'actions': [
            # Fetch the evaluated branch containing the evaluated projects
            'git fetch https://github.com/%(githubrepo)s.git evaluated:refs/remotes/evaluated',
            # Checkout the doc/ folder from that branch into the current branch
            'git checkout evaluated -- ./doc/%(name)s',
            # The previous command stages all what is in doc/, unstage that.
            # This is better UX when building the site locally, not needed on the CI.
            'git reset doc/',
        ],
        'clean': [clean_doc],
        'params': [githubrepo_param, name_param]
}


def task_doc_remove_not_evaluated():
    """TEMP! task that should be removed when all the projects are on evaluated

    TODO: remove it when no longer required.
    """

    def remove():
        projects = all_project_names(root='')
        doc_path = pathlib.Path('doc')
        for project in projects:
            proj_path = doc_path / project
            if not proj_path.exists():
                continue
            if not any(f.suffix == '.ipynb' for f in proj_path.iterdir()):
                print(f'Removing {proj_path} as no evaluated notebook found in it')
                shutil.rmtree(proj_path)

    return {'actions': [remove]}


def task_doc_build_website():
    """Build website with nbsite.
    
    It assumes you are in an environment with required dependencies and
    the projects have been built.
    """

    return {
        'actions': [
            "nbsite build --examples .",
        ],
        'clean': [
            'rm -rf builtdocs/',
            'rm -rf jupyter_execute/',
            'rm -f doc/*/*.rst',
            'rm -f doc/index.rst',
        ]
    }


def task_doc_index_redirects():
    """
    Create redirect pages to provide short, convenient project URLS.

    E.g. examples.pyviz.org/projname
    
    A previous approach was using symlinks and this should behave the same 
    but can be used where symlinks are not suitable.
    https://github.com/pyviz-topics/examples/blob/17a17be1a1b159095be55801202741e049a780e8/dodo.py#L281-L298
    """

    REDIRECT_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>{name} redirect</title>
        <meta http-equiv = "refresh" content = "0; url = https://examples.pyviz.org/{name}/{name}.html" />
    </head>
    </html>
    """

    def write_redirect(name):
        with open('./index.html', 'w') as f:
            contents = textwrap.dedent(REDIRECT_TEMPLATE.format(name=name))
            f.write(contents)
            print('Created relative HTML redirect for %s' % name)

    # TODO: known to generate some broken redirects.
    def generate_index_redirect():
        cwd = os.getcwd()
        for name in all_project_names(''):
            project_path = os.path.abspath(os.path.join('.', 'builtdocs', name))
            try:
                os.chdir(project_path)
                listing = os.listdir(project_path)
                if 'index.html' not in listing:
                    write_redirect(name)
                os.chdir(cwd)
            except Exception as e:
                complain(str(e))
        os.chdir(cwd)

    def clean_index_redirects():
        for name in all_project_names(''):
            project_path = pathlib.Path('builtdocs') / name
            index_path = project_path / 'index.html'
            if index_path.is_file():
                print(f'Removing index redirect {index_path}')
                index_path.unlink()

    return {
        'actions': [generate_index_redirect],
        'clean': [clean_index_redirects]
    }


#### Grouped tasks ####

# These tasks are not meant to be used on the CI (except for cleaning),
# where it's better to call each task individually as it's then easier to
# identify which one failed and why.
# They are more meant to be used by people building and maintaining projects,
# as a quick way to run multiple tasks at once.

def task_validate():
    """
    Validate a project (doit validate:projname)

    This includes:
    - the existence and content of the anaconda-project.yml file
    - the existence of a lock file and that is not stale
    - if there is an intake catalog, that it is named correctly
    - the definition of the project's data sources
    - the existence of small test data, if relevant
    - the notebook names
    - the notebooks have a header
    - the thumbnails existence and dimensions
    """
    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': None,
            'task_dep': [
                f'validate_project_file:{name}',
                f'validate_project_lock:{name}',
                f'validate_intake_catalog:{name}',
                f'validate_data_sources:{name}',
                f'validate_small_test_data:{name}',
                f'validate_index_notebook:{name}',
                f'validate_notebook_header:{name}',
                f'validate_thumbnails:{name}',
            ]
        }

def task_test():
    """
    Test a project (doit test:projname)

    This includes:
    - setting up the small data
    - preparing the project
    - running the project lint command
    - running the project test command


    Run the following command to clean the outputs:
        doit clean --clean-dep test:projname
    """
    for name in all_project_names(root=''):
        yield {
            'name': name,
        'actions': None,
            'task_dep': [
                f'test_small_data_setup:{name}',
                f'test_prepare_project:{name}',
                f'test_lint_project:{name}',
                f'test_project:{name}',
            ]
        }


def task_build():
    """
    Build a project (doit build:projname)
    
    Run the following command to clean the outputs:
        doit clean --clean-dep build:projname
    """
    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': None,
            'task_dep': [
                f'build_prepare_project:{name}',
                f'build_process_notebooks:{name}',
            ]
        }

def task_doc():
    """
    Build the doc (doit doc)

    Run the following command to clean the outputs:
        doit clean --clean-dep doc
    """
    return {
        'actions': None,
        'task_dep': [
            'doc_archive_projects',
            'doc_move_thumbnails',
            'doc_move_assets',
            'doc_get_evaluated',
            'doc_remove_not_evaluated',
            'doc_build_website',
            'doc_index_redirects',
        ]
    }
