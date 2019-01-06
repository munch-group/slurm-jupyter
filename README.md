# Jupyter on a SLURM cluster

You can run a jupyter notebook in your browser from a compute node on the cluster. This way your analysis runs on the file system where your data is, and you can keep data, code and documentation in one place. `slurm_jupyter` is a script that starts and connects to a jupyter server on compute note and forwards the web display to your local machine.  It only works using the Chrome browser.

## One-time setup on the cluster

You need to install jupyter and openssl on the cluster. If you use Anaconda python on the cluster (you should install that yourself) you should do that with conda: 

    conda install -c anaconda jupyter openssl

You have to do some configuration of jupyter for the script to work. I have made a shell script that does that for you. Clone this repository to download the script to the cluster:

    git clone https://github.com/kaspermunch/slurm_jupyter.git

Then run it like this:

    bash slurm_jupyter/cluster_config.sh

It will ask about a lot of information. You can just press enter for all of them *except* when prompted for what password you want to use.

## One-time setup on your local machine

If you have not done that yet, you need to set up your ssh connection to the cluster so you can connect securely without typing the password every time. First see if you have these two authentication files on your local machine:

    ~/.ssh/id_rsa
    ~/.ssh/id_rsa.pub

if not, you generate a pair of authentication keys like this. Do not enter a passphrase when prompted - just press enter:

    ssh-keygen -t rsa

Now use ssh to create a directory ~/.ssh on the cluster (assuming your username on the cluster is `XXX`):

    ssh XXX@login.genome.au.dk mkdir -p .ssh

Finally append the public key on your local machine to the file `.ssh/authorized_key`s on the cluster and enter the password one last time:

    cat ~/.ssh/id_rsa.pub | ssh XXX@login.genome.au.dk 'cat >> .ssh/authorized_keys'

From now on you can log into the cluster from your local machine without being prompted for a password.

## Run slurm_jupyter

Put `slurm_jupyter` somewhere in your PATH or run it like any other Python script. It has a lot of options that you can see like this:

    slurm_jupyter --help

If your username on the cluster (eg. donald) is different from that on your local machine, you need to supply the that:

    slurm_jupyter -u donald -A monkey

To start a Jupyter server under some project (say `monkey`), you just need to execute the script like this:

    slurm_jupyter -u donald -A monkey

To specify that you want 24g of memory and 3 cores, that you want jupyter to run in a conda environment called primates, and that you want jupyter to run for up to 11 hours before slurm cancels your job, you can execute it like this:

    slurm_jupyter -u donald -A monkey -m 24g -c 3 -e primates -t 11:00:00

When you run `slurm_jupyter`, it will connect to the cluster and write a script that it submits on the cluster queue. Once that script runs on a compute node, it starts the jupyter server for you. `slurm_jupyter` then opens connections so it can read the terminal output from jupyter and write it in the teminal of your local macine as it normally happens when you run jupyter. `slurm_jupyter`. It then forwards a port form the cluster to your local machine so you can see the jupyter web app in your local browser. The last thing it does is to open the Chrome browser and point it to the correct port.

The first time Chrome opens the connection to the cluster it will give you an error page saying “Your connection is not private”. You then need to click “Advanced” and then “Proceed to localhost (unsafe)”.  Then your file tree on the cluster should appear.

To stop the server just press Ctrl-C and the script will do all the canceling, closing and cleanup on the cluster before it exits.