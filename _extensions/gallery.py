import os
import yaml
import glob
from pathlib import Path
import nbformat
import sphinx.util
from collections import OrderedDict
import re

logger = sphinx.util.logging.getLogger('category-gallery-extension')

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

INLINE_THUMBNAIL_TEMPLATE = """
    .. grid-item-card:: :doc:`{title} <{section_path}>`
        :shadow: md

        .. image:: /{thumbnail}
            :alt: {title}
            :target: {section_path}.html
            :class: extension-gallery-img
        ^^^
        {description}
        +++
{labels}

"""

INLINE_THUMBNAIL_TEMPLATE_SEE_MORE = """
    .. grid-item-card:: :doc:`See More <{category_path}>`
        :shadow: md

        {category} projects
"""

CATNAME_TO_CAT_MAP = OrderedDict({
    '⭐ Featured': ['Featured'],
    'Geospatial': ['Geospatial'],
    'Life Sciences': ['Life Sciences'],
    'Finance and Economics': ['Finance', 'Economics'],
    'Mathematics': ['Mathematics'],
    'Cybersecurity': ['Cybersecurity'],
    'Neuroscience': ['Neuroscience'],
    'Sports': ['Sports'],
    # 'No Category':[],
})

CAT_TO_CATNAME_MAP = {category: catname
                      for catname, categories in CATNAME_TO_CAT_MAP.items()
                      for category in categories}

ALL_VALID_CATEGORIES = set(CAT_TO_CATNAME_MAP.keys())

def load_tag_mapping(srcdir):
    with open(os.path.join(srcdir, 'tags.yml'), 'r') as file:
        return yaml.safe_load(file)

def sort_index_first(files):
    files = files.copy()
    index_idx = None

    for i, file in enumerate(files):
        if os.path.basename(file) == 'index.ipynb':
            index_idx = i

    assert index_idx is not None, f'index.ipynb not found in {files}'

    sorted_files = [files.pop(index_idx)]
    sorted_files.extend(sorted(files))
    return sorted_files

def clean_description(description):
    return ' '.join(description.splitlines())

def clean_category_name(category_name):
    # remove any emoji's and or leading whitespace
    return re.sub(r'[^a-zA-Z0-9\s]', '', category_name).strip().lower().replace(" ", "_")

def get_labels_path(app):
    doc_dir = app.builder.srcdir
    gallery_conf = app.config.gallery_conf
    if not '_static' in app.config.html_static_path:
        raise FileNotFoundError(
            'Gallery expects `html_static_path` to contain a "doc/_static/" '
            'folder, in which the labels will be looked up.'
        )
    static_dir = os.path.join(doc_dir, '_static')
    labels_dir = gallery_conf['labels_dir']
    return os.path.join(static_dir, labels_dir)

def generate_labels_rst(labels_path, labels):
    labels_str = ''
    for label in labels:
        label_svg = os.path.join(labels_path, f'{label}.svg')
        if not os.path.exists(label_svg):
            raise FileNotFoundError(
                f'Label {label!r} must have an SVG file in {labels_path}'
            )
        # Prepend / to make it an "absolute" path from the root folder.
        label_svg = '/' + label_svg
        labels_str += ' ' * 8 + f'.. image:: {label_svg}\n'
    return labels_str

def generate_card_grid(app, rst, projects, labels_path):
    rst += '\n.. grid:: 2 2 4 4\n    :gutter: 3\n    :margin: 0\n'
    toctree_entries=[]
    for section in projects:
        project_path = section['path']
        title = section['title']
        description = clean_description(section['description'])
        
        doc_dir = app.builder.srcdir
        gallery_path = app.config.gallery_conf['path']
        gallery_project_path = os.path.join(doc_dir, gallery_path, project_path)
        files = glob.glob(os.path.join(gallery_project_path, '*.ipynb'))

        if len(files) > 1:
            if 'index.ipynb' in [os.path.basename(f) for f in files]:
                main_file = 'index'
                thumb_path = os.path.join(gallery_path, project_path, 'thumbnails', 'index.png')
                files = sort_index_first(files)
            else:
                logger.warning(
                    '%s has multiple files but no "index.ipynb", skipping it entirely',
                    title,
                )                    
                continue
        else:
            main_file = Path(files[0]).stem
            thumb_path = os.path.join(gallery_path, project_path, 'thumbnails', f'{main_file}.png')

        if not os.path.isfile(os.path.join(doc_dir, thumb_path)):
            logger.warning(f"Thumbnail not found for {project_path}, skipping.")
            continue  # Skip if thumbnail doesn't exist

        labels_str = generate_labels_rst(labels_path, section['labels'])

        # main_file_path = os.path.join('../', project_path, main_file)
        main_file_path = os.path.join(project_path, main_file)
        rst += INLINE_THUMBNAIL_TEMPLATE.format(
            title=title, section_path=main_file_path,
            description=description, thumbnail=thumb_path,
            labels=labels_str,
        )
        toctree_entries.append(f'{title} <{main_file_path}>')
    return rst, toctree_entries

