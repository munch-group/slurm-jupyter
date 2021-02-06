
Installation and setup
========================

You need to install the package on both your local machine and on the cluster you want to connect to.


On your local machine
-----------------------------------------

Install `Anaconda python
<https://www.anaconda.com/distribution/#download-section>`_ on your local
machine. Make the default installation. 

If you have a Windows machine, you must use the *Anaconda Poweshell Prompt* as
your terminal (*not* the Anaconda Prompt and *not* the CMD). 

Install `slurm-jupyter` like this:

.. code-block:: bash

    conda install -c kaspermunch slurm-jupyter

The operation of `slurm-jupyter` requires that you have set up ssk-keys on the
cluster so that you can log in without using a password. First check if you have
these two authentication files on your local machine (you can do so by running
`ls -a ~/.ssh` in the terminal):

.. code-block:: bash

    ~/.ssh/id_rsa
    ~/.ssh/id_rsa.pub

if not, you generate a pair of authentication keys like this. Do not enter a
passphrase when prompted - just press enter:

.. code-block:: bash

    ssh-keygen -t rsa

Now use ssh to create a directory `~/.ssh` on the cluster (assuming your
username on the cluster is `donald`):

.. code-block:: bash

    ssh donald@login.genome.au.dk mkdir -p .ssh

Finally append the public key on your local machine to the file
``.ssh/authorized_keys`` on the cluster and enter the password one last time
(replace `donald` with your cluster user name):

.. code-block:: bash

    cat ~/.ssh/id_rsa.pub | ssh donald@login.genome.au.dk 'cat >> .ssh/authorized_keys'

From now on you can log into the cluster from your local machine without being
prompted for a password.

Jupyter runs best in the Chrome browser. For the best experience, install that
before you go on. It does not need to be your default browser. `slurm-jupyter`
will use it anyway. 


On the cluster
-------------------------------

You need to install `miniconda
<https://docs.conda.io/en/latest/miniconda.html>`_ if you do not already have
Anaconda Python installed in your cluster home dir. Run these commands in your
cluster home dir. They will download and install miniconda for you. Say yes when
it asks if it should run `conda init` for you.

.. code-block:: bash

    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
    bash Miniconda3-latest-Linux-x86_64.sh

Install `slurm-jupyter` in a conda environment:

.. code-block:: bash

    conda install -c kaspermunch slurm-jupyter

You then have to do some configuration of jupyter. `slurm-jupyter`
comes with a shell script that does that for you. Then run it like this:

.. code-block:: bash

    config-slurm-jupyter.sh

It will ask about a lot of information. You can just press enter for all of them
*except* when prompted for what password you want to use. This password works
across all the environments you create on the cluster, so you need to do this once.

