import datetime
import filecmp
import glob
import os
import pathlib
import shutil

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
        'project': project_path,
        'real': os.path.join(project_path, 'data'),
        'test': test_path,
        'cat_real': os.path.join(project_path, filename),
        'cat_test': os.path.join(test_path, filename),
        'cat_tmp': os.path.join(project_path, 'tmp_' + filename),
    }

def find_notebooks(proj_dir_name, exclude_config=['skip']):
    """
    Find the notebooks in a project.
    """
    from yaml import safe_load

    proj_dir = pathlib.Path(proj_dir_name)

    path = proj_dir / 'anaconda-project.yml'
    with open(path, 'r') as f:
        spec = safe_load(f)

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

# From https://stackoverflow.com/a/24860799/4021797
class dircmp(filecmp.dircmp):
    """
    Compare the content of dir1 and dir2. In contrast with filecmp.dircmp, this
    subclass compares the content of files with the same path.
    """
    def phase3(self):
        """
        Find out differences between common files.
        Ensure we are using content comparison with shallow=False.
        """
        fcomp = filecmp.cmpfiles(self.left, self.right, self.common_files,
                                 shallow=False)
        self.same_files, self.diff_files, self.funny_files = fcomp

def is_same(dir1, dir2):
    """
    Compare two directory trees content.
    Return False if they differ, True is they are the same.
    """
    compared = dircmp(dir1, dir2)
    if (compared.left_only or compared.right_only or compared.diff_files
        or compared.funny_files):
        return False
    for subdir in compared.common_dirs:
        if not is_same(os.path.join(dir1, subdir), os.path.join(dir2, subdir)):
            return False
    return True

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

def task_check_project_exists():
    """Print 1 if the project exist, else 0"""

    def check_project_exists(name):
        projects = all_project_names(root='')
        if name in projects:
            print('1')
        else:
            print('0')

    return {
        'actions': [check_project_exists],
        'params': [name_param],
    }

