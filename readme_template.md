# HoloViz Topics Examples

This project contains self-contained, typically domain-specific
examples illustrating how to use one or more open-source Python
visualization tools to explore data or understand a topic. Each
project is fully reproducible by downloading and running it locally.

# Running Locally

To run an example locally first download it from https://examples.holoviz.org,
unzip it, and cd into it. Then install [pixi](https://pixi.sh) and run the
`notebook` task defined in the `pixi.toml` file:

```bash
pixi run notebook
```

This creates the environment from `pixi.lock`, downloads the data the
notebooks need, and starts Jupyter. To see the other tasks the project
defines, such as `dashboard`, run:

```bash
pixi task list
```
