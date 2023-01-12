import datetime
import glob
import os
import pathlib
import shutil
import subprocess

DOIT_CONFIG = {
    "verbosity": 2,
    "backend": "sqlite3",
}

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

name_param = {
    'name': 'name',
    'long': 'name',
    'type': str,
    'default': 'all'
}

githubrepo_param = {
    'name': 'githubrepo',
    'type': str,
    'default': 'pyviz-topics/examples'
}

sha_param = {
    'name': 'sha',
    'long': 'sha',
    'type': str,
    'default': ''
}

env_spec_param = {
    'name': 'env_spec',
    'long': 'env-spec',
    'type': str,
    'default': 'default'
}

warning_as_error_param = {
    'name': 'warning_as_error',
    'short': 'W',
    'long': 'warning-as-error',
    'type': bool,
    'default': False,
}

def _prepare_paths(root, name, test_data, filename='catalog.yml'):
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


def complain(msg, warning_as_error):
    if warning_as_error:
        raise RuntimeError(msg)
    else:
        print('WARNING: ' + msg)

def project_spec(projname, filename='anaconda-project.yml'):
    # Prepared for when skip_test is added
    from yaml import safe_load

    path = pathlib.Path(projname) / filename
    with open(path, 'r') as f:
        spec = safe_load(f)
    return spec

def all_project_names(root):
    if root == '':
        root = os.getcwd()
    root = os.path.abspath(root)
    return sorted([f for f in next(os.walk('.'))[1] if f not in DEFAULT_EXCLUDE])

def task_list_project_dir_names():
    """Print a list of all the project directory names"""

    def list_project_dir_names():
        print(all_project_names(root=''))

    return {
        'actions': [list_project_dir_names],
    }

