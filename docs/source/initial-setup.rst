
Installation and setup
========================

You need to install the package on both your local machine and on the cluster you want to connect to.


On your local machine
-----------------------------------------

Install [Anaconda python](https://www.anaconda.com/distribution/#download-section) your local machine. Say yes when asked if want to install Visual Studio Code. If you are on a Windows machine you also need to tick the box to add Anaconda python to your PATH when prompted. 

> If you are on a Windows machine, you also need to download and the newest version of Powershell. You find see how to do that [on this page](https://docs.microsoft.com/en-us/powershell/scripting/install/installing-powershell-core-on-windows?view=powershell-7#msi) under "Installing the MSI package". Now open the newly installed Powershell and run: `conda init powershell`. Close Powershell and open it again. Now you have access to conda to create environments if you like.

Activate the environment you want to install in and do:

.. code-block:: bash

    conda install -c kaspermunch slurm-jupyter

If you have not done that yet, you need to set up your ssh connection to the cluster so you can connect securely without typing the password every time. First see if you have these two authentication files on your local machine:

.. code-block:: bash

    ~/.ssh/id_rsa
    ~/.ssh/id_rsa.pub

if not, you generate a pair of authentication keys like this. Do not enter a passphrase when prompted - just press enter:

.. code-block:: bash

    ssh-keygen -t rsa

Now use ssh to create a directory ~/.ssh on the cluster (assuming your username on the cluster is `donald`):

.. code-block:: bash

    ssh donald@login.genome.au.dk mkdir -p .ssh

Finally append the public key on your local machine to the file `.ssh/authorized_key`s on the cluster and enter the password one last time (replace `donald` with your cluster user name):

.. code-block:: bash

    cat ~/.ssh/id_rsa.pub | ssh donald@login.genome.au.dk 'cat >> .ssh/authorized_keys'

From now on you can log into the cluster from your local machine without being prompted for a password.

On the cluster
-------------------------------

You need to install [miniconda](https://docs.conda.io/en/latest/miniconda.html) if you do not already have Anaconda Python installed in your cluster home dir. Run these commands in your cluster home dir. They will download and install miniconda for you. Say yes when it asks if it should run `conda init` for you.

.. code-block:: bash

    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
    bash Miniconda3-latest-Linux-x86_64.sh

You need to install jupyter and openssl on the cluster as well as any package you want to use in your jupyter notebooks. Create a conda environment with the most common packages for population genetics (replace `monkey` with something else): 

.. code-block:: bash

    conda create --name myproject -c anaconda -c conda-forge -c bioconda python=3 biopython jupyter jupyterlab openssl matplotlib mpld3 nbconvert numpy pandas scipy seaborn statsmodels pyfaidx scikit-bio mygene msprime scikit-allel colorama

As a minimum the environment should contain `jupyter`, `jupyterlab`, and `slurm-jupyter`:
    
.. code-block:: bash

    conda create --name myproject -c anaconda -c conda-forge -c kaspermunch python=3 jupyter jupyterlab slurm-jupyter

You have to do some configuration of jupyter script to work. `slurm-jupyter` comes with a shell script that does that for you. Then run it like this:

.. code-block:: bash

    config-slurm-jupyter.sh

It will ask about a lot of information. You can just press enter for all of them *except* when prompted for what password you want to use.

