# -*- coding: utf-8 -*-
from nbsite.shared_conf import *
import os
import glob

project = u'Examples'
authors = u'PyViz Developers'
copyright = u'2019 ' + authors
description = 'Domain-specific narrative examples using multiple PyViz projects.'
site = 'https://examples.pyviz.org'
version = release = '0.0.1'

html_static_path += ['_static']
html_theme = 'sphinx_pyviz_theme'
# logo file etc should be in html_static_path, e.g. _static
# only change colors in primary, primary_dark, and secondary
html_theme_options = {
    'logo': 'logo.png',
    'favicon': 'favicon.ico',
    'primary_color': '#295e62',
    'primary_color_dark': '#1c4648',
    'secondary_color': '#d5d46f',
    'second_nav': True,
    'footer': False,
}

extensions += ['nbsite.gallery']

DEFAULT_EXCLUDE = ['doc', 'envs', 'test_data', 'builtdocs', *glob.glob( '.*'), *glob.glob( '_*')]
PROJECTS_EXCLUDE = ['landsat', 'osm', 'simulation', 'nyc_taxi',
                    'gerrymandering', 'uk_researchers',
                    'census', 'geometry', 'opensky']

DIR = os.getenv('DIR')
if DIR:
    sections = [DIR]
else:
    sections = [f for f in next(os.walk('.'))[1] if f not in DEFAULT_EXCLUDE + PROJECTS_EXCLUDE]

## TODO, in each job, populate one of these, save the doc dir, zip self. Then in the last stage have them all in there.
# {'path': 'foo',
#  'title': 'Foo',
#  'description': 'A set of sophisticated apps built to demonstrate the features of Panel.'},
# {'path': 'bay_trimesh',
#  'title': 'Bay',
#  'description': 'A set of sophisticated apps built to demonstrate the features of Panel.'},
# {'path': 'attractors',
#  'title': 'Attractors',
#  'description': 'A set of sophisticated apps built to demonstrate the features of Panel.'},

nbsite_gallery_conf = {
    'github_org': 'pyviz-topics',
    'github_project': 'examples',
    'examples_dir': '..',
    'default_extensions': ['*.ipynb'],
    'thumbnail_size': (600, 400),
    'galleries': {
        '.': {
            'title': 'Pyviz Topics Examples',
            'sections': sections,
        }
    },
    'thumbnail_url': 'https://assets.holoviews.org/panel/thumbnails',
    'deployment_url': 'https://panel-gallery.pyviz.demo.anaconda.com/'
}

_NAV =  (
    ('Home', 'index'),
    ('Getting Started', 'getting_started'),
    ('Developer Guide', 'developer_guide'),
    ('Downloads', 'downloads'),
    ('About', 'about')
)

html_context.update({
    'PROJECT': project,
    'DESCRIPTION': description,
    'AUTHOR': authors,
    # will work without this - for canonical (so can ignore when building locally or test deploying)
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
