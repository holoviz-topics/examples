# -*- coding: utf-8 -*-
from nbsite.shared_conf import *
import os
import glob
import yaml

EXCLUDE = ['assets', *glob.glob( '.*'), *glob.glob( '_*')]

project = u'Examples'
authors = u'PyViz Developers'
copyright = u'2019 ' + authors
description = 'Domain-specific narrative examples using multiple PyViz projects.'
long_description = ('Home for domain-specific narrative examples using '
                    'multiple PyViz projects. Each project is isolated and '
                    'fully described: runnable locally and deployable to '
                    'Anaconda Enterprise.')
site = 'https://examples.pyviz.org'
version = release = '0.0.1'

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
    'custom_css': 'custom.css'
}
nbbuild_cell_timeout = 600

extensions += ['nbsite.gallery']

def gallery_spec(name):
    path = os.path.join('..', name, 'anaconda-project.yml')
    with open(path) as f:
        spec = yaml.safe_load(f)
    return {
        'path': name,
        'description': spec['description'],
        'deployment_url': 'https://{}.pyviz.demo.anaconda.com/'.format(name.replace('_', '-'))
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
    'galleries': {
        '.': {
            'title': 'Pyviz Topics Examples',
            'intro': long_description,
            'sections': [gallery_spec(project) for project in projects],
        }
    },
    'thumbnail_url': 'http://datashader.org/assets/images/thumbnails',
}

_NAV =  (
    ('Home', 'index'),
    ('Getting Started', 'getting_started'),
    ('Developer Guide', 'developer_guide'),
    ('About', 'about')
)

html_context.update({
    'PROJECT': project,
    'DESCRIPTION': description,
    'AUTHOR': authors,
    # WEBSITE_SERVER is optional for local or test deployments, but provides support for canonical URLs for full deployments
    'WEBSITE_SERVER': site,
    'VERSION': version,
    'NAV': _NAV,
    # by default, footer links are same as those in header
    'LINKS': _NAV,
    'SOCIAL': (
        ('Gitter', 'https://gitter.im/pyviz/pyviz'),
        ('Twitter', 'https://twitter.com/pyviz_org'),
        ('Github', 'https://github.com/pyviz-topics/examples'),
    )
})
