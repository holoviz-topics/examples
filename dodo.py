# Only import from the standard lib, to keep this module easily importable!
# Inline external libraries imports.
import collections
import contextlib
import datetime
import glob
import imghdr
import itertools
import json
import os
import pathlib
import shutil
import struct
import subprocess
import textwrap
import uuid

##### Globals and default config #####

DEFAULT_EXCLUDE = [
    'doc',
    'envs',
    'test_data',
    'builtdocs',
    'assets',
    'jupyter_execute',
    '_extensions',
    *glob.glob( '.*'),
    *glob.glob( '_*'),
]

DEFAULT_DOC_EXCLUDE = [
    '_static',
    '_templates',
    # We don't want to include the template project in the main website
    'template',
]

# But it's included on the dev site if this env var is set.
if os.getenv('EXAMPLES_HOLOVIZ_DEV_SITE') is not None:
    DEFAULT_DOC_EXCLUDE.remove('template')

DEFAULT_SKIP_NOTEBOOKS_EVALUATION = False
DEFAULT_NO_DATA_INGESTION = False
DEFAULT_GH_RUNNER = 'ubuntu-latest'
DEFAULT_DEPLOYMENTS_AUTO_DEPLOY = True
DEFAULT_DEPLOYMENTS_RESOURCE_PROFILE = "medium"

NOTEBOOK_EVALUATION_TIMEOUT = 3600  # in seconds.

ENDPOINT_TEMPLATE_NOTEBOOK = '{servername}-notebook'
ENDPOINT_TEMPLATE_DASHBOARD = '{servername}'

# Same for hostname, different for username and password
AE5_CREDENTIALS_ENV_VARS = {
    'admin': {
        'username': 'EXAMPLES_HOLOVIZ_AE5_ADMIN_USERNAME',
        'password': 'EXAMPLES_HOLOVIZ_AE5_ADMIN_PASSWORD',
    },
    'non-admin': {
        'username': 'EXAMPLES_HOLOVIZ_AE5_USERNAME',
        'password': 'EXAMPLES_HOLOVIZ_AE5_PASSWORD',
    }
}

EXAMPLES_HOLOVIZ_AE5_ENDPOINT = os.getenv('EXAMPLES_HOLOVIZ_AE5_ENDPOINT', 'pyviz.demo.anaconda.com')

# python-dotenv is an optional dep,
# use it to define environment variables
try:
    from dotenv import load_dotenv
except ImportError:
    pass
else:
    load_dotenv()  # take environment variables from .env.

#### doit config and shared parameters ####

DOIT_CONFIG = {
    "verbosity": 2,
    "backend": "sqlite3",
}

ae5_hostname = {
    'name': 'hostname',
    'long': 'hostname',
    'type': str,
    'default': EXAMPLES_HOLOVIZ_AE5_ENDPOINT,
}

ae5_username = {
    'name': 'username',
    'long': 'username',
    'type': str,
    'default': '',
}

ae5_password = {
    'name': 'password',
    'long': 'password',
    'type': str,
    'default': '',
}

ae5_admin_username = {
    'name': 'admin_username',
    'long': 'admin-username',
    'type': str,
    'default': '',
}

ae5_admin_password = {
    'name': 'admin_password',
    'long': 'admin-password',
    'type': str,
    'default': '',
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
    'default': 'holoviz-topics/examples'
}

