

Running a Jupyter server
=============================

You can run a jupyter notebook in your browser from a compute node on the cluster. This way your analysis runs on the file system where your data is, and you can keep data, code and documentation in one place. `slurm_jupyter` is a script that starts and connects to a jupyter server on compute note and forwards the web display to your local machine.  It only works using the Chrome browser.

When you run `slurm-jupyter`, it will connect to the cluster and write a script that it submits on the cluster queue. Once that script runs on a compute node, it starts the jupyter server for you. `slurm-jupyter` then opens connections so it can read the terminal output from jupyter and write it in the teminal of your local macine as it normally happens when you run jupyter. `slurm-jupyter`. It then forwards a port form the cluster to your local machine so you can see the jupyter web app in your local browser. The last thing it does is to open the Chrome browser and point it to the correct port.
The first time Chrome opens the connection to the cluster it will give you an error page saying “Your connection is not private”. You then need to click “Advanced” and then “Proceed to localhost (unsafe)”.  Then your file tree on the cluster should appear.
To stop the server just press Ctrl-C and the script will do all the canceling, closing and cleanup on the cluster before it exits.

If your username on your local machine is the same as on the cluster, `slurm-jupyter` will run like this:

.. code-block:: bash

    slurm-jupyter -e monkey

where `-e monkey` specifies an environment to activate on the cluster that has jupyter installed (my `monkey` environment). If your username on the cluster (eg. donald) is different from that on your local machine, you need to supply the that. 

.. code-block:: bash

    slurm-jupyter -u donald -e monkey

The script `slurm-jupyter` has a lot of options with sensible default values that you can see like this:

.. code-block:: bash

    slurm-jupyter --help    

