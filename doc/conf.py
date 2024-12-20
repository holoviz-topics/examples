# -*- coding: utf-8 -*-
import os
import pathlib
import sys

import yaml

from nbsite.shared_conf import *

# To reuse utilities in dodo.py
sys.path.insert(0, '..')

# To import the local sphinx extension
sys.path.insert(0, os.path.abspath("../_extensions"))

from dodo import (
    all_project_names, deployment_cmd_to_endpoint, last_commit_date,
    projname_to_title, find_notebooks, DEFAULT_DOC_EXCLUDE
)

project = 'Examples'
authors = 'HoloViz Developers'
copyright = '2023 ' + authors
description = 'Domain-specific narrative examples using multiple open-source Python visualization tools.'
long_description = ('Home for domain-specific narrative examples using '
                    'multiple HoloViz projects. Each project is isolated '
                    'and fully described. For information on how to use '
                    'these projects, see how to `get started <getting_started.html>`_. '
                    'We encourage new contributors to add their own examples, '
                    'providing a valuable opportunity to learn the HoloViz tools '
                    'and contribute to the open-source community, benefiting '
                    'other users.')
site = 'https://examples.holoviz.org'
version = release = '0.1.0'

html_static_path += ['_static']
html_theme = 'pydata_sphinx_theme'
html_logo = "_static/holoviz-logo-unstacked.svg"
html_favicon = "_static/favicon.ico"

html_css_files += [
    'css/custom.css',
    'css/header.css',
]

templates_path.insert(0, '_templates')

# Don't copy the sources (notebook files) in builtdocs/_sources, they're heavy.
html_copy_source = False

# Hide the side bar on the gallery page
# html_sidebars = {
#   "gallery/index": [],
# }

extensions = [
    'gallery',  # local gallery extension
    'nbheader',  # local nbheader extension
    'myst_nb',
    'sphinx_design',
    'sphinx_copybutton',
    'nbsite.analytics',
    'nbsite.nb_interactivity_warning',
    'sphinxext.rediraffe',
]

# Turn off myst-nb execute (should not be required, but who knows!)
nb_execution_mode = 'off'

myst_enable_extensions = [
    # MySt-Parser will attempt to convert any isolated img tags (i.e. not
    # wrapped in any other HTML) to the internal representation used in sphinx.
    'html_image',
    # To render math expressions like $y' = f( x, y )$
    'dollarmath',
    # To render Latex math expressions
    'amsmath',
]

nbsite_analytics = {
    'goatcounter_holoviz': True,
}

# The `download` role indicates Sphinx to grab the file and put it in a _downloads folder,
# and in a hashed subfolder to prevent collisions.
# Some CSS was required to style it as it looked a little weird.

def gallery_spec(name):
    path = os.path.join('..', name, 'anaconda-project.yml')
    with open(path) as f:
        spec = yaml.safe_load(f)
    title = projname_to_title(spec['name'])
    description = spec['description']
    # Examples specific spec.
    # TODO: isn't optional
    examples_config = spec.get('examples_config', {})
    # TODO: isn't optional
    categories = examples_config.get('categories', [])
    # TODO: isn't optional
    labels = examples_config.get('labels', [])
    # labels always lower cased on the website
    labels = list(map(str.lower, labels))
    created = examples_config.get('created', 'NA')
    authors = examples_config['maintainers']
    # Optional, computed if not provided.
    last_updated = examples_config.get('last_updated', '')
    if not last_updated:
        last_updated = last_commit_date(name, root='..', verbose=False)
    title = examples_config.get('title', '') or projname_to_title(spec['name'])
    deployments = examples_config.get('deployments', [])
    skip = examples_config.get('skip', False)

    actions = []
    for depl in deployments:
        if depl['command'] == 'notebook':
            url = deployment_cmd_to_endpoint(depl['command'], name)
            if any(nb_file.stem == 'index' for nb_file in pathlib.Path('..', name).glob('*.ipynb')):
                nb_name = 'index'
            else:
                nb_name = name
            url += f'/notebooks/{nb_name}.ipynb'
        elif depl['command'] == 'dashboard':
            url = deployment_cmd_to_endpoint(depl['command'], name)
        actions.append({
            'command': depl['command'],
            'url': url,
        })

    return {
        'path': name,
        'title': title,
        'description': description,
        'actions': actions,
        'labels': labels,
        'header': {
            'authors': authors,
            'created': created,
            'last_updated': last_updated,
            'deployments': deployments,
        },
        'skip': skip,
        'last_updated': last_updated,
        'categories': categories,
    }

