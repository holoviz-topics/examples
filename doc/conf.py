# -*- coding: utf-8 -*-
from nbsite.shared_conf import *

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
    'logo': 'pyviz-logo.png',
    'favicon': 'favicon.ico',
    'primary_color': '#295e62',
    'primary_color_dark': '#1c4648',
    'secondary_color': '#d5d46f',
    'second_nav': True,
    'footer': False,
}

_NAV =  (
    ('Home', 'gallery'),
    ('Getting Started', 'index'),
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
