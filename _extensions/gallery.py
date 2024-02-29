import glob
import os

from pathlib import Path

import nbformat
import sphinx.util

logger = sphinx.util.logging.getLogger('gallery-extension')


INLINE_THUMBNAIL_TEMPLATE = """
    .. grid-item-card:: :doc:`{title} <{section_path}/{fname}>`
        :shadow: md

        .. image:: /{thumbnail}
            :alt: {title}
            :target: {section_path}/{fname}.html
            :class: extension-gallery-img
        ^^^
        {description}
        +++
{labels}

"""


DEFAULT_GALLERY_CONF = {
    'default_extensions': ['*.ipynb'],
    'examples_dir': os.path.join('..', 'examples'),
    'labels_dir': 'labels',
    'github_project': None,
    'intro': 'Sample intro',
    'title': 'A sample gallery title',
    'path': 'path_to_gallery',
    'sections': [
        {
            'path': 'path_to_section',
            'title': 'Sample Title',
            'description': 'A sample section description',
            'labels': [],
            'skip': [],
            'deployment_urls': []
        }
    ],
}


def sort_index_first(files):
    """
    Sort the files, putting 'index.ipynb' first.
    """
    files = files.copy()
    index_idx = None

    for i, file in enumerate(files):
        if os.path.basename(file) == 'index.ipynb':
            index_idx = i

    assert index_idx is not None, f'index.ipynb not found in {files}'

    sorted_files = [files.pop(index_idx)]
    sorted_files.extend(sorted(files))
    return sorted_files


def generate_project_toctree(files):
    toctree = '.. toctree::\n'
    toctree += '   :hidden:\n\n'
    for file in files:
        name = Path(file).stem
        if name == 'index':
            continue
        toctree += f'   {name}\n'
    return toctree


def insert_toctree(nb_path, toctree):
    nb = nbformat.read(nb_path, as_version=4)
    last_cell = nb['cells'][-1]
    toctree = "```{eval-rst}\n" + toctree + "\n```"
    toctree_cell = nbformat.v4.new_markdown_cell(source=toctree)
    if "```{eval-rst}" in last_cell['source']:
        nb['cells'][-1] = toctree_cell
    else:
        nb['cells'].append(toctree_cell)
    nbformat.write(nb, nb_path, version=nbformat.NO_CONVERT)