SINGLE_PROJECT = os.getenv('EXAMPLES_HOLOVIZ_DOC_ONE_PROJECT')
all_projects = all_project_names(root='gallery', exclude=DEFAULT_DOC_EXCLUDE)

exclude_patterns = [
    'category_descriptions',
    'intro.md',
]

# Only build the projects found in doc/
projects = [SINGLE_PROJECT] if SINGLE_PROJECT else all_projects

if SINGLE_PROJECT:
    # Tell Sphinx to ignore other projects if they are already in doc/
    exclude_patterns.extend([
        os.path.join('gallery', project) + '*'
        for project in all_projects
        if project != SINGLE_PROJECT
    ])

print('Project(s) that will be built:', projects)

gallery_conf = {
    'github_org': 'holoviz-topics',
    'github_project': 'examples',
    'examples_dir': '..',
    'default_extensions': ['*.ipynb'],
    'path': 'gallery',
    'intro': long_description,
    'sections': [gallery_spec(project) for project in projects],
}

def root_and_gallery_index_redirects():
    """
    The projects were originally (pyviz era) at the root, e.g. examples.pyviz.org/attractors/attractors.html
    At the time, redirects were implemented to allow shorter URLs like examples.pyviz.org/attractors(/).
    Projects are now under the /gallery folder, because otherwise they would all
    end up being displayed in the navbar, as the PyData Sphinx Theme displays the
    top-level toctree in the navbar. The first goal of this function is to
    generate these redirects to preserve these old links:
    examples.holoviz.org/attractors(/) -> examples.holoviz.org/gallery/attractors/attractors.html

    For mono-notebook projects (the majority), links like examples.pyviz.org/gallery/boids(/)
    don't redirect by default to examples.pyviz.org/gallery/boids/boids.html.
    The second goal of the function is to enable this by creating this redirect link:
    examples.holoviz.org/gallery/boids/index -> examples.holoviz.org/gallery/boids/boids
    Which whill enable examples.holoviz.org/gallery/boids(/)
    """
    redirects = {}
    for project in projects:
        notebooks = find_notebooks(project, root='..')
        nbstems = [nb.stem for nb in notebooks]
        if 'index' in nbstems:
            index = 'index'
        elif len(nbstems) == 1:
            index = nbstems[0]
        else:
            raise RuntimeError(f'Too many notebooks found: {nbstems}')
        redirects[f'{project}/index'] = f'gallery/{project}/{index}'
        if index != 'index':
            # Projects with an index notebook don't need the redirect
            redirects[f'gallery/{project}/index'] = f'gallery/{project}/{index}'
    return redirects

top_level_redirects = {
    # For the transition between examples.pyviz.org and examples.holoviz.org
    'user_guide': 'getting_started',
    'make_project': 'contributing',
    'maintenance' : 'index',
}

