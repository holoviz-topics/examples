import glob
import os

from datetime import datetime
from pathlib import Path

import nbformat
import sphinx.util
import yaml

from dodo import deployment_cmd_to_endpoint

logger = sphinx.util.logging.getLogger('nbheader-extension')
TITLE_TAG = "hv-nbheader-title"


def transform_date(date_obj):
    if date_obj == 'NA':
        return date_obj
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
    return date_obj.strftime('%B %-d, %Y')


def load_authors_mapping(srcdir):
    with open(os.path.join(srcdir, 'authors.yml'), 'r') as file:
        return yaml.safe_load(file)


def create_header_html(
        authors: list[dict[str, str]],
        actions: list[dict[str, str]],
        created_date,
        updated_date,
    ):
    # Title not included in the header HTML but as an extra Markdown
    # cell, as otherwise the next-level headings (`## Foo`) are displayed
    # as if they were first-level titles.
    created_date = transform_date(created_date)
    updated_date = transform_date(updated_date)
    if updated_date == created_date:
        updated_date = None
    authors_html = ''.join([
        f'''
        <div class="d-flex align-items-center">
            <a href="{author['github']}" class="hv-nbheader-author-name">
                <img src="{author['picture']}" alt="profile" class="hv-nbheader-author-image rounded-circle me-2"><span>{author['name']}</span>
            </a>
        </div>
        '''
        for author in authors
    ])

    actions_html = ''.join([
        f"""
        <a class="mr-1" href="{action["url"]}"{'target="_blank"' if 'download' not in action["text"].lower() else ''}>
          <i class="{action["icon"]} me-1"></i>{action["text"]}
        </a>
        """
        for action in actions
    ])

    return f'''
    <div class="hv-nbheader container mb-5">
        <div class="hv-nbheader-authors-container mb-2">
            {authors_html}
        </div>
        <div class= "mb-2 opacity-75">
            Published: {created_date}{f" · Updated: {updated_date}" if updated_date else ""}
        </div>
        <hr />
        <div class=" hv-nbheader-actions mb-2 mt-2">
            {actions_html}
        </div>
        <hr />
    </div>
    '''


def insert_html_header(nb_path, html_header):
    nb = nbformat.read(nb_path, as_version=4)
    first_cell = nb['cells'][0]
    tags = first_cell['metadata'].get('tags', [])

    if not (title_processed := TITLE_TAG in tags):
        parts  = first_cell['source'].split('\n')
        title = parts[0]
        first_cell['source'] = title
        tags.append(TITLE_TAG)
        first_cell['metadata']['tags'] = tags
        if ''.join([s.strip() for s in parts]):
            body_cell = nbformat.v4.new_markdown_cell(source='\n'.join(parts[1:]))
            nb['cells'].insert(1, body_cell)

    html_header = f'```{{raw}} html\n{html_header}\n```'
    html_cell = nbformat.v4.new_markdown_cell(source=html_header)

    # To handle when the extension is run multiple times.
    if not title_processed:
        html_cell = nbformat.v4.new_markdown_cell(source=html_header)
        nb['cells'].insert(1, html_cell)
    else:
        nb['cells'][1]['source'] = html_header

    nbformat.write(nb, nb_path, version=nbformat.NO_CONVERT)


def add_nbheader(app):
    """
    This if for now re-using gallery_conf from the gallery extensions.
    Configurations could be decoupled if need be.
    """

    logger.info('Adding notebook headers...', color='white')

    AUTHORS_MAPPING = load_authors_mapping(app.builder.srcdir)
    # Get config
    gallery_conf = app.config.gallery_conf
    sections = gallery_conf['sections']
    doc_dir = Path(app.builder.srcdir)
    gallery_path = doc_dir / gallery_conf['path']
    for section in sections:
        project_name = section['path']
        header_data = section['header']

        authors_full = []
        authors = header_data['authors']
        for author in authors:
            author_mapping = AUTHORS_MAPPING[author]
            author_data = {
                'name': author_mapping.get('name', author),
                'picture': f'https://avatars.githubusercontent.com/{author}?size=48',
                'github': f'https://github.com/{author}',
            }
            authors_full.append(author_data)

        app.config.html_static_path.append(
            f'gallery/{project_name}/_archive'
        )

        project_path = gallery_path / project_name
        nb_files = glob.glob(os.path.join(project_path, '*.ipynb'))
        for nb_file in nb_files:
            nb_file = Path(nb_file)
            deployments = header_data['deployments']
            actions = []
            for depl in deployments:
                if depl['command'] == 'notebook':
                    text = 'Run notebook'
                    fa_icon = 'fas fa-play'
                    url = deployment_cmd_to_endpoint(depl['command'], project_name)
                    url += f'/notebooks/{nb_file.name}'
                elif depl['command'] == 'dashboard':
                    text = 'Open app(s)'
                    fa_icon = 'fa-solid fa-table-cells-large'
                    url = deployment_cmd_to_endpoint(depl['command'], project_name)
                else:
                    continue
                ddata = {
                    'text': text,
                    'icon': fa_icon,
                    'url': url,
                }
                actions.append(ddata)
                
            # App -> Notebook -> Download
            if len(actions) == 2 and 'notebook' in actions[0]['text'].lower():
                actions = actions[::-1]

            download = {
                'text': 'Download project',
                'icon': 'fas fa-download',
                'url': f'../../_static/{project_name}.zip',
            }
            actions.append(download)

            html_header = create_header_html(
                authors_full,
                actions,
                header_data['created'],
                header_data['last_updated'],
            )

            insert_html_header(nb_file, html_header)


def setup(app):
    app.connect('builder-inited', add_nbheader)
    metadata = {'parallel_read_safe': True,
                'version': '0.0.1'}
    return metadata
