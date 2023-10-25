import glob
import os

from pathlib import Path

import nbformat
import sphinx.util

logger = sphinx.util.logging.getLogger('nbheader-extension')


def insert_prolog(nb_path, prolog):
    nb = nbformat.read(nb_path, as_version=4)
    first_cell = nb['cells'][0]
    prolog = "```{eval-rst}\n" + prolog + "\n```"
    prolog_cell = nbformat.v4.new_markdown_cell(source=prolog)
    if "```{eval-rst}" in first_cell:
        nb['cells'][0] = prolog_cell
    else:
        nb['cells'].insert(0, prolog_cell)
    nbformat.write(nb, nb_path, version=nbformat.NO_CONVERT)


def add_nbheader(app):
    """
    This if for now re-using gallery_conf from the gallery extensions.
    Configurations could be decoupled if need be.
    """

    logger.info('Adding notebook headers...', color='white')

    # Get config
    gallery_conf = app.config.gallery_conf
    sections = gallery_conf['sections']
    doc_dir = Path(app.builder.srcdir)
    gallery_path = doc_dir / gallery_conf['path']
    for section in sections:
        prolog = section['prolog']
        project_path = gallery_path / section['path']
        nb_files = glob.glob(os.path.join(project_path, '*.ipynb'))
        for nb_file in nb_files:
            nb_file = Path(nb_file)
            # Used by examples.holoviz.org to link to the viewed notebook
            nb_prolog = prolog
            if '/notebooks/{template_notebook_filename}' in prolog:
                nb_prolog = prolog.format(
                    template_notebook_filename=nb_file.name,
                )
            insert_prolog(nb_file, nb_prolog)


def setup(app):
    app.connect('builder-inited', add_nbheader)
    metadata = {'parallel_read_safe': True,
                'version': '0.0.1'}
    return metadata
