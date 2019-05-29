# -*- coding: utf-8 -*-
# flake8: noqa (hacky way of sharing config, etc...)

from nbsite.shared_conf import *

project = u'examples'
authors = u'PyViz Developers'
copyright = u'2019 ' + authors
description = 'Domain-specific narrative examples using multiple PyViz projects.'
site = 'https://{}.pyviz.org'.format(project)
version = release = '0.0.1'

html_static_path += ['_static']
html_theme = 'sphinx_pyviz_theme'
# logo file etc should be in html_static_path, e.g. _static
# only change colors in primary, primary_dark, and secondary
html_theme_options = {
#    'custom_css': 'site.css',
#    'logo': 'logo.png',
#    'favicon': 'favicon.ico',
#    'primary_color': 'coral',
#    'primary_color_dark': 'sienna',
#    'secondary_color': 'gold',
    'first_nav': False,
    'footer': False,
}

_NAV =  (
    ('Getting Started', 'getting_started/index'),
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
        ('Github', 'https://github.com/pyviz-topics/{}'.format(project)),
    )
})