def task_list_comma_separated_projects():
    """Print a list of all the projects found in .projects
    
    They are expected to be comma separated
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

def task_small_data_setup():
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
                raise FileNotFoundError("Nothing to do: No temp file found. Use git status to "
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

def task_archive_project():
    """Archive project with given name, assumes anaconda-project is in env"""

    def archive_project(project):
        from yaml import safe_dump

        print(f'Archving {project}...')
        readme_path = os.path.join(project, 'README.md')
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

        doc_path = os.path.join('doc', project)
        if not os.path.exists(doc_path):
            os.mkdir(doc_path)

        subprocess.run(["anaconda-project", "archive", "--directory", f"{project}", f"doc/{project}/{project}.zip"])
        shutil.copyfile(tmp_path, path)
        os.remove(tmp_path)

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(archive_project, [name])],
            # TODO
            'clean': [f'git clean -fxd doc/{name}'],
        }

def task_move_thumbnails():
    """Move the thumbnails from the project dir to the doc dir"""

    def move_thumbnails(name):
        src_dir = os.path.join(name, 'thumbnails')
        dst_dir = os.path.join('doc', name, 'thumbnails')
        if os.path.exists(src_dir):
            if not os.path.exists(dst_dir):
                os.makedirs(dst_dir)
            for item in os.listdir(src_dir):
                src = os.path.join(src_dir, item)
                dst = os.path.join(dst_dir, item)
                shutil.copyfile(src, dst)

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(move_thumbnails, [name])],
            # TODO
            'clean': [f'git clean -fxd doc/{name}']
        }

def task_get_evaluated_doc():
    """Fetch the evaluated branch and checkout the /doc folder."""

    def clean_doc():
        doc_dir = pathlib.Path('doc')
        for subdir in doc_dir.glob('*/'):
            if not subdir.is_dir():
                continue
            if subdir.name in DEFAULT_DOC_EXCLUDE:
                continue
            shutil.rmtree(subdir)

    return {
        'actions': [
            # Fetch the evaluated branch containing the evaluated projects
            'git fetch https://github.com/%(githubrepo)s.git evaluated:refs/remotes/evaluated',
            # Checkout the doc/ folder from that branch into the current branch
            'git checkout evaluated -- ./doc',
            # The previous command stages all what is in doc/, unstage that.
            # This is better UX when building the site locally, not needed on the CI.
            'git reset doc/',
        ],
        'clean': [clean_doc],
        'params': [githubrepo_param]
}

def task_make_assets():
    """Copy the projects assets to assets/
    
    This includes:
    - the project archive (output of anaconda-project archive)
      that is in the ./doc/projname/ folder
    - all the files found in the ./projename/assets/ folder, if it exists.
    """

    def make_assets(name):
        if not os.path.exists('assets'):
            os.mkdir('assets')
        # Copy the project archive to the assets
        archived_project = os.path.join('doc', name, f'{name}.zip')
        if os.path.exists(archived_project):
            dst = os.path.join('assets',  f'{name}.zip')
            shutil.copyfile(archived_project, dst)
        # Copy all the files in ./projname/assets to ./assets
        assets_dir = os.path.join(name, 'assets')
        if os.path.exists(assets_dir):
            for item in os.listdir(assets_dir):
                src = os.path.join(assets_dir, item)
                dst = os.path.join('assets', item)
                # There could be a name clash between the assets
                # TODO: Better handle this, assets should have their namespace
                # preserved.
                if os.path.exists(dst):
                    complain(
                        f'Asset {item} already in the root `assets` folder'
                        ' (from another project), please rename your asset.',
                        warning_as_error=False
                    )
                shutil.copyfile(src, dst)

    def clean_assets(name):
        assets_dir = pathlib.Path('assets')
        if not assets_dir.exists():
            return
        proj_dir = pathlib.Path(name)
        archived_project = assets_dir / f'{name}.zip'
        if archived_project.exists():
            archived_project.unlink()
        proj_assets_dir = proj_dir / 'assets'
        if proj_assets_dir.is_dir():
            asset_names = [path.name for path in proj_assets_dir.iterdir()]
            for asset in assets_dir.iterdir():
                if asset.name in asset_names:
                    if asset.is_file():
                        asset.unlink()
                    elif asset.is_dir():
                        shutil.rmtree(asset)
        if not any(assets_dir.iterdir()):
            assets_dir.rmdir()

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(make_assets, [name])],
            'clean': [(clean_assets, [name])],
        }

def task_build_website():
    """Build website, assumes you are in an environment with required dependencies and have build projects"""

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

def task_index_symlinks():
    "Create relative symlinks to provide short, convenient project URLS"

    def generate_index_symlinks():
        cwd = os.getcwd()
        for name in all_project_names(''):
            project_path = os.path.abspath(os.path.join('.', 'builtdocs', name))
            try:
                os.chdir(project_path)
                listing = os.listdir(project_path)
                if 'index.html' not in listing:
                    os.symlink('./%s.html' % name, './index.html')
                    print('Created symlink for %s' % name)
                os.chdir(cwd)
            except Exception as e:
                print(str(e))
        os.chdir(cwd)
    return {'actions':[generate_index_symlinks]}


REDIRECT_TEMPLATE = """
<!DOCTYPE html>
<html>
   <head>
      <title>{name} redirect</title>
      <meta http-equiv = "refresh" content = "0; url = https://examples.pyviz.org/{name}/{name}.html" />
   </head>
</html>
"""


def task_index_redirects():
    """
    Create redirect pages to provide short, convenient project URLS.
    Should behave the same as task_index_symlinks but can be used where
    symlinks are not suitable.

    """
    def write_redirect(name):
        with open('./index.html', 'w') as f:
            contents = REDIRECT_TEMPLATE.format(name=name)
            f.write(contents)
            print('Created relative HTML redirect for %s' % name)

    def generate_index_redirect(warning_as_error):
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
                complain(str(e), warning_as_error)
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
        'params': [warning_as_error_param],
        'clean': [clean_index_redirects]
    }

def print_changes_in_dir(filepath='.diff'):
    """Print a list of the projects referenced in the file.
    
    An empty list is printed if no projects were referenced.
    """
    paths = pathlib.Path(filepath).read_text().splitlines()
    paths = [pathlib.Path(p) for p in paths]
    all_projects = all_project_names(root='')
    changed_dirs = []
    for path in paths:
        root = path.parts[0]
        if not pathlib.Path(root).is_dir() or root not in all_projects:
            continue
        changed_dirs.append(root)
    changed_dirs = sorted(set(changed_dirs))
    print(changed_dirs)

def task_list_changed_dirs_with_main():
    """
    Print the list of projects that have changes compared to main.
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

