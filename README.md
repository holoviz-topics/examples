# PyViz Topics Examples

Domain-specific narrative examples using multiple PyViz projects.
Isolated fully described projects, runnable locally and deployable
to Anaconda Enterprise.

# Running Locally

To run an example locally install anaconda-project and run the
command defined in the anaconda-project file:

```bash
conda install anaconda-project tornado<5.0
anaconda-project run
```

### Don't want to use anaconda-project?
If you don't want to use anaconda-project, you can create a regular
conda environment using:

```bash
conda env create --file anaconda-project.yml
```

Activate the environment (be sure to replace env-name with the real
name of the environment you created):

```bash
conda activate <env-name>
```

Then start a jupyter notebook as usual:

```bash
jupyter notebook
```

**NOTE:** If the notebook depends on data files, you will need to
download them explicitly if you don't use anaconda-project, by
extracting the URLs defined in anaconda-project.yml and saving
the file(s) to this directory.

# Uploading to AE
In addition to running examples locally you can upload and share them
using Anaconda Enterprise. If you've already installed anaconda-project,
then for an example named "bears" just do:

```
cd bears
anaconda-project archive bears.zip
```

Then in the AE interface select "Create", "Upload Project" and navigate
to the zip file. Once your project has been created, you can deploy it.

# Making a new project

Once you have a notebook that you think it is ready to be its own project
you can follow these steps to get it set up. For the examples I'll use
an example project named "bears"

### 1. Move the notebook into a new directory with same name

```bash
mkdir bears
mv bears.ipynb ./bears
cd bears
```

### 2. Get the minimum package dependencies

I usually start by using nbrr (`conda install -c conda-forge nbrr `) which
reads the notebooks and looks for dependencies:

```bash
nbrr env --directory "." --name bears > anaconda-project.yml
```

### 3. Create the anaconda-project file

Copy anaconda-project_template.yml to your own project, then just
replace NAME, DESC, MAINTAINERS and add the dependencies from step 2.

### 4. Make sure it works

```
anaconda-project run test
```

You might need to declare extra dependencies or add data
downloads (see bay_trimesh for an example of downloading data).

### 5. For remote or large data

Make a smaller version of the data and put it in `test_data/<project>`.

### 6. If using intake

The intake catalog should be at the top level of the project directory and
called "catalog.yml".

```
. bears
├── anaconda-project.yml
├── bears.ipynb
└── catalog.yml
```

If using the intake cache, point the cache to the data dir in the project
by defining the INTAKE_CACHE_DIR variable in the anaconda-project file:

```yaml
variables:
  INTAKE_CACHE_DIR: data
```

This way when the user runs the notebook, they will still be able to see
the data from within the project directory:

```
. bears
├── anaconda-project.yml
├── bears.ipynb
├── catalog.yml
└── data
    └── f890ce4d538240e87ede9d31a6541443
        └── data.csv
```

Make sure to make a test catalog and put it in `test_data/<project>/catalog.yml`.
The sources in this catalog should have the same keys as the sources in the
real catalog, but they can point to smaller local versions of the data. That
data should also be in `test_data/<project>/` but referred to as if it were
inside a data directory.

```
test_data
└── bears
    ├── catalog.yml
    └── fake_local_data.csv
```

```yaml
sources:
  bears:
    description: Test data in a test catalog
    driver: csv
    args:
      urlpath: '{{ CATALOG_DIR }}/data/fake_local_data.csv'
```

# How test data work
Before running the tests on CI, we call `doit small_data_setup --name <name>`.
This command injects small versions of the data (from test_data) into the
project declared in the name argument. If intake is being used then the
test_catalog is swapped for the real intake catalog. To set everything
back to normal after running the tests, call `doit small_data_cleanup --name <name>`.