# Redirects from e.g. examples.holoviz.org/attractors/attractors to examples.holoviz.org/gallery/attractors/attractors
# since projects have been moved to /gallery (to avoid being at the top level and affecting the top-level toctree)
project_direct_links = {
    ## Direct links (examples moved to /gallery)
    'attractors/attractors': 'gallery/attractors/attractors',
    'attractors/attractors_panel': 'gallery/attractors/attractors_panel',
    'attractors/clifford_panel': 'gallery/attractors/clifford_panel',
    'bay_trimesh/bay_trimesh': 'gallery/bay_trimesh/bay_trimesh',
    'boids/boids': 'gallery/boids/boids',
    'carbon_flux/carbon_flux': 'gallery/carbon_flux/carbon_flux',
    'census/census': 'gallery/census/census',
    'datashader_dashboard/dashboard': 'gallery/datashader_dashboard/datashader_dashboard',
    'euler/euler': 'gallery/euler/euler',
    'exoplanets/exoplanets': 'gallery/exoplanets/exoplanets',
    'gapminders/gapminders': 'gallery/gapminders/gapminders',
    'gerrymandering/gerrymandering': 'gallery/gerrymandering/gerrymandering',
    'glaciers/glaciers': 'gallery/glaciers/glaciers',
    'gull_tracking/gull_tracking': 'gallery/gull_tracking/gull_tracking',
    'heat_and_trees/Heat_and_Trees': 'gallery/heat_and_trees/heat_and_trees',
    'hipster_dynamics/hipster_dynamics': 'gallery/hipster_dynamics/hipster_dynamics',
    'iex_trading/IEX_stocks': 'gallery/iex_trading/IEX_stocks',
    'iex_trading/IEX_trading': 'gallery/iex_trading/IEX_trading',
    'landsat/landsat': 'gallery/landsat/landsat',
    'landsat_clustering/landsat_clustering': 'gallery/landsat_clustering/landsat_clustering',
    'landuse_classification/Image_Classification': 'gallery/landuse_classification/landuse_classification',
    'lsystems/lsystems': 'gallery/lsystems/lsystems',
    'ml_annotators/ml_annotators': 'gallery/ml_annotators/ml_annotators',
    'network_packets/network_packets': 'gallery/network_packets/network_packets',
    'nyc_buildings/nyc_buildings': 'gallery/nyc_buildings/nyc_buildings',
    'nyc_taxi/dashboard': 'gallery/nyc_taxi/dashboard',
    'nyc_taxi/nyc_taxi-nongeo': 'gallery/nyc_taxi/nyc_taxi-nongeo',
    'nyc_taxi/nyc_taxi': 'gallery/nyc_taxi/nyc_taxi',
    'opensky/opensky': 'gallery/opensky/opensky',
    'osm/osm-1billion': 'gallery/osm/osm-1billion',
    'osm/osm-3billion': 'gallery/osm/osm-3billion',
    'penguin_crossfilter/penguin_crossfilter': 'gallery/penguin_crossfilter/penguin_crossfilter',
    'portfolio_optimizer/portfolio': 'gallery/portfolio_optimizer/portfolio_optimizer',
    'seattle_lidar/Seattle_Lidar': 'gallery/seattle_lidar/seattle_lidar',
    'ship_traffic/ship_traffic': 'gallery/ship_traffic/ship_traffic',
    'square_limit/square_limit': 'gallery/square_limit/square_limit',
    'sri_model/sri_model': 'gallery/sri_model/sri_model',
    'uk_researchers/uk_researchers': 'gallery/uk_researchers/uk_researchers',
    'walker_lake/walker_Lake': 'gallery/walker_lake/walker_lake',
}

if SINGLE_PROJECT:
    project_direct_links = {
        k: v
        for k, v in project_direct_links.items()
        if k.split('/')[0] == SINGLE_PROJECT
    }

rediraffe_redirects = {
    **top_level_redirects,
    **project_direct_links,
    # Links from e.g. /attractors to /gallery/attractors/index.html
    # And from e.g. /gallery/boids/index.html to /gallery/boids/boids.html
    **root_and_gallery_index_redirects(),
}

html_context.update({
    "last_release": f"v{release}",
    "github_user": "holoviz-topics",
    "github_repo": "examples",
    "default_mode": "light"
})

html_theme_options = {
    "github_url": "https://github.com/holoviz-topics/examples",
    "icon_links": [
        {
            "name": "Twitter",
            "url": "https://twitter.com/holoviz_org",
            "icon": "fab fa-twitter-square",
        },
        {
            "name": "Forum",
            "url": "https://discourse.holoviz.org/",
            "icon": "fab fa-discourse",
        },
        {
            "name": "Discord",
            "url": "https://discord.gg/UXdtYyGVQX",
            "icon": "fa-brands fa-discord",
        },
    ],
    "footer_start": [
        "copyright",
        "last-updated",
    ],
    "navbar_end": ["navbar-icon-links"],
    "secondary_sidebar_items": {
        "**": ["page-toc"],
        "gallery/index": [],
    },
}


def add_filter_js_gallery_index(app, pagename, templatename, context, doctree):
    # Only add filter.js to the gallery index page
    if pagename != "gallery/index":
        return
    app.add_js_file("js/filter.js")

def setup(app):
    from nbsite import nbbuild
    nbbuild.setup(app)

    app.connect("builder-inited", remove_mystnb_static)
    app.connect("html-page-context", add_filter_js_gallery_index)

    # hv_sidebar_dropdown
    app.add_config_value('nbsite_hv_sidebar_dropdown', {}, 'html')
    app.connect("html-page-context", add_hv_sidebar_dropdown_context)
