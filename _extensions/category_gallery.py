import os
import yaml
import glob
from pathlib import Path
import nbformat
import sphinx.util

logger = sphinx.util.logging.getLogger('category-gallery-extension')

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

def generate_category_galleries(app):
    TAG_MAPPING = load_tag_mapping(app.builder.srcdir)
    gallery_conf = app.config.gallery_conf

    doc_dir = app.builder.srcdir
    categories_dir = os.path.join(doc_dir, 'category_gallery')
    if not os.path.exists(categories_dir):
        os.makedirs(categories_dir)

    # Ensure _static path is included
    if not '_static' in app.config.html_static_path:
        raise FileNotFoundError(
            'Gallery expects `html_static_path` to contain a "doc/_static/" '
            'folder, in which the labels will be looked up.'
        )
    static_dir = os.path.join(doc_dir, '_static')
    labels_dir = gallery_conf['labels_dir']
    labels_path = os.path.join(static_dir, labels_dir)

    # Create category pages
    category_projects = {}
    for section in gallery_conf['sections']:
        project = section['path']
        info = TAG_MAPPING.get(project, {})
        categories = info.get('category', [])
        for category in categories:
            if category not in category_projects:
                category_projects[category] = []
            category_projects[category].append(section)

    for category, sections in category_projects.items():
        generate_category_page(app, category, sections, categories_dir, labels_path)

    # Create main index.rst for category gallery
    generate_category_index(app, category_projects.keys(), categories_dir)

def generate_category_page(app, category, sections, categories_dir, labels_path):
    category_rst = category + '\n' + '_'*len(category) + '\n'
    category_rst += f'\n{category} Projects\n'
    category_rst += '\n.. grid:: 2 2 4 4\n    :gutter: 3\n    :margin: 0\n'

    toctree_entries = []

    for section in sections:
        project_path = section['path']
        title = section['title']
        description = section['description']
        labels = section['labels']
        
        doc_dir = app.builder.srcdir
        gallery_path = app.config.gallery_conf['path']
        gallery_project_path = os.path.join(doc_dir, gallery_path, project_path)
        files = glob.glob(os.path.join(gallery_project_path, '*.ipynb'))

        if len(files) > 1:
            if 'index.ipynb' in [os.path.basename(f) for f in files]:
                main_file = 'index'
                thumb_path = os.path.join(gallery_project_path, 'thumbnails', 'index.png')
                files = sort_index_first(files)
            else:
                logger.warning(
                    '%s has multiple files but no "index.ipynb", skipping it entirely',
                    title,
                )
                continue
        else:
            main_file = Path(files[0]).stem
            thumb_path = os.path.join(gallery_project_path, 'thumbnails', f'{main_file}.png')

        if not os.path.isfile(thumb_path):
            logger.warning(f"Thumbnail not found for {project_path}, skipping.")
            continue  # Skip if thumbnail doesn't exist

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


        main_file_path = os.path.join(gallery_project_path, main_file)
        category_rst += INLINE_THUMBNAIL_TEMPLATE.format(
            title=title, section_path=main_file_path,
            description=description, thumbnail=thumb_path,
            labels=labels_str,
        )

        toctree_entries.append(f'{title} <{main_file_path}>')

    category_rst += generate_project_toctree(toctree_entries)

    with open(os.path.join(categories_dir, f'{category.lower().replace(" ", "_")}.rst'), 'w') as f:
        f.write(category_rst)

def generate_project_toctree(projects):
    toctree = '.. toctree::\n'
    toctree += '   :hidden:\n\n'
    for project in projects:
        toctree += f'   {project}\n'
    return toctree

def generate_category_index(app, categories, categories_dir):
    index_rst = 'Category Gallery\n' + '_'*len('Category Gallery') + '\n'
    index_rst += '\nList of categories:\n\n'

    for category in sorted(categories):
        index_rst += f'* :doc:`{category} <{category.lower().replace(" ", "_")}>`\n'

    with open(os.path.join(categories_dir, 'index.rst'), 'w') as f:
        f.write(index_rst)

def setup(app):
    app.add_config_value('category_gallery_conf', {}, 'html')
    app.connect('builder-inited', generate_category_galleries)
    metadata = {'parallel_read_safe': True, 'version': '0.0.1'}
    return metadata