def generate_toctree(entries, hidden=True):
    if hidden:
        toctree = '.. toctree::\n'
        toctree += '   :hidden:\n\n'
    else:
        toctree = '.. toctree::\n\n'
    for entry in entries:
        toctree += f'   {entry}\n'
    return toctree

def generate_galleries(app):
    TAG_MAPPING = load_tag_mapping(app.builder.srcdir)
    gallery_conf = app.config.gallery_conf

    labels_path = get_labels_path(app)
    # Create category pages
    category_projects = {}
    for section in gallery_conf['sections']:
        project = section['path']
        info = TAG_MAPPING.get(project, {})
        categories = info.get('category', [])
        for category in categories:
            if category not in ALL_VALID_CATEGORIES:
                raise ValueError(f"Invalid category '{category}' found in project '{project}'.")
            # add this section to the list for each catname
            catname = CAT_TO_CATNAME_MAP[category]
            if catname not in category_projects:
                category_projects[catname] = []
            category_projects[catname].append(section)

    for category in CATNAME_TO_CAT_MAP:
        projects = category_projects.get(category, [])
        generate_category_page(app, category, projects, labels_path)

    # Create main index.rst for gallery
    generate_gallery_index(app, category_projects, labels_path)

def generate_category_page(app, category, projects, labels_path):
    # Main Header
    rst = category + '\n' + '_'*len(category)*3 + '\n'

    # Insert category page overview if exists
    category_file_path = os.path.join(app.builder.srcdir, 'category_descriptions', f'{clean_category_name(category)}.rst')
    if os.path.exists(category_file_path):
        with open(category_file_path, 'r') as file:
            rst += '\n' + file.read() + '\n\n'
    else:
        rst += f'\n{category} Projects\n'

    if projects:
        # Gallery Cards
        rst, toctree_entries = generate_card_grid(app, rst, projects, labels_path)
        rst += generate_toctree(toctree_entries)

    with open(os.path.join(app.builder.srcdir,
                           app.config.gallery_conf['path'],
                           f'{clean_category_name(category)}.rst'),
                           'w') as f:
        f.write(rst)

def generate_label_buttons(labels):
    buttons_html = '\n\n<div id="label-filters-container">\n'
    buttons_html += '  <div class="filter-label">Filter by label:</div>\n'
    buttons_html += '  <div id="label-filters" class="filter-box">\n'
    for label in labels:
        buttons_html += f'    <button class="filter-btn" data-label="{label}">{label}</button>\n'
    buttons_html += '  </div>\n</div>\n'
    return buttons_html

def generate_gallery_index(app, category_projects, labels_path):
    # Main Header
    gallery_conf = app.config.gallery_conf
    title = gallery_conf['title']
    rst = title + '\n' + '_'*len(title)*3 + '\n'

    # Overview
    INTRO = os.path.join(app.builder.srcdir, f'intro.rst')
    with open(INTRO, 'r') as file:
        rst += '\n' + file.read() + '\n\n'

    # Label Filter Buttons
    all_labels = set()
    for sections in category_projects.values():
        for section in sections:
            all_labels.update(section['labels'])
    label_buttons_html = generate_label_buttons(all_labels)
    
    # Insert the label buttons using raw:: html
    rst += '\n.. raw:: html\n\n'
    for line in label_buttons_html.splitlines():
        rst += f'   {line}\n'
    rst += '\n'

    # Gallery Cards per category
    toctree_entries = []
    for category in CATNAME_TO_CAT_MAP:
        category_link = f'{clean_category_name(category)}'
        rst += f'\n`{category} <{category_link}.html>`_\n' + '-'*len(category) + '\n\n'

        projects = category_projects.get(category, [])
        if not projects:
            continue
        
        rst, _ = generate_card_grid(app, rst, projects, labels_path)
        rst += '\n\n'

        toctree_entries.append(f'{category} <{category_link}>')

    rst += generate_toctree(toctree_entries)

    with open(os.path.join(app.builder.srcdir,
                           app.config.gallery_conf['path'],
                           'index.rst'),
                           'w') as f:
        f.write(rst)

def generate_gallery_rst(app):
    if DEFAULT_GALLERY_CONF == app.config.gallery_conf:
        return
    logger.info('generating gallery...', color='white')
    gallery_conf = dict(DEFAULT_GALLERY_CONF, **app.config.gallery_conf)

    # this assures I can call the config in other places
    app.config.gallery_conf = gallery_conf
    generate_galleries(app)

def setup(app):
    app.add_config_value('gallery_conf', DEFAULT_GALLERY_CONF, 'html')
    app.connect('builder-inited', generate_gallery_rst)
    metadata = {'parallel_read_safe': True,
                'version': '0.0.1'}
    return metadata