def generate_gallery(app):
    """
    Adapted from generate_gallery, tailored for the HoloViz examples site.
    """

    # Get config
    gallery_conf = app.config.gallery_conf
    extensions = gallery_conf['default_extensions']

    gallery_path = gallery_conf['path']

    # Get directories
    doc_dir = app.builder.srcdir
    examples_dir = os.path.join(doc_dir, gallery_conf['examples_dir'])
    if not '_static' in app.config.html_static_path:
        raise FileNotFoundError(
            'Gallery expects `html_static_path` to contain a "doc/_static/" '
            'folder, in which the labels will be looked up.'
        )
    static_dir = '_static'
    labels_dir = gallery_conf['labels_dir']
    labels_path = os.path.join(static_dir, labels_dir)

    sections = gallery_conf['sections']
    if not sections:
        raise ValueError('sections must be defined.')
    if sections and not all(isinstance(section, dict) for section in sections):
        raise TypeError('a sections must be defined as a dictionary.')

    # Main level display info
    title = gallery_conf['title']
    intro = gallery_conf['intro']

    # Start to write gallery index.rst

    # Page header
    gallery_rst = title + '\n' + '_'*len(title) + '\n'
    # Page intro
    if intro:
        gallery_rst += '\n' + intro + '\n'
    # Sphinx-design grid
    gallery_rst += '\n.. grid:: 2 2 4 4\n    :gutter: 3\n    :margin: 0\n'

    toctree_entries = []

    for section in sections:
        section_path = section['path']
        if not 'path' in section or not section['path']:
            raise ValueError('Missing or empty path value in section definition')
        section_title = section.get('title', section['path'])
        description = section.get('description', None)
        labels = section.get('labels', [])
        skip = section.get('skip', [])

        dest_dir = os.path.join(doc_dir, gallery_path, section_path)

        # Collect examples
        files = []
        for extension in extensions:
            files += glob.glob(os.path.join(dest_dir, extension))
        if skip:
            files = [f for f in files if os.path.basename(f) not in skip]
        
        if not files:
            raise ValueError(f'No files found in section {section_path}')
        
        if len(files) > 1:
            if not any(os.path.basename(file) == 'index.ipynb' for file in files):
                logger.warning(
                    '%s has multiple files but no "index.ipynb", skipping it entirely',
                    section_title,
                )
                continue
            files = sort_index_first(files)

        logger.info(f"building gallery... {section_title}: {len(files)} files")

        basenames = []
        for f in files:

            extension = f.split('.')[-1]
            basename = os.path.basename(f)[:-(len(extension)+1)]
            basenames.append(basename)

            # Generate a card only for the index
            if len(files) > 1 and basename != 'index':
                continue

            thumb_dir = os.path.join(dest_dir, 'thumbnails')
            if not os.path.isdir(thumb_dir):
                os.makedirs(thumb_dir)
            thumb_path = os.path.join(thumb_dir, '%s.png' % basename)

            # Try existing file
            if not os.path.isfile(thumb_path):
                logger.warning(f'Notebook {f} has no thumbnail.')
                continue

            labels_str = ''
            for label in labels:
                label_svg = os.path.join(labels_path, f'{label}.svg')
                if not os.path.exists(os.path.join(doc_dir, label_svg)):
                    raise FileNotFoundError(
                        f'Label {label!r} must have an SVG file in {labels_path}'
                    )
                # Prepend / to make it an "absolute" path from the root folder.
                label_svg = '/' + label_svg
                labels_str += ' ' * 8 + f'.. image:: {label_svg}\n'

            # Description with new lines break the grid
            description = ' '.join(description.splitlines())

            # Generate the card rst
            this_entry = INLINE_THUMBNAIL_TEMPLATE.format(
                title=section_title, section_path=section_path, fname=basename,
                description=description, thumbnail=thumb_path,
                labels=labels_str,
            )
            gallery_rst += this_entry

        if len(files) > 1:
            index_nb = next(file for file in files if file.endswith('index.ipynb'))
            project_toctree = generate_project_toctree(files)
            insert_toctree(index_nb, project_toctree)

        # Gallery toctree: just put the index file or the only notebook available.
        target = 'index' if 'index' in basenames else basenames[0]
        toctree_entries.append(f'{section_title} <{section_path}/{target}>')

    # Add gallery toctree
    assert toctree_entries, 'Empty toctree entries.'
    toctree_rst = '.. toctree::\n   :hidden:\n\n'
    for toctree_entry in toctree_entries:
        toctree_entry = 'self' if toctree_entry == 'index' else toctree_entry
        toctree_rst += f'   {toctree_entry}\n'

    gallery_rst += toctree_rst

    with open(os.path.join(doc_dir, gallery_path, 'index.rst'), 'w') as f:
        f.write(gallery_rst)


def generate_gallery_rst(app):
    """
    Adapted from generate_gallery_rst to build the HoloViz examples site.
    """
    if DEFAULT_GALLERY_CONF == app.config.gallery_conf:
        return
    logger.info('generating gallery...', color='white')
    gallery_conf = dict(DEFAULT_GALLERY_CONF, **app.config.gallery_conf)

    # this assures I can call the config in other places
    app.config.gallery_conf = gallery_conf
    generate_gallery(app)


def setup(app):
    app.add_config_value('gallery_conf', DEFAULT_GALLERY_CONF, 'html')
    app.connect('builder-inited', generate_gallery_rst)
    metadata = {'parallel_read_safe': True,
                'version': '0.0.1'}
    return metadata
