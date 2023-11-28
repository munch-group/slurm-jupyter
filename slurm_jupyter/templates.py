


# shell script for running a batch job
slurm_batch_script =  """#!/bin/sh
#SBATCH -p {queue}
{gres}
{memory_spec}
#SBATCH -n {nr_nodes}
#SBATCH -c {nr_cores}
#SBATCH -t {walltime}
#SBATCH -o {tmp_dir}/{tmp_name}.%j.out
#SBATCH -e {tmp_dir}/{tmp_name}.%j.err
#SBATCH -J {job_name}
{account_spec}
{sources_loaded}
##cd "{cwd}"

# Set nr of cores available to NumExpr
export NUMEXPR_MAX_THREADS={nr_cores}

{commands}
"""

# shell script for running the jupyter server
slurm_server_script =  """#!/bin/sh
#SBATCH -p {queue}
{gres}
{memory_spec}
#SBATCH -n {nr_nodes}
#SBATCH -c {nr_cores}
#SBATCH -t {walltime}
#SBATCH -o {tmp_dir}/{tmp_name}.%j.out
#SBATCH -e {tmp_dir}/{tmp_name}.%j.err
#SBATCH -J {job_name}
{account_spec}
{sources_loaded}
##cd "{cwd}"

if [ "{package_manager}" == "miniconda3" ] && [ -d "$HOME/miniconda3" ]
then
    # >>> conda initialize >>>
    # !! Contents within this block are managed by 'conda init' !!
    __conda_setup="$('$HOME/miniconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
    if [ $? -eq 0 ]; then
        eval "$__conda_setup"
    else
        if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
            . "$HOME/miniconda3/etc/profile.d/conda.sh"
        else
            export PATH="$HOME/miniconda3/bin:$PATH"
        fi
    fi
    unset __conda_setup
    # <<< conda initialize <<<
elif [ "{package_manager}" == "mambaforge" ] && [ -d "$HOME/mambaforge" ]
then
    # >>> conda initialize >>>
    # !! Contents within this block are managed by 'conda init' !!
    __conda_setup="$('$HOME/mambaforge/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
    if [ $? -eq 0 ]; then
        eval "$__conda_setup"
    else
        if [ -f "$HOME/mambaforge/etc/profile.d/conda.sh" ]; then
            . "$HOME/mambaforge/etc/profile.d/conda.sh"
        else
            export PATH="$HOME/mambaforge/bin:$PATH"
        fi
    fi
    unset __conda_setup

    if [ -f "$HOME/mambaforge/etc/profile.d/mamba.sh" ]; then
        . "$HOME/mambaforge/etc/profile.d/mamba.sh"
    fi
    # <<< conda initialize <<<
elif [ "{package_manager}" == "miniforge3" ] && [ -d "$HOME/miniforge3" ]
then
    # >>> conda initialize >>>
    # !! Contents within this block are managed by 'conda init' !!
    __conda_setup="$('$HOME/miniforge3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
    if [ $? -eq 0 ]; then
        eval "$__conda_setup"
    else
        if [ -f "$HOME/miniforge3/etc/profile.d/conda.sh" ]; then
            . "$HOME/miniforge3/etc/profile.d/conda.sh"
        else
            export PATH="$HOME/miniforge3/bin:$PATH"
        fi
    fi
    unset __conda_setup

    if [ -f "$HOME/miniforge3/etc/profile.d/mamba.sh" ]; then
        . "$HOME/miniforge3/etc/profile.d/mamba.sh"
    fi
    # <<< conda initialize <<<
elif [ "{package_manager}" == "anaconda3" ] && [ -d "$HOME/anaconda3" ]
then
    # >>> conda initialize >>>
    # !! Contents within this block are managed by 'conda init' !!
    __conda_setup="$('$HOME/anaconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
    if [ $? -eq 0 ]; then
        eval "$__conda_setup"
    else
        if [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
            . "$HOME/anaconda3/etc/profile.d/conda.sh"
        else
            export PATH="$HOME/anaconda3/bin:$PATH"
        fi
    fi
    unset __conda_setup
    # <<< conda initialize <<<
fi

{environment}
{ipcluster}
unset XDG_RUNTIME_DIR
jupyter {run} --ip=0.0.0.0 --no-browser --port={hostport} --ServerApp.iopub_data_rate_limit=10000000000
"""

# python script for monitoring memory usage
mem_script = """
import psutil
import os
import time
import sys

def str_to_mb(s):
    # compute mem in mb
    scale = s[-1].lower()
    assert scale in ['k', 'm', 'g']
    memory_per_cpu_mb = float(s[:-1])
    if scale == 'g':
        memory_per_cpu_mb *= 1024
    if scale == 'k':
        memory_per_cpu_mb /= 1024.0
    return memory_per_cpu_mb

def memory_status(max_proportion):

    used_mem, max_used_mem, reserved_mem = 0, 0, 0

    if {memory_per_cpu}: # #######
        reserved_mem = str_to_mb('{memory_per_cpu}') * {nr_cores} 
    else:
        reserved_mem = str_to_mb('{total_memory}')

    used_mem = -1
    for proc in psutil.process_iter():
        try:
            if '/job{job_id}/' in ' '. join(proc.cmdline()) and proc.username() == os.environ['USER']:            
                # print(proc.cmdline())
                used_mem = int(sum(c.memory_info().rss for c in proc.children(recursive=True)) ) / 1024**2
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    width = 40
    proportion = used_mem / reserved_mem
    max_proportion = max(proportion, max_proportion)
    n = int(round(proportion * width, 0))
    m = int(round(max_proportion * width, 0))

    # terminal colors
    BLUE = '\\033[94m' # added an extra \ to make literal escape chars
    RED = '\\033[91m'
    ENDC = '\\033[0m'

    n, m = m - (m - n), m - n
    bar = '[' + '=' * n + '-' * m + ' ' * (width - n - m) + ']'

    line = str(round(used_mem / 1024.0, 1)).rjust(6, ' ') + ' Gb ' + bar + str(round(reserved_mem / 1024.0, 1)) + ' Gb'
    if proportion < 0.8:
        color = BLUE
    else:
        color = RED
    return proportion, color + line + ENDC

max_proportion = 0
prev_proportion = 0
prev_time = 0
while True:
    time.sleep(5)
    try:
        max_proportion = max(prev_proportion, max_proportion)
        proportion, status_line = memory_status(max_proportion)
        max_interval = 5 * 60
        if abs(proportion - prev_proportion) > 0.1 or (time.time() - prev_time > max_interval):
            prev_proportion = proportion
            prev_time = time.time()
            print(status_line, file=sys.stdout)
            sys.stdout.flush()
    except UnboundLocalError:
        # This can happen when the function is interrupted halfway
        break
"""
