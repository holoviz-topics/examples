import os
import glob
from pathlib import Path
import sphinx.util
import re

from collections import Counter

from dodo import CATNAME_TO_CAT_MAP, CAT_TO_CATNAME_MAP

logger = sphinx.util.logging.getLogger('category-gallery-extension')

DEFAULT_GALLERY_CONF = {
    'default_extensions': ['*.ipynb'],
    'examples_dir': os.path.join('..', 'examples'),
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
            'categories': [],
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
{last_updated}

"""

INLINE_THUMBNAIL_TEMPLATE_SEE_MORE = """
    .. grid-item-card:: :doc:`See More <{category_path}>`
        :shadow: md

        {category} projects
"""


def md_directive(md, name, contents, inline=None, params=None):
    if isinstance(contents, str):
        contents = [contents]
    # Code to acquire resource, e.g.:
    md += f'\n\n```{{{name}}}{" " + inline if inline else ""}\n'
    if params:
        for k, v in params.items():
            md += f':{k}:{" " + v if v else ""}\n'
    md += '\n'
    for line in contents:
        md += f'{line}\n'
    md += '```\n\n'
    return md


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

def generate_labels_rst(labels):
    labels_str = '        .. container:: hv-gallery-badges \n\n'
    for label in labels:
        labels_str += ' ' * 11 + f':bdg-primary-line:`{label}`\n'
    return labels_str

def generate_last_updated_rst(last_updated):
    if last_updated:
        return f"""
        .. container:: last-updated

            Updated: {last_updated}
        """
    return ''

def generate_card_grid(app, projects):
    rst = '\n.. grid:: 2 2 4 4\n    :gutter: 3\n    :margin: 0\n'
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

        labels_str = generate_labels_rst(section['labels'])

        last_updated_str = generate_last_updated_rst(section['last_updated'])

        main_file_path = os.path.join(project_path, main_file)
        rst += INLINE_THUMBNAIL_TEMPLATE.format(
            title=title, section_path=main_file_path,
            description=description, thumbnail=thumb_path,
            labels=labels_str, last_updated=last_updated_str,
        )
        toctree_entries.append(f'{title} <{main_file_path}>')
    md = md_directive('', 'eval-rst', rst)
    return md, toctree_entries

def generate_toctree(entries, hidden=True):
    params = {}
    if hidden:
        params['hidden'] = None
    toctree = md_directive('', 'toctree', entries, params=params)
    return toctree

def generate_galleries(app):
    gallery_conf = app.config.gallery_conf

    # Create category pages
    category_projects = {}
    for section in gallery_conf['sections']:
        categories = section['categories']
        for category in categories:
            # add this section to the list for each catname
            catname = CAT_TO_CATNAME_MAP[category]
            if catname not in category_projects:
                category_projects[catname] = []
            category_projects[catname].append(section)

    for category in CATNAME_TO_CAT_MAP:
        projects = category_projects.get(category)
        if projects:
            generate_category_page(app, category, projects)

    # Create main index.md for gallery
    generate_gallery_index(app, category_projects)

def generate_category_page(app, category, projects):
    # Main Header
    md = f'# {category}\n\n'

    # Insert category page overview if exists
    category_file_path = os.path.join(app.builder.srcdir, 'category_descriptions', f'{clean_category_name(category)}.md')
    if os.path.exists(category_file_path):
        with open(category_file_path, 'r') as file:
            md += '\n' + file.read() + '\n\n'
    else:
        md += f'\n{category} Projects\n'

    if projects:
        # Gallery Cards
        md_cg, toctree_entries = generate_card_grid(app, projects)
        md += md_cg
        md += generate_toctree(toctree_entries)

    with open(os.path.join(app.builder.srcdir,
                           app.config.gallery_conf['path'],
                           f'{clean_category_name(category)}.md'),
                           'w') as f:
        f.write(md)

def generate_label_buttons(labels):
    buttons_html = '\n\n<div id="label-filters-container">\n'
    # add sort by controls within this container
    buttons_html += """
  <div class="filter-label" id="sort-container" style="margin-bottom: 15px;">
    <label for="sort-options">Sort by:</label>
    <select id="sort-options">
      <option value="title">Title</option>
      <option value="date">Last Updated</option>
    </select>
  </div>
"""
    buttons_html += '  <div class="filter-label">Filter by label:</div>\n'
    buttons_html += '  <div id="label-filters" class="filter-box">\n'
    for label in labels:
        buttons_html += f'    <button class="filter-btn" data-label="{label}">{label}</button>\n'
    buttons_html += '  </div>\n</div>\n'
    return buttons_html

def generate_gallery_index(app, category_projects):
    # Overview
    INTRO = os.path.join(app.builder.srcdir, 'intro.md')
    with open(INTRO, 'r') as file:
        md = '\n' + file.read() + '\n\n'

    # Label Filter Buttons
    all_labels = []
    for sections in category_projects.values():
        for section in sections:
            all_labels.extend(section['labels'])
    all_labels = Counter(all_labels)
    all_labels = [label for label, _ in all_labels.most_common()]
    label_buttons_html = generate_label_buttons(all_labels)
    
    # Insert the label buttons using raw/html directive
    md = md_directive(md, 'raw', label_buttons_html.splitlines(), 'html')

    # Gallery Cards per category
    toctree_entries = []
    for category in CATNAME_TO_CAT_MAP:
        if category not in category_projects:
            continue
        category_link = f'{clean_category_name(category)}'
        md += f'\n## [{category}]({category_link})\n\n'

        projects = category_projects.get(category, [])
        if not projects:
            continue
        
        md_cg, _ = generate_card_grid(app, projects)
        md += md_cg

        toctree_entries.append(f'{category} <{category_link}>')

    md += generate_toctree(toctree_entries)

    with open(os.path.join(app.builder.srcdir,
                           app.config.gallery_conf['path'],
                           'index.md'),
                           'w') as f:
        f.write(md)

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
