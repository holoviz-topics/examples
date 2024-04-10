# Modernizing an example checklist

## Preliminary checks

- [ ] Look for [open PRs](https://github.com/holoviz-topics/examples/pulls) and [issues](https://github.com/holoviz-topics/examples/issues) that reference the project you are updating. It is possible previous unmerged work in PR could be re-used to modernize the project. Comment on these PRs and issues when appropriate, hopefully we should be able to close some of them after your modernizing work.

## Change ‘anaconda-project.yml’ to use the latest workable version of packages

- [ ] Pin python=3.11
- [ ] Remove the upper pin (e.g. `hvplot<0.9` to `hvplot`, `panel>=0.12,<1.0` to `panel>=0.12`) of all other dependencies. Removing the upper pins of dependencies could necessitate code revisions in the notebooks to address any errors encountered in the updated environment. Should complexities or extensive time requirements arise, document issues for team discussion on whether to re-pin specific packages or explore other solutions.
- [ ] Add/update the lower pin of all other dependencies (e.g. `hvplot` to `hvplot>=0.9.2`, `hvplot>=0.8` to `hvplot>=0.9.2`). Usually, the new/updated lower pin of a dependency will be the version resolved after `anaconda prepare` has been run. Execute `!conda list` in a notebook, or `anaconda run conda list` in the terminal, to display the version of each dependency installed in the environment. Adjusting the lower pin helps ensure that the locks produced for each platform (linux-64, win-64, osx-64, osx-arm64) rely on the tested dependencies and not on some older versions.
- [ ] If one of the channels include conda-forge or pyviz, ask Maxime if it can be removed

## Plot API updates (discussed on a per-example basis)

- [ ] Generally, try to replace HoloViews usage with hvPlot. At a certain point of complexity, such as with the use of ‘.select’, it might be better to stick with HoloViews. Additional examples of ‘complexity boundaries’ should be documented in [this document](https://docs.google.com/document/d/1LYkChbVZzqq5S1S4Mkj1rM3PNPJDDGriks8YTc4EQc4/edit?usp=sharing).
- [ ] Almost always, try to replace the use of `datashade` with `rasterize` (read [this page](https://holoviews.org/user_guide/Large_Data.html)). Essentially, `rasterize` allows Bokeh to handle the colormapping instead of Datashader.

## Interactivity API updates (discussed on a per-example basis)

- [ ] Remove all `pn.interact` usage
- [ ] Avoid `.param.watch()` usage. This is [pretty low-level and verbose approach](https://param.holoviz.org/user_guide/Dependencies_and_Watchers.html#watchers) and should not be used in Examples unless required, or an Example is specifically trying to demo its usage in an advanced workflow.
- [ ] Prefer using `pn.bind()`. Read [this page](https://panel.holoviz.org/explanation/api/reactive.html) for explanation.
- [ ] For apps built using a class approach, when they create a `view()` method and call it directly, update the class by inheriting from `pn.viewable.Viewer` and replace `view()` by `__panel__()`. Here is an [example](https://panel.holoviz.org/gallery/nyc_deckgl.html). 

## Panel App updates (discussed on a per-example basis)

- [ ] If the project doesn’t at any point create a Panel app at all, consider creating one. It can be as simple as wrapping a plot in `pn.Column`, or more complicated to incorporate widgets, etc. Make the final app  `.servable()`.
- [ ] If the project creates an app in a notebook but doesn’t deploy it (i.e. there is no `command: dashboard` declaration in the `anaconda-project.yml` file), try adding it.
- [ ] If the project already deploys an app but doesn’t wrap it in a nice template, consider wrapping it in a [template](https://panel.holoviz.org/reference/index.html#templates).
- [ ] If the project deploys an app wrapped in a template, customize the template a little so all the apps don’t look similar (e.g. change the header background color). This doesn’t need to be discussed.

## General code quality updates

- [ ] If the notebook disables warnings (e.g. with `warnings.simplefilter(‘ignore’)` somewhere at the start of the notebook, remove this line. Try to update the code to remove the warnings, if any. If updating the code to remove the warnings is taking significant amount of time and effort, bring it up for discussion and we may decide to disable warnings again.

## Text content

- [ ] Edit the text content anywhere and everywhere that it can be improved for clarity.
- [ ] Check the links are valid, and update old links (e.g. http -> https, xyz.pyviz.org -> xyz.holoviz.org)
- [ ] Remove instructions to install packages inside an example

## Visual appearance - Example

- [ ] Check that the titles/headings make sense and are succinct.
- [ ] Check that the text content blocks are easily readable; revise into additional paragraphs if needed.
- [ ] Check that the code blocks are easily readable; revise as needed. (e.g. add spaces after commas in a list if there are none, wrap long lines, etc.)
- [ ] Check image and plot sizes. If possible, making them responsive is highly recommended.
- [ ] Check the appearance on a smartphone (check Google to see how to adapt the appearance of your browser to display pages as if they were seen from a smartphone, this is usually done via the web developer tools). This is not a top priority for all examples, but if there are a few easy and straightforward changes to make that can improve the experience, let’s do it.
- [ ] Check the updated notebook with the original notebook

## Visual appearance - Gallery

- [ ] Check the thumbnail is visually appealing
- [ ] Check the project title is well formatted (e.g. `Ml Annotators` to `ML Annotators`), if not, add/update the `examples_config.title` field in `anaconda-project.yml`
- [ ] Check the project description is appropriate, if not, update the `description` field in `anaconda-project.yml`

## Workflow (after you have made the changes above)

- [ ] Run successfully `doit validate:<projectname>`
- [ ] Run successfully `doit test:<projectname>`
- [ ] Run successfully `doit doc_one –name <projectname>`. It’s better if the project notebook(s) is saved with its outputs (but be sure to clear outputs before committing to the examples repo!) when building the docs. Then open this file in your browser `./builtdocs/index.html` and check how the site looks.
- [ ] If you’re happy with all the above, open a PR. Reminder, clear notebook outputs before pushing to the PR.
