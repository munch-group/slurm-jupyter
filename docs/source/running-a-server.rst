

Running a Jupyter server
=============================

You can run a jupyter notebook in your browser from a compute node on the
cluster. This way your analysis runs on the file system where your data is, and
you can keep data, code and documentation in one place. ``slurm_jupyter`` is a
script that starts and connects to a jupyter server on compute note and forwards
the web display to your local machine. 

When you run ``slurm-jupyter``, it will connect to the cluster and write a
script that it submits on the cluster queue. Once that script runs on a compute
node, it starts the jupyter server for you. ``slurm-jupyter`` then opens
connections so it can read the terminal output from jupyter and write it in the
teminal of your local macine as it normally happens when you run jupyter.
``slurm-jupyter``. It then forwards a port form the cluster to your local
machine so you can see the jupyter web app in your local browser. The last thing
it does is to open the browser on your own machine and point it to the correct port. 

Running `slurm-jupyter`
-------------------------

If your username on your local machine is the same as on the cluster,
you can run `slurm-jupyter` like this:

.. code-block:: bash

    slurm-jupyter -e monkey -A baboon

`slurm-jupyter` runs jupyterlab by default. If you want the classical notebook use this command:

.. code-block:: bash

    slurm-jupyter -e monkey -A baboon --run notebook

The ``-e`` option specifies some conda environment on the cluster that you
want jupyter to run in. Your notbooks run on the cluster, so that environment
needs should have jupyter/jupyterlab installed and any packages needed to run
your notebooks. Use the `-A` options to specify the project you want to bill
computing hours to. If your username on the cluster is different from that on
your local machine, you need to supply the that using the `-u` option. Use the
`-h` option to see help text and all the options.

Once executed `slurm-jupyter prints colored status messages to the terminal. All
output from the jupyter server is redirected to your terminal too and printed without color.

After a while a jupyter notebook should show up in your browser window. The
first time you do this, your browser may refuse to show jupyter because the
connection is unsafe. In Safari you proceed to allow this. In Chrome, you can
simply type the characters "thisisunsafe" while in the Chrome window:

Once ready, jupyter may ask for your password. To close the jupyter
notebook, press `Ctrl-c` in the terminal. Closing the browser window does not
close down the jupyter on the cluster.

The script ``slurm-jupyter`` has a lot of options with sensible default values that you can see like this:

.. code-block:: bash

    slurm-jupyter --help    

Specifying resources
-------------------------

`slurm-jupyter` has a lot of options to specify required resources and the
defaults are sensible. The most important ones to know are the ones that specify
memory and time allotted for your session. For a jupyter session that can run up
to five hours and needs eight gigabytes of memory:

.. code-block:: bash

    slurm-jupyter -u hamlet -e monkey -A baboon -m 8g -t 5h