def task_small_data_setup():
    """Copy small versions of the data from test_data"""

    def copy_test_data(name, root='', test_data='test_data', cat_filename='catalog.yml'):
        paths = _prepare_paths(root, name, test_data, cat_filename)
        has_catalog = os.path.exists(paths['cat_real'])

        if not os.path.exists(paths['test']) or not os.listdir(paths['test']):
            if has_catalog:
                raise ValueError(f"Fail: {name} has no test_data")
            else:
                print(f"  Nothing to do: Test data not found for {name}")
                return

        if has_catalog and not os.path.exists(paths['cat_test']):
            raise ValueError(f"Fail: {name} contains intake catalog, but "
                             "no catalog found in test_data")

        if has_catalog:
            print('* Copying intake catalog ...')

            # move real catalog file to tmp if tmp doesn't exist
            if os.path.exists(paths['cat_tmp']):
                raise ValueError("Fail: Temp file already exists - try 'doit small_data_cleanup'")
            os.rename(paths['cat_real'], paths['cat_tmp'])

            # move test catalog to project directory
            shutil.copyfile(paths['cat_test'], paths['cat_real'])
            print(f"  Intake catalog successfully copied from {paths['cat_test']} to {paths['cat_real']}")

        print('* Copying test data ...')
        if os.path.exists(paths['real']) and os.listdir(paths['real']):
            matching_files = filecmp.dircmp(paths['test'], paths['real']).same_files
            if os.listdir(paths['real']) != matching_files:
                raise ValueError(f"Fail: Data files already exist in {paths['real']}")
            else:
                print(f"  Nothing to do: Test data already in {paths['real']}")
        else:
            shutil.copytree(paths['test'], paths['real'])
            print(f"  Test data sucessfully copied from {paths['test']} to {paths['real']}")

    def remove_test_data(name, root='', test_data='test_data', cat_filename='catalog.yml'):
        paths = _prepare_paths(root, name, test_data, cat_filename)

        if os.path.exists(paths['cat_real']):
            print("* Replacing intake catalog ...")

            if not os.path.exists(paths['cat_tmp']):
                print("  Nothing to do: No temp file found. Use git status to "
                      f"check that you have the real catalog at {paths['cat_real']}")
            else:
                os.remove(paths['cat_real'])
                os.rename(paths['cat_tmp'], paths['cat_real'])
                print('  Intake catalog successfully cleaned')

        print('* Removing test data ...')

        if not os.path.exists(paths['test']):
            print(f"  Nothing to do: No test_data found for {name} in {paths['test']}")
        elif not os.path.exists(paths['real']):
            print(f"  Nothing to do: No data found in {paths['real']}")
        elif not os.listdir(paths['real']):
            os.rmdir(paths['real'])
            print(f"  No data found in {paths['real']}, just removed empty dir")
        elif not is_same(paths['test'], paths['real']):
            raise ValueError(f"Fail: Data files at {paths['real']} are not identical to test, "
                             "so they shouldn't be deleted.")
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
        import subprocess
        from shutil import copyfile
        from yaml import safe_load, safe_dump

        print(f'Archving {project}...')
        readme_path = os.path.join(project, 'README.md')
        if not os.path.exists(readme_path):
            copyfile('README.md', readme_path)

        # stripping extra fields out of anaconda_project to make them more legible
        path = os.path.join(project, 'anaconda-project.yml')
        tmp_path = f'{project}_anaconda-project.yml'
        copyfile(path, tmp_path)
        with open(path, 'r') as f:
            spec = safe_load(f)

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
        copyfile(tmp_path, path)
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
        from shutil import copyfile
        src_dir = os.path.join(name, 'thumbnails')
        dst_dir = os.path.join('doc', name, 'thumbnails')
        if os.path.exists(src_dir):
            if not os.path.exists(dst_dir):
                os.makedirs(dst_dir)
            for item in os.listdir(src_dir):
                src = os.path.join(src_dir, item)
                dst = os.path.join(dst_dir, item)
                copyfile(src, dst)

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
    """Copy the projects assets to assets/."""

    def make_assets():
        from shutil import copyfile
        if not os.path.exists('assets'):
            os.mkdir('assets')
        for name in all_project_names(''):
            archived_project = os.path.join('doc', name, f'{name}.zip')
            if os.path.exists(archived_project):
                dst = os.path.join('assets',  f'{name}.zip')
                copyfile(archived_project, dst)
            assets_dir = os.path.join(name, 'assets')
            if os.path.exists(assets_dir):
                for item in os.listdir(assets_dir):
                    src = os.path.join(assets_dir, item)
                    dst = os.path.join('assets', item)
                    copyfile(src, dst)

    return {
        'actions': [make_assets],
        'clean': ['rm -rf assets/'],
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

def task_list_changed_dirs():
    """
    Print the list of projects that have changes compared to main.
    """

    def changes_in_dir(filepath='.diff'):
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
        
    return {
        'actions': [
            'git fetch origin main',
            'git diff origin/main %(sha)s --name-only > .diff',
            changes_in_dir,
        ],
        'params': [sha_param],
        'teardown': ['rm -f .diff']
    }

def task_validate_test_data():
    def validate_test_data(name, warning_as_error):
        from yaml import safe_load

        # Before this was run "anaconda-project list-downloads --directory {name}" 
        # and the output inspected (it returns 'No downloads in project') if
        # the project has no downloads. However this was pretty slow to run
        # over all the projects.

        path = os.path.join(name, 'anaconda-project.yml')
        with open(path, 'r') as f:
            spec = safe_load(f)

        downloads = spec.get('downloads', {})
        if downloads and not (pathlib.Path(name) / 'data').exists():
            complain(
                'Project has downloads but test data NOT found',
                warning_as_error,
            )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_test_data, [name])],
            'params': [warning_as_error_param],
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
    from yaml import safe_load

    path = pathlib.Path(name) / 'anaconda-project.yml'
    with open(path, 'r') as f:
        spec = safe_load(f)
    
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
    """
    from yaml import safe_load

    path = os.path.join(name, 'anaconda-project.yml')
    with open(path, 'r') as f:
        spec = safe_load(f)

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
        # skip_notebooks_evaluation = get_skip_notebooks_evaluation(name)
        skip_notebooks_evaluation = True
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
            'uptodate': [(should_skip_notebooks_evaluation, [name])],
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
