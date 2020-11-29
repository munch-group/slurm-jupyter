
Excecuting notebooks on a slurm node
=====================================

You can execute long-running notebooks on the cluster so you do not have to wait for them to complete.

Executing notebooks
-----------------------

Execute a notebook `notebook1.ipynb` crating a new file called `notebook1.nbconvert.ipynb`:

.. code-block:: bash

    slurm-nb-run notebook1.ipynb

Output HTML format instead:

.. code-block:: bash

    slurm-nb-run --format html notebook1.ipynb

Execute a notebook `notebook1.ipynb` inplace:

.. code-block:: bash

    slurm-nb-run --inplace notebook1.ipynb

Execute several notebooks in the order given as arguments:

.. code-block:: bash

    slurm-nb-run --inplace notebook1.ipynb notebook2.ipynb notebook3.ipynb

Executing notebooks with different parameters
------------------------------------------------

When parameter settings apply to several notebooks (E.g. notebook1.ipynb and notebook2.ipynb), you can keep them in separate file (E.g. `permissive.py`) and them run the file in the first cell of each notebook. Say `permissive.py` contains:

.. code-block:: python

    cutoff = 5
    level = 1

then you can load those parameters using the `%run` `magic <https://ipython.readthedocs.io/en/stable/interactive/magics.html#magic-run>`_ in a cell at the top of each notebook:

.. code-block:: python

    %run permissive.py

Now say that you want to run your notebooks with several different sets of parameters (E.g. ``permissive.py`` and ``strict.py``) to see how your analysis and plots look in each case. You can do that like this:

.. code-block:: bash

    slurm-nb-run --spike permissive.py --spike strict.py --replace-run-magic notebook1.ipynb notebook1.ipynb

or the shorter

.. code-block:: bash

    slurm-nb-run -s permissive.py -s strict.py -r notebook1.ipynb notebook1.ipynb

This will create and execute notebooks in a directory structure like this:    

.. code-block:: 

    ├── notebook1
    │   ├── notebook1_permissive.ipynb
    │   └── notebook1_strict.ipynb
    ├── notebook2
    │   ├── notebook2_permissive.ipynb
    │   └── notebook2_strict.ipynb

In each notebook the first ``%run`` magic encountered will be replace to instead run one of the spiked python files. If you do not want to replace any of your existing ``%run`` magics, just omit the ``-r`` option:

.. code-block:: bash

    slurm-nb-run -s permissive.py -s strict.py notebook1.ipynb notebook1.ipynb