name_param = {
    'name': 'name',
    'long': 'name',
    'type': str,
    'default': 'all'
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


def complain(msg, level='WARNING'):
    """
    Print a warning, unless the environment variable
    EXAMPLES_HOLOVIZ_WARNING_AS_ERROR is set.
    """
    if (
        os.getenv('EXAMPLES_HOLOVIZ_WARNING_AS_ERROR', None) is not None
        and level == 'WARNING'
    ):
        raise ValidationError(msg)
    else:
        print(f'{level}: ' + msg)


def deployment_cmd_to_endpoint(cmd, name, full=True):
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

    if not full:
        return endpoint

    full_url = 'https://' + endpoint + '.' + EXAMPLES_HOLOVIZ_AE5_ENDPOINT
    return full_url


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
        # empty suffix is a hint for a directory, useful to catch when
        # a non-project file has been removed
        if pathlib.Path(root).is_file() or pathlib.Path(root).suffix != '':
            continue
        if root in DEFAULT_EXCLUDE:
            continue
        if root in all_projects:
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
    has_files = any(path.iterdir())
    return has_files


def project_has_no_data_ingestion(name):
    """Whether a project defines `no_data_ingestion` to True"""
    spec = project_spec(name)
    return spec.get('examples_config', {}).get(
        'no_data_ingestion', DEFAULT_NO_DATA_INGESTION
    )


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
    has_files = any(path.iterdir())
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
        if path.exists():
            already_there.append(path)
    yield
    for path in paths:
        if not path.exists():
            continue
        if path in already_there:
            continue
        if verbose:
            print(f'Removing {path}')
        path.unlink()


def run_fast_scandir(dir):
    """
    Traverse the filesystem, ignoring /envs and .examples_snapshot
    """
    subfolders, files = [], []

    for f in os.scandir(dir):
        if f.is_dir() and f.name != 'envs':
            subfolders.append(f.path)
        if f.is_file() and f.name != '.examples_snapshot':
            files.append(f.path)

    for dir in list(subfolders):
        sf, f = run_fast_scandir(dir)
        subfolders.extend(sf)
        files.extend(f)
    return subfolders, files


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
    skip_notebooks_evaluation = spec.get('examples_config', {}).get(
        'skip_notebooks_evaluation', DEFAULT_SKIP_NOTEBOOKS_EVALUATION
    )
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


#### AE5 utils ####

def ae5_session(hostname=None, username=None, password=None, admin=False):
    """
    Return an AE5UserSession if the credentials are provided, either
    directly or via environment variables. If not return None.
    """
    from ae5_tools.api import AEUserSession

    env_vars = AE5_CREDENTIALS_ENV_VARS
    cat = 'admin' if admin else 'non-admin'

    if not hostname:
        raise ValueError('Missing hostname')
    if not username:
        username = os.getenv(env_vars.get(cat).get('username'), None)
    if not password:
        password = os.getenv(env_vars.get(cat).get('password'), None)
    if any(arg is None for arg in (username, password)):
        print('Missing credentials to initialize the AE5 session')
        return None

    return AEUserSession(
        hostname=hostname, username=username, password=password
    )


def canonical_url(u):
    u = u.lower()
    if u.startswith("https://"):
        u = u[8:]
    if u.endswith("/"):
        u = u[:-1]
    return u


def find_endpoints(root='', name='all', include_auto_deploy=False):
    """
    Return a dict of <projectname>: <list of endpoints>
    """
    endpoints = collections.defaultdict(list)
    projects = all_project_names(root) if name == 'all'  else [name]
    for project in projects:
        spec = project_spec(project)
        deployments = spec.get('examples_config', {}).get('deployments', [])
        for depl in deployments:
            auto_deploy = depl.get('auto_deploy', DEFAULT_DEPLOYMENTS_AUTO_DEPLOY)
            if auto_deploy or include_auto_deploy:
                endpoint = deployment_cmd_to_endpoint(depl['command'], project, full=False)
                endpoints[project].append(endpoint)
    return dict(endpoints)


def list_ae5_projects(session):
    """
    List all the project names available to the authenticated user on AE5.
    """

    deployed_projects = session.project_list()

    # {'url': 'http://anaconda-enterprise-ap-storage/projects/d9f53edcf52a4942bcdf5183854eadef',
    # 'created': '2021-05-25T16:22:35.175500+00:00',
    # 'repo_owned': True,
    # 'repo_url': 'http://anaconda-enterprise-ap-git-storage/anaconda/anaconda-enterprise-d9f53edcf52a4942bcdf5183854eadef.git',
    # 'repository': 'anaconda-enterprise-d9f53edcf52a4942bcdf5183854eadef',
    # 'updated': '2022-04-07T17:01:17.616320+00:00',
    # 'project_create_status': 'done',
    # 'git_repos': {},
    # 'resource_profile': 'default',
    # 'owner': 'anaconda-enterprise',
    # 'id': 'a0-d9f53edcf52a4942bcdf5183854eadef',
    # 'git_server': 'default',
    # 'editor': 'notebook',
    # 'name': 'nyc_buildings',
    # '_record_type': 'project'}

    deployed_projects = set(project['name'] for project in deployed_projects)
    return sorted(deployed_projects)


def list_ae5_deployments(session, name=None):
    """
    List the deployments specs available to the authenticated user on AE5.
    The returned list can be limited to a project only.
    """

    deployments = session.deployment_list(format="json")

    # {'url': 'https://gapminders.pyviz.demo.anaconda.com/',
    # 'public': True,
    # 'created': '2022-12-08T11:12:20.538714+00:00',
    # 'project_name': 'gapminders',
    # 'goal_state': 'started',
    # 'source': 'http://anaconda-enterprise-ap-storage/projects/aa4854c00d1f475b95a45f2db3cf6bee/archive/latest',
    # 'project_url': 'http://anaconda-enterprise-ap-storage/projects/aa4854c00d1f475b95a45f2db3cf6bee',
    # 'updated': '2022-12-08T11:18:20.402424+00:00',
    # 'git_repos': {},
    # 'replicas': 1,
    # 'variables': {},
    # 'project_owner': 'anaconda-enterprise',
    # 'status_text': 'Started',
    # 'resource_profile': 'default',
    # 'revision': 'latest',
    # 'state': 'started',
    # 'owner': 'anaconda-enterprise',
    # 'id': 'a2-062618a509c94226a291fb938faeb1dd',
    # 'command': 'dashboard',
    # 'name': 'gapminders',
    # 'project_id': 'a0-aa4854c00d1f475b95a45f2db3cf6bee',
    # 'endpoint': 'gapminders',
    # '_record_type': 'deployment'}

    if name:
        deployments = [
            depl for depl in deployments
            if depl['project_name'] == name
        ]
    return deployments


def list_ae5_sessions(session, name):
    """
    List the sessions specs available to the authenticated user on AE5
    and for a given project.
    """

    sessions = session.session_list(format='json')

    # {'_project': {'_record_type': 'project',
    #             'created': '2020-06-20T21:36:00.642785+00:00',
    #             'editor': 'notebook',
    #             'git_repos': {},
    #             'git_server': 'default',
    #             'id': 'a0-144c9dd8b1e34ee09ed8c555a42f2dce',
    #             'name': 'Panel-Gallery',
    #             'owner': 'anaconda-enterprise',
    #             'project_create_status': 'done',
    #             'repo_owned': True,
    #             'repo_url': 'http://anaconda-enterprise-ap-git-storage/anaconda/anaconda-enterprise-144c9dd8b1e34ee09ed8c555a42f2dce.git',
    #             'repository': 'anaconda-enterprise-144c9dd8b1e34ee09ed8c555a42f2dce',
    #             'resource_profile': 'default',
    #             'updated': '2022-10-14T10:50:26.781927+00:00',
    #             'url': 'http://anaconda-enterprise-ap-storage/projects/144c9dd8b1e34ee09ed8c555a42f2dce'},
    # '_record_type': 'session',
    # 'created': '2022-12-14T15:38:25.795710+00:00',
    # 'id': 'a1-8bfc935b04794519bc3d2b637d3b51a7',
    # 'iframe_hosts': 'https://pyviz.demo.anaconda.com',
    # 'name': 'Panel-Gallery',
    # 'owner': 'anaconda-enterprise',
    # 'project_branch': 'anaconda-enterprise-d979c8be607b4745ac817dc6477f770d',
    # 'project_id': 'a0-144c9dd8b1e34ee09ed8c555a42f2dce',
    # 'project_url': 'http://anaconda-enterprise-ap-storage/projects/144c9dd8b1e34ee09ed8c555a42f2dce',
    # 'resource_profile': 'default',
    # 'session_name': '8bfc935b04794519bc3d2b637d3b51a7',
    # 'state': 'initial',
    # 'updated': '2022-12-14T15:38:25.795710+00:00',
    # 'url': 'http://anaconda-enterprise-ap-workspace/sessions/8bfc935b04794519bc3d2b637d3b51a7'}

    proj_sessions = []
    for session_ in sessions:
        assert session_['name'] == session_['_project']['name'], f'Unexpected sessions payload\n\n{session_!r}'
        if session_['name'] == name:
            proj_sessions.append(session_)

    return proj_sessions


def list_ae5_jobs(session, name):
    """
    List the jobs specs available to the authenticated user on AE5 and
    for a given project.
    """

    jobs = session.job_list(format='json')


    # {'_project': {'_record_type': 'project',
    #               'created': '2023-01-20T17:09:51.552442+00:00',
    #               'editor': 'notebook',
    #               'git_repos': {},
    #               'git_server': 'default',
    #               'id': 'a0-6d99ba7ada9e45d996bb561d5a19f562',
    #               'name': 'boids',
    #               'owner': 'holoviz-examples',
    #               'project_create_status': 'done',
    #               'repo_owned': True,
    #               'repo_url': 'http://anaconda-enterprise-ap-git-storage/anaconda/holoviz-examples-6d99ba7ada9e45d996bb561d5a19f562.git',
    #               'repository': 'holoviz-examples-6d99ba7ada9e45d996bb561d5a19f562',
    #               'resource_profile': 'default',
    #               'updated': '2023-01-20T17:09:51.552442+00:00',
    #               'url': 'http://anaconda-enterprise-ap-storage/projects/6d99ba7ada9e45d996bb561d5a19f562'},
    #  '_record_type': 'job',
    #  'command': 'notebook',
    #  'created': '2023-01-20T17:40:28.978378+00:00',
    #  'git_repos': {},
    #  'goal_state': 'scheduled',
    #  'id': 'a2-c06fd89ed71844dc91f5476c92744bcd',
    #  'name': 'test',
    #  'owner': 'holoviz-examples',
    #  'project_id': 'a0-6d99ba7ada9e45d996bb561d5a19f562',
    #  'project_name': 'boids',
    #  'project_owner': 'holoviz-examples',
    #  'project_url': 'http://anaconda-enterprise-ap-storage/projects/6d99ba7ada9e45d996bb561d5a19f562',
    #  'resource_profile': 'default',
    #  'revision': 'latest',
    #  'schedule': '5 4 5 5 *',
    #  'source': 'http://anaconda-enterprise-ap-storage/projects/6d99ba7ada9e45d996bb561d5a19f562/archive/latest',
    #  'state': 'scheduled',
    #  'status_text': 'Scheduled job',
    #  'updated': '2023-01-20T17:40:30.835304+00:00',
    #  'url': 'http://anaconda-enterprise-ap-deploy/jobs/c06fd89ed71844dc91f5476c92744bcd',
    #  'variables': {}}

    proj_jobs = []
    for job in jobs:
        if job['project_name'] == name:
            proj_jobs.append(job)

    return proj_jobs


def remove_project(session, name):
    """
    Remove a project on AE5, stopping its deployments before that if any.
    """
    # from ae5_tools.api import AEUnexpectedResponseError
    projects = list_ae5_projects(session)
    if name not in projects:
        print(f'Project {name!r} not found on AE5, skip.')
        return
    project_deployments = list_ae5_deployments(session, name=name)
    if project_deployments:
        print(f'Project {name!r} has {len(project_deployments)} deployments to stop...')
        for depl in project_deployments:
            print(f'Stopping endpoint {depl["endpoint"]!r} ...')
            session.deployment_stop(ident=depl)
            print(f'Endpoint {depl["endpoint"]!r} stopped.')

    print(f'Deleting remote project {name}...')
    session.project_delete(ident=name)
    print(f'Remote project {name} deleted!')

############# TASKS #############

#### Utils tasks ####


def task_util_gh_runner():
    """Print the gh runner of a project"""

    def project_gh_runner(name):
        spec = project_spec(name)
        runner = spec.get('examples_config', []).get('gh_runner', DEFAULT_GH_RUNNER)
        print(runner)

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(project_gh_runner, [name])]
        }


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
            'git diff --merge-base --name-only origin/main > .diff',
            print_changes_in_dir,
        ],
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

        user_config = spec.get('examples_config', [])

        root_required = [
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
        for entry in root_required:
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
        if 'test' in commands:
            complain(
                'Found `test` command, are you sure you need it? '
                'Most projects are tested remotely by nbval, smoke testing '
                'the notebooks, so you do not usually need a `test` command. '
                'Having it however means that nbval will not be used and that '
                'your project is going to be tested solely based on your '
                'command.',
                level='INFO',
            )
        if 'lint' in commands:
            complain(
                'Linting is done by the system and should not be defined on '
                'a per-project basis, please remove the `lint` command.'
            )
        # Seems like defining the lint/test commands with -k *.ipynb was
        # actually ignoring all the notebooks when there was more than one.
        for cmd in ('test', 'lint'):
            cmd_spec = commands.get('cmd', {})
            for target in ('unix', 'windows'):
                cmd_string = cmd_spec.get(target, '')
            if '-k *.ipynb' in cmd_string:
                suggestion = '-k ".ipynb"'
                complain(
                    f"Replace '-k *.ipynb' by '{suggestion}' in command {command}/{target}"
                )

        notebook_cmds = [
            cmd
            for cmd, cmd_spec in commands.items()
            if 'notebook' in cmd_spec
        ]
        if 'notebook' not in commands and notebook_cmds:
            complain(
                f'Found at least one command using the special `notebook` spec type ({", ".join(notebook_cmds)!r}), '
                'one of them must be named "notebook".'
            )

        serve_cmds = {
            cmd: cmd_spec
            for cmd, cmd_spec in commands.items()
            if 'unix' in cmd_spec and
            any(served in cmd_spec['unix'] for served in ('panel serve', 'lumen serve'))
        }
        if serve_cmds and not 'dashboard' in serve_cmds:
            complain(
                f'Command serving Panel/Lumen apps must be called `dashboard`, not {list(serve_cmds)}',
            )
        dashboard_cmd = commands.get('dashboard')
        if dashboard_cmd and (
            "-rest-session-info" not in dashboard_cmd["unix"]
            or "--session-history -1" not in dashboard_cmd["unix"]
        ):
            complain(
                'dashboard command serving Panel/Lumen apps must set "--rest-session-info --session-history -1"',
            )

        env_specs = spec.get('env_specs', {})
        if 'test' in env_specs:
            complain(
                'Found a "test" env_spec, are you sure you need it? If so '
                'you also need to define a "test" command, with which '
                'the tests of your project are going to be executed '
                'instead of relying on the remote tests run by the system',
                level='INFO',
            )
        user_fields = spec.get('user_fields', [])
        if user_fields != ['examples_config']:
            complain('`user_fields` must be [examples_config]')

        # Validating maintainers and labels
        expected = ['maintainers', 'labels']
        for entry in expected:
            if entry not in user_config:
                complain(f'missing {entry!r} list')
                continue
            value = user_config[entry]
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

        # Validating created
        created = user_config.get('created')
        if created:
            if not isinstance(created, datetime.date):
                complain('`created` value must be a date expressed as YYYY-MM-DD')
        else:
            complain('`created` entry not found')

        # Validating last_updated
        last_updated = user_config.get('last_updated', '')
        if last_updated and not isinstance(last_updated, datetime.date):
            complain('`last_updated` value must be a date expressed as YYYY-MM-DD')

        # Validating last_updated
        title = user_config.get('title', '')
        if title and not isinstance(title, str):
            complain('`title` value must be a string')

        # Validating deployments
        deployments = user_config.get('deployments')
        if deployments:
            if not isinstance(deployments, list):
                complain('`deployments` must be a list')
            for depl in deployments:
                if not isinstance(depl, dict):
                    complain('a deployment entry must be a dict')
                command = depl.get('command', None)
                if not command:
                    complain(f'missing `command` in deployment {depl}')
                expected_command = ('dashboard', 'notebook')
                if command not in expected_command:
                    complain(
                        f'`command` can only be one of {expected_command!r}, '
                        f'not {command}'
                    )
                resource_profile = depl.get('resource_profile', None)
                expected_rp = ('default', 'medium', 'large')
                if resource_profile and resource_profile not in expected_rp:
                    complain(
                        f'`resource_profile` can only be one of {expected_rp!r}, '
                        f'not {resource_profile}'
                    )
                auto_deploy = depl.get('auto_deploy', None)
                if auto_deploy is not None and not isinstance(auto_deploy, bool):
                    complain(f'`auto_deploy` must be a boolean, not {auto_deploy}')

        # Validating skip_notebooks_evaluation
        skip_notebooks_evaluation = user_config.get('skip_notebooks_evaluation', None)
        if skip_notebooks_evaluation is not None and not isinstance(skip_notebooks_evaluation, bool):
            complain(f'`skip_notebooks_evaluation` must be a boolean, not {skip_notebooks_evaluation}')

        # Validating no_data_ingestion
        no_data_ingestion = user_config.get('no_data_ingestion', None)
        if no_data_ingestion is not None and not isinstance(no_data_ingestion, bool):
            complain(f'`no_data_ingestion` must be a boolean, not {no_data_ingestion}')

        # Validation gh_runner
        gh_runner = user_config.get('gh_runner', None)
        allowed_runners = ['ubuntu-latest', 'macos-latest', 'windows-latest']
        if gh_runner is not None and not gh_runner in allowed_runners:
            complain(f'"gh_runner" must be one of {allowed_runners}')

        required_config = ['created', 'maintainers', 'labels']
        optional_config = [
            'last_updated', 'deployments', 'skip_notebooks_evaluation',
            'no_data_ingestion', 'title', 'gh_runner',
        ]
        for key in user_config:
            if key not in required_config + optional_config:
                complain(f'Unexpected entry {key!r} found in `examples_config`')

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(validate_project_file, [name])],
        }

