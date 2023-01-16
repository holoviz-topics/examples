# -*- coding: utf-8 -*-
from nbsite.shared_conf import *
import os
import glob
import yaml

EXCLUDE = ['assets', *glob.glob( '.*'), *glob.glob( '_*')]

project = u'Examples'
authors = u'PyViz Developers'
copyright = u'2019 ' + authors
description = 'Domain-specific narrative examples using multiple open-source Python visualization tools.'
long_description = ('Home for domain-specific narrative examples using '
                    'multiple PyViz projects. Each project is isolated and '
                    'fully described. For information on how to use these projects, '
                    'see the `User Guide <user_guide>`_.')
site = 'https://examples.pyviz.org'
version = release = '0.1.0'

html_static_path += ['_static']
html_theme = 'pydata_sphinx_theme'
html_logo = "_static/logo.png"
html_favicon = "_static/favicon.ico"

html_css_files = [
    'nbsite.css',
    'site.css',
]

templates_path += [
    '_templates'
]

nbbuild_cell_timeout = 600

extensions += [
    'nbsite.gallery',
    'sphinx_copybutton',
    # See https://github.com/ipython/ipython/issues/13845
    'IPython.sphinxext.ipython_console_highlighting',
]

# Turn off myst-nb execute (should not be required, but...)
nb_execution_mode = 'off'

def gallery_spec(name):
    path = os.path.join('..', name, 'anaconda-project.yml')
    with open(path) as f:
        spec = yaml.safe_load(f)
    url_name = name.replace('_', '-')
    # TODO: ask if it would be possible to move them to a holoviz domain
    # TODO: ask where the AE5 instance is actually located? Do we know how much it costs?
    deployment_urls = [
            f'https://{url_name}.pyviz.demo.anaconda.com',
            f'https://{url_name}-notebooks.pyviz.demo.anaconda.com']
    title = spec['name']
    description = spec['description']
    # Examples specific spec.
    examples_config = spec.get('examples_config', {})
    labels = examples_config.get('labels', [])
    skip = examples_config.get('skip', False)
    
    return {
        'path': name,
        'title': title,
        'description': description,
        'labels': labels,
        'skip': skip,
        'deployment_urls': deployment_urls,
    }

DIR = os.getenv('DIR')
if DIR:
    projects = [DIR]
else:
    projects = sorted([f for f in next(os.walk('.'))[1] if f not in EXCLUDE])
    projects = [p for p in projects if p!='grabcut']
    print('PROJECTS:', projects)

nbsite_gallery_inlined_conf = {
    'github_org': 'pyviz-topics',
    'github_project': 'examples',
    'host': 'assets',
    'download_as': 'project',
    'examples_dir': '..',
    'alternative_toctree': ['user_guide', 'make_project', 'maintenance'],
    'default_extensions': ['*.ipynb'],
    'only_use_existing': DIR is None,
    'path': '.',
    'title': 'PyViz Topics Examples',
    'intro': long_description,
    'sections': [gallery_spec(project) for project in projects],
}

html_context.update({
    "last_release": f"v{release}",
    "github_user": "pyviz-topics",
    "github_repo": "examples",
    "default_mode": "light"
})

html_theme_options = {
    "github_url": "https://github.com/pyviz-topics/examples",
    "icon_links": [
        {
            "name": "Twitter",
            "url": "https://twitter.com/holoviz_org",
            "icon": "fab fa-twitter-square",
        },
        {
            "name": "Discourse",
            "url": "https://discourse.holoviz.org/",
            "icon": "fab fa-discourse",
        },
    ],
    "footer_items": [
        "copyright",
        "last-updated",
    ],
    "navbar_end": ["navbar-icon-links"],
    "google_analytics_id": "UA-154795830-9",
    "pygment_light_style": "material",
    "pygment_dark_style": "material"
}