def task_list_changed_dirs_with_last_commit():
    """
    Print the list of projects that have changes compared to the last commit..
    """ 
    return {
        'actions': [
            'git diff HEAD^ HEAD --name-only > .diff',
            print_changes_in_dir,
        ],
        'teardown': ['rm -f .diff']
    }

# INFO:
# anaconda-project prepare ... doesn't download the data, instaed it prints "Previously downloaded file located at {abs/to/data}"
# This is why it makes sense to setup the small test data before running `anaconda-project prepare/run`.

# Potential alternatives to run the tests with nbqa and nbmake (or nbval when 0.9.7/0.10.0 gets released)
# nbqa flake8 network_packets/network_packets.ipynb
# pytest --nbmake --nbmake-kernel=test-kernel network_packets/network_packets.ipynb


def should_skip_test(name):
    skip_test = False
    if skip_test:
        print('skip_test: True')
    return False

    # Prepared for when skip_test is added
    spec = project_spec(name)
    skip_test = spec['examples_config'].get('skip_test', False)
    return skip_test

def task_prepare_project_test():
    """
    Run `anaconda-project prepare --directory name`,

    This doesn't run if `skip_notebooks_evaluation` is set to True.
    """
    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [
                f'anaconda-project prepare --directory {name} --env-spec test',
            ],
            'uptodate': [(should_skip_test, [name])],
            # TODO
            'clean': [f'git clean -fxd {name}'],
        }

def task_lint_project():
    """Run the lint command of a project"""
    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [
                f'anaconda-project run --directory {name} lint',
            ],
            'uptodate': [(should_skip_test, [name])],
        }

def task_test_project():
    """Run the test command of a project"""
    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [
                f'anaconda-project run --directory {name} test',
            ],
            'uptodate': [(should_skip_test, [name])]
        }

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
    if skip_notebooks_evaluation:
        print('skip_notebooks_evaluation: True')
    return skip_notebooks_evaluation

def task_prepare_project():
    """
    Run `anaconda-project prepare --directory name`,

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

def task_process_notebooks():
    """
    Process notebooks.

    If the project has not set `skip_notebooks_evaluation` to True then
    run notebooks and save their evaluated version in doc/{name}.
    This is expected to be executed from an environment outside of the 
    target environment (i.e. the one running the notebooks).

    Otherwise simply copy the notebooks to doc/{name}.
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
                # Setup Kernel
                f'conda run --prefix {name}/envs/default python -m ipykernel install --user --name={name}-kernel',
                # Run notebooks with that kernel
                (run_notebooks, [name]),
            ]
            teardown = [
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

def task_validate_project_file():
    """Validate the existence and content of the anaconda-project.yml file"""

    def validate_project_file(name, warning_as_error):
        from yaml import safe_load, YAMLError

        project = pathlib.Path(name) / 'anaconda-project.yml'
        if not project.exists():
            raise FileNotFoundError('Missing anaconda-project.yml file')

        with open(project, 'r') as f:
            try:
                spec = safe_load(f)
            except YAMLError:
                raise YAMLError('invalid file content')

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
                raise ValueError(f"Missing {entry!r} entry")
        commands = spec.get('commands', {})
        if not all(expected_command in commands for expected_command in ['test', 'lint']):
            raise ValueError('missing lint or test command')
        env_specs = spec.get('env_specs', {})
        if not all(expected_es in env_specs for expected_es in ['default', 'test']):
            raise ValueError('missing default or test env_spec')
        user_fields = spec['user_fields']
        if user_fields != ['examples_config']:
            raise ValueError('"user_fields" must be [examples_config]')

        config = spec.get('examples_config', [])
        expected = ['maintainers', 'labels']
        for entry in expected:
            if entry not in config:
                raise ValueError(f'missing {entry!r} list')
            value = config[entry]
            if not isinstance(value, list):
                raise ValueError(f'{entry!r} must be a list')
            if not all(isinstance(item, str) for item in value):
                raise ValueError(f'all values of {value!r} must be a string')
            if entry == 'labels':
                labels_path = pathlib.Path('doc') / '_static' / 'labels'
                labels = list(labels_path.glob('*.svg'))
                for label in value:
                    if not any(label_file.stem == label for label_file in labels):
                        raise FileNotFoundError(f'missing {label}.svg file in doc/_static/labels')

        created = config.get('created')
        if created:
            if not isinstance(created, datetime.date):
                raise ValueError('"created" must be a date expressed as YYYY-MM-DD')
        else:
            complain(
                '"created" not found',
                warning_as_error,
            )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_project_file, [name])],
            'params': [warning_as_error_param],
        }

