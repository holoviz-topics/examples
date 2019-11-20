Maintenance
===========

This work is supported and maintained by `Anaconda
<https://www.anaconda.com>`_.  PyViz Topics is part of the `PyViz
<https://pyviz.org>`_ project to showcase Python data visualization tools.
The primary PyViz maintainers are Philipp Rudiger, James A. Bednar,
Julia Signell, and Jean-Luc Stevens, with bug reports and patches from
numerous members of the Github community.

Website Maintenance
===================
The website building occurs in travis jobs that are triggered by commit messages.

**NOTE:** When you merge PRs, you should be very careful about what is included
in the commit messages.

Building the dev website
~~~~~~~~~~~~~~~~~~~~~~~~

The `dev website <https://pyviz-dev.github.io/examples>`_ builds everytime someone
builds any project. This is useful, because people can see what their project will
look like, and make any adjustments.

**NOTE:** If multiple people are doing this at the same time, they will step on each
others toes, and jobs might fail.

Building the rel website
~~~~~~~~~~~~~~~~~~~~~~~~~

To build the release version of the `website <https://examples.pyviz.org>`_, push
a commit (it can be empty ``--allow-empty``) that contains the text
``build:website_release``.

Rebuilding project(s)
~~~~~~~~~~~~~~~~~~~~~

Once a project is built, it is stored on a special ``evaluated`` branch on github
and it won't be rebuilt until that is specifically requested.
If you need to rebuild projects, you can do that by pushing a commit
containing ``build:`` and the name of any project. If you would like to rebuild
them all (not recommended) instead of listing them by name, just include ``build:all``.
Each project will build in its own job on Travis and then
try to commit the result to the evaluated branch. This mostly works, but if multiple
jobs finish at the same time, one might not get pushed. If after all the jobs have
finished, you notice that some projects are not updated in the evaluated branch, you
can restart those jobs on travis.

Top level actions
=================

Project writers should never touch the top level files and directories (except
for test_data), but for maintainters, there are certain top-level maintenance
jobs that keep this site running smoothly.

Adding new label badges
~~~~~~~~~~~~~~~~~~~~~~~

When a project contains labels, a badge is added to the website for each label.
If the badge isn't listed in `doc/_static/labels <https://github.com/pyviz-topics/examples/tree/master/doc/_static/labels>`_
the color is gray by default. Additionally, nbsite should raise a warning that explains
how to create a specialized badge. Normally this just means choosing a color and
adding this svg: https://img.shields.io/badge/-<label>-<color> to the labels directory.

Skipping notebooks in tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a particular notebook needs skipping in the tests, add the relevant glob
to tox.ini.

Specifying binder env
~~~~~~~~~~~~~~~~~~~~~

Hopefully this will get easier, but basically, at this time there is an entirely
separate environment file for binder. Ideally, binder would read from all the projects,
unpin everything, and then setup that union environment.
