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
html_theme = 'sphinx_pyviz_theme'
# logo file etc should be in html_static_path, e.g. _static
# only change colors in primary, primary_dark, and secondary
html_theme_options = {
    'logo': 'logo.png',
    'favicon': 'favicon.ico',
    'primary_color': '#666666',
    'primary_color_dark': '#333333',
    'secondary_color': '#eeeeee',
    'second_nav': True,
    'footer': False,
    'custom_css': 'site.css',
}
nbbuild_cell_timeout = 600

extensions += ['nbsite.gallery']

def gallery_spec(name):
    path = os.path.join('..', name, 'anaconda-project.yml')
    with open(path) as f:
        spec = yaml.safe_load(f)
    default = list(spec['commands'].values())[0]
    url_name = name.replace('_', '-')
    deployment_urls = [
            f'https://{url_name}.pyviz.demo.anaconda.com',
            f'https://{url_name}-notebooks.pyviz.demo.anaconda.com']
    description = spec['description']
    orphans = spec.get('orphans', [])
    if 'index.ipynb' in os.listdir(os.path.join('..', name)):
        description = f'`{description} <{name}/index.ipynb>`_'
        orphans.append('index.ipynb')
    return {
        'path': name,
        'description': description,
        'labels': spec.get('labels', []),
        'skip': spec.get('skip', False),
        'orphans': orphans,
        'deployment_urls': deployment_urls,
    }

DIR = os.getenv('DIR')
if DIR:
    projects = [DIR]
else:
    projects = sorted([f for f in next(os.walk('.'))[1] if f not in EXCLUDE])
    print('PROJECTS:', projects)

nbsite_gallery_conf = {
    'host': 'assets',
    'download_as': 'project',
    'examples_dir': '..',
    'default_extensions': ['*.ipynb'],
    'only_use_existing': DIR is None,
    'inline': True,
    'galleries': {
        '.': {
            'title': 'PyViz Topics Examples',
            'intro': long_description,
            'sections': [gallery_spec(project) for project in projects],
        }
    },
}

_NAV =  (
    ('Home', 'index'),
    ('User Guide', 'user_guide'),
    ('Making a New Project', 'make_project'),
    ('Maintenance', 'maintenance')
)

html_context.update({
    'PROJECT': project,
    'DESCRIPTION': description,
    'AUTHOR': authors,
    # WEBSITE_SERVER is optional for local or test deployments, but provides support for canonical URLs for full deployments
    'WEBSITE_SERVER': site,
    'VERSION': version,
    'GOOGLE_ANALYTICS_UA': 'UA-154795830-9',
    'NAV': _NAV,
    # by default, footer links are same as those in header
    'LINKS': _NAV,
    'SOCIAL': (
        ('Gitter', 'https://gitter.im/pyviz/pyviz'),
        ('Twitter', 'https://twitter.com/pyviz_org'),
        ('Github', 'https://github.com/pyviz-topics/examples'),
    )
})