def task_validate_project_lock():
    """Validate the existence of the anaconda-project-lock.yml file"""

    def validate_project_lock(name, warning_as_error):
        from anaconda_project.project import Project

        if name == 'carbon_flux':
            return

        project = Project(directory_path=name)
        lock_path = pathlib.Path(project.lock_file.filename)
        if not lock_path.exists():
            complain(
                f'Missing {lock_path} file',
                warning_as_error,
            )

        # Copied from https://github.com/Anaconda-Platform/anaconda-project/blob/a82a02083e9a19e9cfb33ca193737ed47fd7c914/anaconda_project/project.py#L758-L763
        for env_spec_name, env_spec in project.env_specs.items():
            locked_hash = env_spec.lock_set.env_spec_hash
            if locked_hash is not None and locked_hash != env_spec.logical_hash:
                complain(
                    f"Env spec '{env_spec_name}' has changed since the lock file was last updated.",
                    warning_as_error,
                )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_project_lock, [name])],
            'params': [warning_as_error_param],
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
                    raise ValueError(
                        f'Intake catalog must be saved at "{expected_path}", '
                        f'not at "{path}".'
                    )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_intake_catalog, [name])],
        }

def project_has_downloads(name):
    """Whether a project has a non-empty `downloads` section."""
    spec = project_spec(name)
    downloads = spec.get('downloads', {})
    return bool(downloads)

def project_has_intake_catalog(name):
    """Whether a project has an Intake catalog"""
    path = pathlib.Path(name) / 'catalog.yml'
    return path.is_file()

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

def task_validate_data_sources():
    """Validate the data sources of a project

    For a project to have valid data sources it must have either:
    - a `downloads` section in its anaconda-project.yml file
    - an intake catalog
    - a `data/` subfolder containing files
    - the `no_data_ingestion` flag set to true in its `examples_config` spec
    """

    def validate_data_sources(name, warning_as_error):
        has_downloads = project_has_downloads(name)

        if has_downloads:
            spec = project_spec(name)
            for var, dspec in spec['downloads'].items():
                dfilename = dspec.get('filename', '')
                if not dfilename:
                    raise KeyError(
                        f'`downloads` entry {var!r} must define `filename`'
                    )
                if not dfilename.startswith('data'):
                    raise ValueError(
                        f'`downloads` entry {var!r} must define `filename` '
                        'starting with "data"'
                    )

        has_intake_catalog = project_has_intake_catalog(name)
        has_data_folder = project_has_data_folder(name)
        has_no_data_ingestion = project_has_no_data_ingestion(name)

        if has_downloads and has_intake_catalog:
            raise ValueError(
                'Relying on `downloads` in anaconda-project.yml and '
                'on an Intake catalog is not supported (may need updates '
                'in task_small_data_setup)'
            )

        # This used to be partially supported but was actually
        # not used by projects so was removed. The old code
        # can be found here:
        # https://github.com/pyviz-topics/examples/blob/d85de1c78f1351047c003cddd0d4b02603f08f2a/dodo.py#L49-L183
        if has_data_folder and (has_downloads or has_intake_catalog):
            raise ValueError(
                'Relying on `downloads` in anaconda-project.yml OR '
                'on an Intake catalog, together with the presence of '
                'a `data/` folder is not supported (need updates in '
                'task_small_data_setup'
            )

        has_explicit_source = has_downloads or has_intake_catalog or has_data_folder
        if has_explicit_source and has_no_data_ingestion:
            raise ValueError(
                'The project set `no_data_ingestion` to True but has either '
                'a `downloads` section, an intake catalog or a `data` folder.'
            )
        if not has_explicit_source and not has_no_data_ingestion:
            complain(
                'The project does not define its data sources.',
                warning_as_error,
            )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_data_sources, [name])],
            'params': [warning_as_error_param],
        }

def project_has_test_data(name):
    """Whether a project has a test data"""
    path = pathlib.Path('test_data') / name
    if not path.is_dir():
        return False
    has_files = not any(path.iterdir())
    return has_files

