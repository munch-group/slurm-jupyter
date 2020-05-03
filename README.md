# Jupyter on a SLURM cluster

You can run a jupyter notebook in your browser from a compute node on the cluster. This way your analysis runs on the file system where your data is, and you can keep data, code and documentation in one place. `slurm_jupyter` is a script that starts and connects to a jupyter server on compute note and forwards the web display to your local machine.  It only works using the Chrome browser.

## One-time setup on your local machine

Install [Anaconda python](https://www.anaconda.com/distribution/#download-section) your local machine. Say yes when asked if want to install Visual Studio Code. If you are on a Windows machine you also need to tick the box to add Anaconda python to your PATH when prompted. 

> If you are on a Windows machine, you also need to download and the newest version of Powershell. You find see how to do that [on this page](https://docs.microsoft.com/en-us/powershell/scripting/install/installing-powershell-core-on-windows?view=powershell-7#msi) under "Installing the MSI package". Now open the newly installed Powershell and run: `conda init powershell`. Close Powershell and open it again. Now you have access to conda to create environments if you like.

You install `slurm-jupyter` like this:

    conda install -c kaspermunch slurm-jupyter

If you have not done that yet, you need to set up your ssh connection to the cluster so you can connect securely without typing the password every time. First see if you have these two authentication files on your local machine:

    ~/.ssh/id_rsa
    ~/.ssh/id_rsa.pub

if not, you generate a pair of authentication keys like this. Do not enter a passphrase when prompted - just press enter:

    ssh-keygen -t rsa

Now use ssh to create a directory ~/.ssh on the cluster (assuming your username on the cluster is `donald`):

    ssh donald@login.genome.au.dk mkdir -p .ssh

Finally append the public key on your local machine to the file `.ssh/authorized_key`s on the cluster and enter the password one last time (replace `donald` with your cluster user name):

    cat ~/.ssh/id_rsa.pub | ssh donald@login.genome.au.dk 'cat >> .ssh/authorized_keys'

From now on you can log into the cluster from your local machine without being prompted for a password.

## One-time setup on the cluster

You need to install [miniconda](https://docs.conda.io/en/latest/miniconda.html) if you do not already have Anaconda Python installed in your cluster home dir. Run these commands in your cluster home dir. They will download and install miniconda for you. Say yes when it asks if it should run `conda init` for you.

    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
    bash Miniconda3-latest-Linux-x86_64.sh

You need to install jupyter and openssl on the cluster as well as any package you want to use in your jupyter notebooks. Create a conda environment with the most common packages for population genetics (replace `monkey` with something else): 

    conda create --name myproject -c anaconda -c conda-forge -c bioconda python=3 biopython jupyter jupyterlab openssl matplotlib mpld3 nbconvert numpy pandas scipy seaborn statsmodels pyfaidx scikit-bio mygene msprime scikit-allel colorama

As a minimum the environment should contain `jupyter`, `jupyterlab`, and `slurm-jupyter`:
    
    conda create --name myproject -c anaconda -c conda-forge -c kaspermunch python=3 jupyter jupyterlab slurm-jupyter

You have to do some configuration of jupyter script to work. `slurm-jupyter` comes with a shell script that does that for you. Then run it like this:

    config-slurm-jupyter.sh

It will ask about a lot of information. You can just press enter for all of them *except* when prompted for what password you want to use.

## Run slurm-jupyter.py

Put `slurm_jupyter.py` somewhere in your PATH or run it like any other Python script. It has a lot of options that you can see like this:

    slurm-jupyter.py --help

If your username on the cluster (eg. donald) is different from that on your local machine, you need to supply the that. You also need to specify an environment to activate on the cluster that has jupyter installed (our `monkey` environment):

    slurm-jupyter.py -u donald -e monkey

To specify that you want 24g of memory and 3 cores, that you want jupyter to run in a conda environment called `monkey`, and that you want jupyter to run for up to 11 hours before slurm cancels your job, you can execute it like this:

    slurm-jupyter.py -u donald -m 24g -c 3 -e monkey -t 11:00:00

When you run `slurm-jupyter`, it will connect to the cluster and write a script that it submits on the cluster queue. Once that script runs on a compute node, it starts the jupyter server for you. `slurm-jupyter` then opens connections so it can read the terminal output from jupyter and write it in the teminal of your local macine as it normally happens when you run jupyter. `slurm-jupyter`. It then forwards a port form the cluster to your local machine so you can see the jupyter web app in your local browser. The last thing it does is to open the Chrome browser and point it to the correct port.

The first time Chrome opens the connection to the cluster it will give you an error page saying “Your connection is not private”. You then need to click “Advanced” and then “Proceed to localhost (unsafe)”.  Then your file tree on the cluster should appear.

To stop the server just press Ctrl-C and the script will do all the canceling, closing and cleanup on the cluster before it exits.
