# -*- coding: utf-8 -*-
import glob
import os
import sys

import yaml

from nbsite.shared_conf import *

# To reuse utilities in dodo.py
sys.path.insert(0, '..')

from dodo import (
    all_project_names, deployment_cmd_to_endpoint, last_commit_date,
    projname_to_servername, projname_to_title, DEFAULT_DOC_EXCLUDE
)

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

# Turn off myst-nb execute (should not be required, but who knows!)
nb_execution_mode = 'off'

PROLOG_TEMPLATE = """
.. grid:: 1 1 1 2
   :outline:
   :padding: 2
   :margin: 2 4 2 2
   :class-container: sd-rounded-1

   .. grid-item::
      :columns: 12
      :margin: 0
      :padding: 0

      .. grid:: 1 1 1 2
         :margin: 0
         :padding: 1

         .. grid-item::
            :columns: auto
            :class: nbsite-metadata

            :material-outlined:`person;24px` {authors}

         .. grid-item::
            :columns: auto
            :class: nbsite-metadata

            :material-outlined:`event;24px` {created} (Last Updated: {last_updated})

   .. grid-item::
      :columns: 12
      :margin: 0
      :padding: 0

      .. grid:: 1 1 1 3
         :margin: 0
         :padding: 1

         .. grid-item::
            :columns: auto
            :class: nbsite-metadata

            :material-outlined:`download;24px` `Download project <../assets/_archives/{projectname}.zip>`_

{deployments}

"""

# Tried using the `download` role, with which Sphinx handles entirely the files to download.
# It grabs them and puts them in a _downloads folder, with a hash to prevent collisions.
# However the link was styled in a weird way (`downloads` not handled by the PyData Sphinx Theme?)
# Keeping that trick around as it is how it should be done, assuming the archives is in doc/projname/
# :download:`Download project <{projectname}.zip>`

AUTHOR_TEMPLATE = '`{author} <https://github.com/{author}>`_'
DEPLOYMENT_TEMPLATE = """
         .. grid-item::
            :columns: auto
            :class: nbsite-metadata

            :material-outlined:`{material_icon};24px` `{text} <{endpoint}>`_
"""

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
    labels = examples_config.get('labels', [])
    # TODO: isn't optional
    created = examples_config.get('created', 'NA')
    # TODO: isn't optional
    authors = examples_config.get('maintainers', '')
    # TODO: is optional, if not provided is computed
    last_updated = examples_config.get('last_updated', '')
    if not last_updated:
        last_updated = last_commit_date(name, root='..', verbose=False)
    deployments = examples_config.get('deployments', '')

    if authors:
        authors = [AUTHOR_TEMPLATE.format(author=author) for author in authors]
        authors = ', '.join(authors)

    if deployments:
        _formatted_deployments = []
        for depl in deployments:
            if depl['command'] == 'notebook':
                text = 'Run notebook'
                material_icon = 'smart_display'
                endpoint = deployment_cmd_to_endpoint(depl['command'], name)
                # nbsite will look for "/notebooks/{template_notebook_filename}"
                # and replace {template_notebook_filename} by the notebook
                # filename where the metadata prolog is injected.
                endpoint += '/notebooks/{template_notebook_filename}'
            elif depl['command'] == 'dashboard':
                text = 'Open app'
                material_icon = 'dashboard'
                endpoint = deployment_cmd_to_endpoint(depl['command'], name)
            formatted_depl = DEPLOYMENT_TEMPLATE.format(
                text=text, material_icon=material_icon, endpoint=endpoint
            )
            _formatted_deployments.append(formatted_depl)
        deployments = '\n\n'.join(_formatted_deployments)

    prolog = PROLOG_TEMPLATE.format(
        created=created, authors=authors, last_updated=last_updated,
        projectname=name, deployments=deployments,
    )

    skip = examples_config.get('skip', False)
    
    return {
        'path': name,
        'title': title,
        'description': description,
        'labels': labels,
        'prolog': prolog,
        'skip': skip,
    }

# Only build the projects found in doc/
projects = all_project_names(root='.', exclude=DEFAULT_DOC_EXCLUDE)
print('Projects that will be built:', projects)

nbsite_gallery_inlined_conf = {
    'github_org': 'pyviz-topics',
    'github_project': 'examples',
    'examples_dir': '..',
    'alternative_toctree': ['user_guide', 'make_project', 'maintenance'],
    'default_extensions': ['*.ipynb'],
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