def project_has_test_catalog(name):
    """Whether a project has a test catalog"""
    path = pathlib.Path('test_data') / name / 'catalog.yml'
    return path.exists()

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

    def validate_small_test_data(name, warning_as_error):
        has_downloads = project_has_downloads(name)
        has_intake_catalog = project_has_intake_catalog(name)
        has_test_data = project_has_test_data(name)
        has_test_catalog = project_has_test_catalog(name)
        
        if has_downloads and not has_test_data:
            msg = (
                'Project defined `downloads` but did not provide test data in '
                f'test_data/{name}/'
            )
            complain(msg, warning_as_error)
        if has_intake_catalog and not has_test_catalog:
            msg = (
                'Project has an Intake catalog but did not provide a test '
                f'catalog at test_data/{name}/catalog.yml '
            )
            complain(msg, warning_as_error)


    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_small_test_data, [name])],
            'params': [warning_as_error_param],
        }

def task_validate_index_notebook():
    """
    Validate that a project with multiple displayed notebooks has an index.ipynb notebook.
    """

    def validate_index(name, warning_as_error):
        # Notebooks in skip don't need a thumbnail.
        notebooks = find_notebooks(name, exclude_config=['skip'])
        # Not index.ipynb file, the project isn't displayed so just complain
        if len(notebooks) > 1:
            if not any(nb.stem == 'index' for nb in notebooks):
                complain(
                    f'{name}: has multiple files but no index.ipynb',
                    warning_as_error,
                )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_index, [name])],
            'params': [warning_as_error_param],
        }

def task_validate_thumbnails():
    """Validated that the project has a thumbnail."""

    def validate_thumbnails(name, warning_as_error):
        thumb_folder = pathlib.Path(name) / 'thumbnails'
        if not thumb_folder.exists():
            complain(
                f"{name}: has no 'thumbnails/' folder",
                warning_as_error,
            )
            return
        # Notebooks in skip  don't need a thumbnail.
        notebooks = find_notebooks(name, exclude_config=['skip'])
        # Not index.ipynb file, the project isn't displayed so just complain
        if len(notebooks) > 1:
            if not any(nb.stem == 'index' for nb in notebooks):
                complain(
                    f'{name}: has multiple files but no index.ipynb, thumbnails validation skipped',
                    warning_as_error,
                )
                return
            else:
                notebooks = [nb for nb in notebooks if nb.stem == 'index']

        notebook = notebooks[0]
        if not any(
            thumb.stem == notebook.stem
            for thumb in thumb_folder.glob('*.png')
        ):
            complain(
                f'{name}: has no PNG thumbnail for notebook {notebook.name}',
                warning_as_error
            )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_thumbnails, [name])],
            'params': [warning_as_error_param],
        }

### Grouped tasks

def task_validate():
    """
    Validate a project, including:
    - the existence and content of the anaconda-project.yml file
    - the existence of a lock file and its state
    - if there is an intake catalog, that it is named correctly
    - the definition of the project's data sources
    - the existence of small test data, if relevant
    - index notebook for project with multiple notebooks
    - thumbnails
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
                f'validate_thumbnails:{name}',
            ]
        }

def task_test():
    """
    Test a project, including:
    - setting up the small data
    - preparing the project
    - running the project lint command
    - running the project test command
    """
    for name in all_project_names(root=''):
        yield {
            'name': name,
        'actions': None,
            'task_dep': [
                f'small_data_setup:{name}',
                f'prepare_project_test:{name}',
                f'lint_project:{name}',
                f'test_project:{name}',
            ]
        }

def task_validate_and_test():
    """Validate and test a project."""
    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': None,
            'task_dep': [
                f'validate:{name}',
                f'test:{name}',
            ]
        }

def task_build():
    """
    Build a project in one command.

        doit build:boids
    
    Run the following command to clean the outputs:

        doit clean --clean-dep build:boids
    """
    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': None,
            'task_dep': [
                f'archive_project:{name}',
                f'move_thumbnails:{name}',
                f'prepare_project:{name}',
                f'process_notebooks:{name}',
            ]
        }

def task_website():
    """
    Run subtasks to build the site entirely.

        doit website
    
    Run the following command to clean the outputs:

        doit clean --clean-dep website
    """
    return {
        'actions': None,
        'task_dep': [
            'get_evaluated_doc',
            'make_assets',
            'build_website',
            'index_redirects',
        ]
    }
