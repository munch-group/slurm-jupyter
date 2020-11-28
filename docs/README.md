 

Replace `slurm_jupyter` with actual package name below:

In docs run:

    sphinx-quickstart

Choose `'y'` when prompted for separate source and buld directories.

In `source/conf.py`, change

```python
sys.path.insert(0, os.path.abspath('.'))
```

to 

```python
sys.path.insert(0, os.path.abspath('../../'))
```

Set theme:

```python
html_theme = 'sphinx_rtd_theme'
```

Enable these extensions:

```python
extensions = ['sphinx.ext.autodoc',
              'sphinx.ext.napoleon'
]
```

Run this in `docs` to generate rst files from API doc strings:

    sphinx-apidoc -f -o source ../slurm_jupyter

Modify `index.rst` to your liking. Add other rst files to the toc tree. Remember to honor indentation and put a line between the directive and the rst base names.:


```rst
.. toctree::
   :maxdepth: 2
   :caption: Contents:

   modules
```

Generate html documentation:

```bash
make html
```

Sign into https://readthedocs.org/ and add the GitHub repo.