def task_validate_project_lock():
    """Validate the existence of the anaconda-project-lock.yml file"""

    def validate_project_lock(name):
        import anaconda_project.internal.conda_api as conda_api
        from anaconda_project.project import Project
        from anaconda_project.project_lock_file import ProjectLockFile

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

                if env_spec.platforms != env_spec.lock_set.platforms:
                    if len(env_spec.lock_set.platforms) == 0:
                        text = "Env spec '%s' specifies platforms '%s' but the lock file lists no platforms for it" % (
                            env_spec.name, ",".join(env_spec.platforms))
                    else:
                        text = ("Env spec '%s' specifies platforms '%s' but the lock file has " +
                                "locked versions for platforms '%s'") % (env_spec.name, ",".join(
                                    env_spec.platforms), ",".join(env_spec.lock_set.platforms))
                        complain(text)
                
                if len(env_spec.conda_packages) > 0:
                    for platform in env_spec.lock_set.platforms:
                        conda_packages = env_spec.lock_set.package_specs_for_platform(platform)
                        if len(conda_packages) == 0:
                            text = ("Lock file lists no packages for env spec '%s' on platform %s") % (env_spec.name,
                                                                                                    platform)
                            complain(text)
                        else:
                            # If conda ever had RPM-like "Obsoletes" then this situation _may_ happen
                            # in correct scenarios.
                            lock_set_names = set()
                            for package in conda_packages:
                                parsed = conda_api.parse_spec(package)
                                if parsed is not None:
                                    lock_set_names.add(parsed.name)
                            unlocked_names = env_spec.conda_package_names_set - lock_set_names
                            if len(unlocked_names) > 0:
                                text = "Lock file is missing %s packages for env spec %s on %s (%s)" % (
                                    len(unlocked_names), env_spec.name, platform, ",".join(sorted(list(unlocked_names))))
                                complain(text)

                # Look for lock sets that don't go with an env spec
                lock_file = ProjectLockFile.load_for_directory(project.directory_path)
                lock_file = project.lock_file
                lock_sets = lock_file.get_value(['env_specs'], {})
                for name in lock_sets.keys():
                    if name not in project.env_specs:
                        text = ("Lock file lists env spec '%s' which is not in %s") % (name, 'anaconda-project.yml')
                        complain(text)

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

        for dirname, dirs, filenames in os.walk(proj_dir):
            dirs[:] = [d for d in dirs if d not in ['envs']]
            for file in filenames:
                if file.endswith(('.yml', '.yaml')):
                    path = pathlib.Path(dirname, file)
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
        # https://github.com/holoviz-topics/examples/blob/d85de1c78f1351047c003cddd0d4b02603f08f2a/dodo.py#L49-L183
        if has_data_folder and (has_downloads or has_intake_catalog):
            raise NotImplementedError(
                'Relying on `downloads` in anaconda-project.yml OR '
                'on an Intake catalog, together with the presence of '
                'a `data/` folder is not supported (need updates in '
                'task_small_data_setup'
            )
        
        if has_data_folder:
            pignore = pathlib.Path(name, '.projectignore')
            if pignore.exists():
                lines = pignore.read_text().splitlines()
                if any(line.strip() in ('data', 'data/') for line in lines):
                    complain(
                        '.projectignore must not ignore the "data/" folder'
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
        
        if has_intake_catalog:
            spec = project_spec(name)
            if not spec.get('variables', {}).get('INTAKE_CACHE_DIR', '') == 'data':
                complain(
                    'The project has an Intake catalog, it must declare the '
                    'variable INTAKE_CACHE_DIR in its anaconda-project.yml file '
                    'and set it to "data".'
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
        # No index.ipynb file, the project isn't displayed so just complain
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
    - 0.9 < aspect ratio < 1.5
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
            return
        thumb = thumb_folder / (notebook.stem + '.png')
        size = thumb.stat().st_size * 1e-6
        if size > 1:
            complain(f'thumbnail size ({size:.2f} MB) is above 1MB')
        w, h = get_png_dims(thumb)
        aspect_ratio = w / h
        if not (0.9 <= aspect_ratio <= 1.5):
            complain(
                f'thumbnail aspect ratio ({aspect_ratio:.2f}) must be between 0.9 and 1.5',
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
                    f"'doit clean test_small_data_setup:{name}'"
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
                f"'doit clean test_small_data_setup:{name}'"
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
    Run `anaconda-project prepare --directory name`

    `anaconda-project prepare ...` doesn't download the data is already there.
    Instead it prints "Previously downloaded file located at <abs/to/data>"
    This is why it makes sense to setup the small test data before running
    `anaconda-project prepare`.

    # TODO: remove if not needed
    This doesn't run if `skip_test` is set to True.
    """

    def prepare_project(name):
        with removing_files([pathlib.Path(name, '.projectignore')]):
            subprocess.run(
                ['anaconda-project', 'prepare', '--directory', name],
                check=True
            )

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(prepare_project, [name])],
            'uptodate': [(should_skip_test, [name])],
            'clean': [f'rm -rf {name}/envs'],
        }

def task_test_lint_project():
    """Lint a project with nbqa flake8

    Skipped notebooks are not linted, Python scripts either.
    Check the pyproject.toml file to see which rules are ignored,
    add more if need be.
    """
    def lint_notebooks(name):
        notebooks = find_notebooks(name)
        notebooks = [str(nb) for nb in notebooks]
        subprocess.run(['nbqa', 'flake8'] + notebooks, check=True)

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(lint_notebooks, [name])],
            'uptodate': [(should_skip_test, [name])],
        }


def task_test_project():
    """Test a project

    This is either done:
    - remotely with nbval, executing the project's kernel, assuming the project
      environment has been prepared
    - if a `test` command is found then that command is executed.

    Just noting that an alternative at the time of writing for nbval would
    be nbmake, as it also allows to smoke test notebooks remotely.
    """

    def has_test_command(name):
        spec = project_spec(name)
        cmd = spec.get('commands', {}).get('test', {})
        return bool(cmd)

    def test_notebooks(name):
        notebooks = find_notebooks(name)
        notebooks = [str(nb) for nb in notebooks]
        subprocess.run(
            [
                'pytest',
                '--nbval-lax',
                '--nbval-cell-timeout=3600',
                f'--nbval-kernel-name={name}-kernel',
            ] + notebooks,
            check=True
        )

    for name in all_project_names(root=''):
        if has_test_command(name):
            yield {
                'name': name,
                'actions': [f'anaconda-project run --directory {name} test'],
                # TODO: remove if all the projects can actually be tested
                'uptodate': [(should_skip_test, [name])]
            }
        else:

            try:
                import nbval.plugin
            except ImportError:
                pass
            else:
                old_runtest = nbval.plugin.IPyNbCell.runtest
                
                def runtest(self):
                    self.output_timeout = 10
                    old_runtest(self)
                
                nbval.plugin.IPyNbCell.runtest = runtest

            yield {
                'name': name,
                'actions': [
                    f'echo "install kernel {name}-kernel"',
                    # Setup Kernel
                    f'conda run --prefix {name}/envs/default python -m ipykernel install --user --name={name}-kernel',
                    # Run notebooks with that kernel
                    (test_notebooks, [name]),
                ],
                'teardown': [
                    f'echo "remove kernel {name}-kernel"',
                    # Remove Kernel
                    f'conda run --prefix {name}/envs/default jupyter kernelspec remove {name}-kernel -f',
                ],
                # TODO: remove if all the projects can actually be tested
                'uptodate': [(should_skip_test, [name])]
            }


#### Build ####


def task_build_list_existing_files():
    """
    Saves the existing files paths in a file.

    Saves in .examples_snapshot all the files and folders found in the
    directory, except this file and the /envs folder.
    """

    def list_existing_items(name):
        subfolders, files = run_fast_scandir(name)
        paths = sorted(subfolders + files)
        pathlib.Path(name, '.examples_snapshot').write_text("\n".join(paths))

    def clean(name):
        envs = pathlib.Path(name, 'envs')
        if envs.is_dir():
            print(f'Removing the environment folder: {envs} ...')
            shutil.rmtree(envs)
        fsnapshot = pathlib.Path(name, '.examples_snapshot')
        if not fsnapshot.exists():
            return
        before = set(fsnapshot.read_text().splitlines())
        subfolders, files = run_fast_scandir(name)
        now = set(subfolders + files)
        new = now - before
        for p in new:
            p = pathlib.Path(p)
            if p.is_file():
                print(f'Removing file {p}')
                p.unlink()
            elif p.is_dir():
                print(f'Removing directory {p}')
                shutil.rmtree(p)
        print('Removing snapshot')
        fsnapshot.unlink()

    for name in all_project_names(root=''):
        yield {
            'name': name,
            'actions': [(list_existing_items, [name]),],
            'clean': [(clean, [name]),],
        }


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

    def clean_notebooks(name):
        folder = pathlib.Path('doc', name)
        if not folder.is_dir():
            return
        print(f'Removing all from {folder}')
        shutil.rmtree(folder)

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
            'clean': [(clean_notebooks, [name]),],
        }


#### Doc ####


def task_doc_archive_projects():
    """Archive projects to assets/_archives"""

    def archive_project(root='', name='all', extension='.zip'):
        projects = all_project_names(root) if name == 'all'  else [name]
        for project in projects:
            _archive_project(project, extension)

    def _archive_project(project, extension):
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

        # TODO: removing the test env_specs here but not in the lock
        # leads to a warning emitted to users when they prepare their project.

        # stripping extra fields out of anaconda_project to make them more legible
        path = os.path.join(project, 'anaconda-project.yml')
        tmp_path = f'{project}_anaconda-project.yml'
        shutil.copyfile(path, tmp_path)
        spec = project_spec(project)

        # special field that anaconda-project doesn't know about
        spec.pop('examples_config', '')
        spec.pop('user_fields', '')

        # commands and envs that users don't need
        spec.get('commands', {}).pop('test', '')
        spec.get('commands', {}).pop('lint', '')
        spec.get('env_specs', {}).pop('test', '')

        # get rid of any empty fields
        spec = {k: v for k, v in spec.items() if bool(v)}

        with open(path, 'w') as f:
            safe_dump(spec, f, default_flow_style=False, sort_keys=False)

        archives_path = os.path.join('assets', '_archives')
        if not os.path.exists(archives_path):
            os.makedirs(archives_path)

        subprocess.run(
            ["anaconda-project", "archive", "--directory", f"{project}", f"assets/_archives/{project}{extension}"],
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
        for ext in ('.zip', '.tar.bz2'):
            archive_path = _archives_path / f'{project}{ext}'
            if archive_path.exists():
                print(f'Removing {archive_path}')
                archive_path.unlink(archive_path)

    return {
        'actions': [archive_project],
        'params': [
            name_param,
            {
                'name': 'extension',
                'long': 'extension',
                'type': str,
                'choices': (('.zip', ''), ('.tar.bz2', '')),
                'default': '.zip'
            }
        ],
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
    """Copy the projects assets to doc/projname/assets/
    """

    def move_assets(root='', name='all'):
        projects = all_project_names(root) if name == 'all'  else [name]
        for project in projects:
            _move_assets(project)

    def _move_assets(name):
        # Copy all the files in ./projname/assets to ./doc/projname/assets/
        proj_assets_path = pathlib.Path(name, 'assets')
        if proj_assets_path.exists():
            dest_assets_path = pathlib.Path('doc', name, 'assets')
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
        doc_dir = pathlib.Path('doc')
        proj_dir = doc_dir / name
        if not proj_dir.exists():
            return
        project_assets_dir = proj_dir / 'assets'
        if not project_assets_dir.exists():
            return
        for asset in project_assets_dir.iterdir():
            if asset.is_file():
                print(f'Removing asset {asset}')
                asset.unlink()
            elif asset.is_dir():
                print(f'Removing empty dir {asset}')
                shutil.rmtree(asset)
        project_assets_dir.rmdir()

    return {
        'actions': [move_assets],
        'params': [name_param],
        'clean': [clean_assets],
    }


def task_doc_get_evaluated():
    """Fetch the evaluated branch and checkout the /doc folder"""

    def checkout(name):
        if name == 'all':
            name = ''
        
        subprocess.run(
            ['git', 'checkout', 'evaluated', '--', f'./doc/{name}'],
            check=True,
        )

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
            checkout,
            # The previous command stages all what is in doc/, unstage that.
            # This is better UX when building the site locally, not needed on the CI.
            'git reset doc/',
        ],
        'clean': [clean_doc],
        'params': [
            githubrepo_param,
            name_param,
        ]
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
            "sphinx-build -b html doc builtdocs"
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

    E.g. examples.holovz.org/projname

    A previous approach was using symlinks and this should behave the same
    but can be used where symlinks are not suitable.
    https://github.com/holoviz-topics/examples/blob/17a17be1a1b159095be55801202741e049a780e8/dodo.py#L281-L298
    """

    REDIRECT_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>{name} redirect</title>
        <meta http-equiv = "refresh" content = "0; url = https://examples.holoviz.org/{name}/{name}.html" />
    </head>
    </html>
    """

    def generate_index_redirect(root='', name='all'):
        projects = all_project_names(root) if name == 'all'  else [name]
        for project in projects:
            _generate_index_redirect(project)

    def write_redirect(name):
        with open('./index.html', 'w') as f:
            contents = textwrap.dedent(REDIRECT_TEMPLATE.format(name=name))
            f.write(contents)
            print('Created relative HTML redirect for %s' % name)

    # TODO: known to generate some broken redirects.
    def _generate_index_redirect(project):
        cwd = os.getcwd()
        project_path = os.path.abspath(os.path.join('.', 'builtdocs', project))
        os.chdir(project_path)
        try:
            listing = os.listdir(project_path)
            if 'index.html' not in listing:
                write_redirect(project)
        except Exception as e:
            complain(str(e))
        finally:
            os.chdir(cwd)

    def clean_index_redirects(root='', name='all'):
        projects = all_project_names(root) if name == 'all'  else [name]
        for project in projects:
            _clean_index_redirects(project)

    def _clean_index_redirects(project):
        project_path = pathlib.Path('builtdocs') / project
        index_path = project_path / 'index.html'
        if index_path.is_file():
            print(f'Removing index redirect {index_path}')
            index_path.unlink()

    return {
        'actions': [generate_index_redirect],
        'params': [name_param],
        'clean': [clean_index_redirects]
    }

#### AE5 ####

AE5_USER_PARAMS = [ae5_hostname ,ae5_username, ae5_password]
AE5_ALL_PARAMS = AE5_USER_PARAMS + [ae5_admin_username, ae5_admin_password]

def task_ae5_list_deployments():
    """
    List the deployments on AE5.

    Including:
    - examples deployments found
    - missing deployments
    - unexpected deployments
    """

    def _list_deployments(hostname, username, password):
        session = ae5_session(hostname, username, password)
        if not session:
            complain('AE5 Session could not be initialized', level='INFO')
            return

        projects_local = all_project_names(root='')

        deployments_ae5_ = list_ae5_deployments(session)
        endpoints_ae5 = [depl['endpoint'] for depl in deployments_ae5_]

        deployments_ae5 = {}
        for k, g in itertools.groupby(deployments_ae5_, key=lambda l: l['project_name']):
            deployments_ae5[k] = list(g)

        deployments_local = {}
        for project in projects_local:
            spec = project_spec(project)
            depls = spec['examples_config'].get('deployments', [])
            if depls:
                deployments_local[project] = depls
        endpoints_local = [
            deployment_cmd_to_endpoint(depl['command'], name, full=False)
            for name, depls in deployments_local.items()
            for depl in depls
        ]

        deployed = collections.defaultdict(list)
        missing = collections.defaultdict(list)
        unexpected = collections.defaultdict(list)
        for project, depls in deployments_local.items():
            for depl in depls:
                local_endpoint = deployment_cmd_to_endpoint(
                    depl['command'], project, full=False
                )
                if local_endpoint in endpoints_ae5:
                    ae5_depl = [
                        depl
                        for depl in deployments_ae5[project]
                        if depl['endpoint'] == local_endpoint
                    ][0]
                    deployed[project].append(ae5_depl)
                else:
                    missing[project].append(depl)
        
        for project, depls in deployments_ae5.items():
            for depl in depls:
                if depl['endpoint'] not in endpoints_local:
                    unexpected[project].append(depl)

        if deployed:
            print('Deployments found:')
            for project, depls in deployed.items():
                print(f'  * Project {project!r}')
                for depl in depls:
                    print(f'    - {depl["url"]!r} (command {depl["command"]!r}, resource_profile: {depl["resource_profile"]!r})')
                print()

        if missing:
            print('Missing deployments:')
            for project, depls in missing.items():
                print(f'  * Project {project!r}')
                for depl in depls:
                    print(f'    - {depl["command"]!r}')
                print()

        if unexpected:
            print('Unexpected deployments:')
            for project, depls in unexpected.items():
                print(f'  * Project {project!r}')
                for depl in depls:
                    print(f'    - {depl["url"]!r} (command {depl["command"]!r}, resource_profile: {depl["resource_profile"]!r})')
                print()


        return

    return {
        'actions': [_list_deployments],
        'params': AE5_USER_PARAMS,
    }


def task_ae5_list_projects():
    """
    List the projects on AE5.

    Including:
    - examples projects found
    - examples projects not found
    - unexpected non-examples projects
    """

    def _list_projects(hostname, username, password):

        session = ae5_session(hostname, username, password)
        if not session:
            complain('AE5 Session could not be initialized', level='INFO')
            return

        projects_ae5 = set(list_ae5_projects(session))
        projects_local = set(all_project_names(root=''))
        unwanted = projects_ae5 - projects_local
        deployed = projects_ae5 & projects_local
        non_deployed = projects_local - deployed
        if deployed:
            print(f'Projects found ({len(deployed)}):')
            print(", ".join(sorted(deployed)))
            print()
        if non_deployed:
            print(f'Projects not found ({len(non_deployed)}):')
            print(", ".join(sorted(non_deployed)))
            print()
        if unwanted:
            print(f'Unwanted projects ({len(unwanted)}):')
            print(", ".join(sorted(unwanted)))
            print()

    return {
        'actions': [_list_projects],
        'params': AE5_USER_PARAMS,
    }


def task_ae5_validate_deployment():
    """
    Validate the deployments can be made.
    """

    def validate_deployment(name, hostname, username, password, admin_username, admin_password):
        # Need an ADMIN account to get the list of ALL the deployments
        # to check that the project to update/add will not try to use
        # an endpoint already used by another project on the AE5 instance.
        admin_session = ae5_session(hostname, admin_username, admin_password, admin=True)
        if not admin_session:
            complain('AE5 Admin Session could not be initialized', level='INFO')
            return

        expected_endpoints = find_endpoints(
            root='', name=name, include_auto_deploy=True
        ).get(name, [])
        if not expected_endpoints:
            return

        # check no other project use one of the planned endpoints
        all_deployments = list_ae5_deployments(admin_session)
        uname = username or os.getenv(AE5_CREDENTIALS_ENV_VARS['non-admin']['username'])
        for deployment in all_deployments:
            # this is the project we aim to update, skip.
            if deployment['project_name'] == name and deployment['owner'] == uname:
                continue
            depl_endpoint = deployment['endpoint']

            # Will warn if the env var is set and this endpoint is already used
            # on the instance by another project.
            if depl_endpoint in expected_endpoints:
                if os.getenv('EXAMPLES_HOLOVIZ_STRICT_DEPLOYMENT_POLICY') is not None:
                    level = 'WARNING'
                else:
                    level = 'INFO'
                complain(
                    f'Endpoint {deployment["url"]!r} already used by project '
                    f'{deployment["project_name"]!r}. Ask a maintainer if '
                    f'it can be stopped, if not, rename your project. \n\n{deployment!r}\n',
                    level=level
                )

        # Switch to the user session
        del admin_session, all_deployments
        session = ae5_session(hostname, username, password)
        if not session:
            complain('AE5 Session could not be initialized', level='INFO')
            return

        all_deployments = list_ae5_deployments(session)

        # check the project has no other deployments than the expected ones,
        # that can only deploy dashboard or notebook
        project_deployments = [
            depl for depl in all_deployments
            if depl['project_name'] == name
        ]
        for pdepl in project_deployments:
            if pdepl['command'] not in ['dashboard', 'notebook']:
                complain(
                    f'Unexpected deployment {pdepl["url"]!r} (command {pdepl["command"]!r}) '
                    f'found set by project {pdepl["project_name"]!r}, close it if possible or '
                    f'change the project name to get another endpoint.\n\n{pdepl!r}\n'
                )

        # check the project has no active sessions
        project_sessions = list_ae5_sessions(session, name)
        if project_sessions:
                complain(
                    f'Unexpected sessions found, close them:\n\n {project_sessions!r}\n'
                )

        # check the project has no jobs.
        project_jobs = list_ae5_jobs(session, name)
        if project_jobs:
                complain(
                    f'Unexpected jobs found, close them:\n\n {project_jobs!r}\n'
                )

    return {
        'actions': [validate_deployment],
        'params': [name_param] + AE5_ALL_PARAMS,
    }


def task_ae5_remove_project():
    """
    Remove a project on AE5.
    """

    def _remove_project(name, hostname, username, password):
        session = ae5_session(hostname, username, password)
        if not session:
            complain('AE5 Session could not be initialized', level='INFO')
            return

        remove_project(session, name)

    return {
        'actions': [_remove_project],
        'params': [name_param] + AE5_USER_PARAMS,
    }


def task_ae5_sync_project():
    """
    Create/Update a project on AE5.

    It expects the archive to be a .tar.bz2 saved in assets/_archives/
    If a project is found it will delete it automatically.
    """

    def _sync_project(name, hostname, username, password):

        spec = project_spec(name)
        deployments = spec.get('examples_config', {}).get('deployments', {})
        deployments = [
            depl
            for depl in deployments
            if depl.get('auto_deploy', DEFAULT_DEPLOYMENTS_AUTO_DEPLOY)
        ]
        if not deployments:
            print('No deployments found in the project file')
            return
        print(f'Found {len(deployments)} deployments to start:\n{deployments}\n')

        archive = pathlib.Path('assets', '_archives', f'{name}.tar.bz2')
        if not archive.exists():
            raise FileNotFoundError(f'Expected archive {archive} not found')

        session = ae5_session(hostname, username, password)
        if not session:
            complain('AE5 Session could not be initialized', level='INFO')
            return

        deployed_projects = list_ae5_projects(session)

        # Remove if there, this should also shut down existing deployments
        if name in deployed_projects:
            remove_project(session, name)

        print(f'Uploading project {name!r} as {name!r} using archive {archive} ...')
        response = session.project_upload(
            project_archive=str(archive), name=name, tag='0.0.1', wait=True
        )
        print('Uploaded project with response:')
        print(response)
        print()

        status = response.get('project_create_status', '')
        if status.lower()  != 'done':
            raise RuntimeError(f'"project_create_status" is not "done" but {status}')

        for dspec in deployments:
            command = dspec['command']
            resource_profile = dspec.get(
                'resource_profile', DEFAULT_DEPLOYMENTS_RESOURCE_PROFILE
            )
            endpoint = deployment_cmd_to_endpoint(command, name, full=False)

            print(
                f'Start deployment of command {command!r} at the endpoint '
                f'{endpoint!r} with resource_profile {resource_profile!r} '
                f'for the AE5 project {name!r} ...'
            )
            try:
                # - Waiting means that it can take a while (downloading data,
                # installing the env, etc.) but feels safer for now.
                # - Deployments can't have the same name across projects.
                dname = command + '_' + str(uuid.uuid4())
                response = session.deployment_start(
                    ident=name, endpoint=endpoint, command=command, name=dname,
                    resource_profile=resource_profile, public=True, wait=True,
                )
                if not response['state'] == 'started':
                    raise RuntimeError(f'Deployment failed with response {response}')
            except Exception as e:
                print(f'Deployment failed with {e}')
                print('Attempt to remove the just created project')
                remove_project(session, name)
                raise
            print(f'Deployment started!\n Visit {response["url"]}\n')
            print('Full response:')
            print(response)
            print()

    return {
        'actions': [_sync_project],
        'params': [name_param] + AE5_USER_PARAMS,
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
                f'build_list_existing_files:{name}',
                f'build_prepare_project:{name}',
                f'build_process_notebooks:{name}',
            ]
        }


def task_doc_project():
    """
    Build the doc for a single project (doit doc_project --name <projname>) 

    Run the following command to clean the outputs:
        doit clean doc_project
    """
    return {
        'actions': [
            'doit doc_archive_projects --name %(name)s',
            'doit doc_move_thumbnails --name %(name)s',
            'doit doc_move_assets --name %(name)s',
            'doit doc_build_website',
            'doit doc_index_redirects --name %(name)s',
        ],
        'clean': [
            'doit clean doc_archive_projects',
            'doit clean doc_move_thumbnails',
            'doit clean doc_move_assets',
            'doit clean doc_build_website',
            'doit clean doc_index_redirects',
        ],
        'params': [name_param],
    }


def task_doc_full():
    """
    Build the full doc (doit doc)

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
        ],
    }
