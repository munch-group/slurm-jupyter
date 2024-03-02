#!/usr/bin/env python

import subprocess
import sys
import os
import re
import time
import select
import selectors
import getpass
import webbrowser
import platform
import argparse
import signal
from textwrap import wrap
from distutils.version import LooseVersion
from packaging import version
from datetime import datetime

from subprocess import PIPE, Popen
from threading  import Thread, Event, Timer
import webbrowser

import shlex
import shutil

from colorama import init
init()

try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty  # python 3.x

from .templates import slurm_server_script, slurm_batch_script, mem_script
from .utils import execute, modpath, on_windows, str_to_mb, seconds2string, human2walltime

# global run event to communicate with threads
RUN_EVENT = None

# terminal colors
BLUE = '\033[94m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
ENDC = '\033[0m'

ON_POSIX = 'posix' in sys.builtin_module_names

# TODO: Use this instead?
# import selectors
# import subprocess
# import sys

# p = subprocess.Popen(
#     ["python", "random_out.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
# )

# sel = selectors.DefaultSelector()
# sel.register(p.stdout, selectors.EVENT_READ)
# sel.register(p.stderr, selectors.EVENT_READ)

# while True:
#     for key, _ in sel.select():
#         data = key.fileobj.read1().decode()
#         if not data:
#             exit()
#         if key.fileobj is p.stdout:
#             print(data, end="")
#         else:
#             print(data, end="", file=sys.stderr)


class StopServerException(Exception):
    pass

def check_for_conda_update():
    """Checks for a more recent conda version and prints a message.
    """
    cmd = 'conda search -c kaspermunch slurm-jupyter'
    cmd = shlex.split(cmd)
    cmd[0] = shutil.which(cmd[0])    
    conda_search = subprocess.check_output(cmd, shell=False).decode()
    newest_version = conda_search.strip().splitlines()[-1].split()[1]
    cmd = 'conda list -f slurm-jupyter'
    cmd = shlex.split(cmd)
    cmd[0] = shutil.which(cmd[0])    
    conda_search = subprocess.check_output(cmd, shell=False).decode()
    this_version = conda_search.strip().splitlines()[-1].split()[1]
    if LooseVersion(newest_version) > LooseVersion(this_version):
        msg = '\nA newer version of slurm-jupyter exists ({}). To update run:\n'.format(newest_version)
        msg += '\n\tconda install -c kaspermunch -c conda-forge slurm-jupyter={}\n'.format(newest_version)
        print(RED + msg + ENDC)


# Ask for confirmation on keyboard interrupt
def keyboard_interrupt_handler(signal, frame):
    """Intercepts KeyboardInterrupt and asks for confirmation.
    """
    # msg = BLUE+'\nAre you sure? y/n: '+ENDC
    # try:
    #     if input(msg) == 'y':
    #         raise KeyboardInterrupt
    # except RuntimeError: # in case user does Ctrl-C instead of y
    #     raise KeyboardInterrupt
    raise KeyboardInterrupt


def keyboard_interrupt_repressor(signal, frame):
    """For ignoring KeyboardInterrupt.
    """
    pass


def get_cluster_uid(spec):
    """Gets id of user on the cluster.

    Args:
        spec (dict): Parameter specification.

    Returns:
        int: User id.
    """
    cmd = shlex.split('ssh {user}@{frontend} id'.format(**spec))
    cmd[0] = shutil.which(cmd[0]) 
    process = Popen(
        cmd,
        shell=False,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    assert not process.returncode
    uid = int(re.search(r'uid=(\d+)', stdout).group(1))
    return uid


def submit_slurm_server_job(spec, verbose=False):
    """Submits slurm job that runs jupyter server.

    Args:
        spec (dict): Parameter specification.
        verbose (bool, optional): Verbose if True. Defaults to False.

    Returns:
        str: Slurm job id.
    """

    cmd = 'ssh {user}@{frontend} cat - > {tmp_dir}/{tmp_script} ; mkdir -p {tmp_dir} ; sbatch {tmp_dir}/{tmp_script} '.format(**spec)
        
    if verbose: print("script ssh transfer:", cmd, sep='\n')

    script = slurm_server_script.format(**spec)
    if verbose: print("slurm script:", script, sep='\n')

    script = script.encode()
    stdout, stderr = execute(cmd, stdin=script) # hangs until submission

    # get stdout and stderr and get jobid
    stdout = stdout.decode()
    stderr = stderr.decode()
    try:
        job_id = re.search(r'Submitted batch job (\d+)', stdout).group(1)
    except AttributeError:
        print(BLUE+'Slurm job submission failed'+ENDC)
        print(stdout)
        print(stderr)
        sys.exit()
    print(BLUE+log_prefix()+"Submitted slurm with job id:", job_id, ENDC)

    return job_id


def submit_slurm_batch_job(spec, verbose=False):
    """Submits slurm job that runs batch job.

    Args:
        spec (dict): Parameter specification.
        verbose (bool, optional): Verbose if True. Defaults to False.

    Returns:
        str: Slurm job id.
    """

    script = slurm_batch_script.format(**spec)
    if verbose: print("slurm script:", script, sep='\n')

    tmp_script_path = "{tmp_dir}/{tmp_script}".format(**spec)
    with open(tmp_script_path, 'w') as f:
        f.write(script)

    cmd = 'sbatch {tmp_dir}/{tmp_script} '.format(**spec)
    if verbose: print("command:", cmd, sep='\n')

    stdout, stderr = execute(cmd, shell=False) # hangs until submission

    # get stdout and stderr and get jobid
    stdout = stdout.decode()
    stderr = stderr.decode()
    try:
        job_id = re.search(r'Submitted batch job (\d+)', stdout).group(1)
    except AttributeError:
        print('Slurm job submission failed')
        print(stdout)
        print(stderr)
        sys.exit()
    print("Submitted slurm with job id:", job_id)

    return job_id


def wait_for_job_allocation(spec, verbose=False):
    """Waits for slurm job to run.

    Args:
        spec (dict): Parameter specification.
        verbose (bool, optional): Verbose if True. Defaults to False.

    Returns:
        str: Id of node running job.
    """
    # wait a bit to make sure jobinfo database is updated
    time.sleep(20)

    regex = re.compile(r'(s\d+n\d+|cn-\d+)')
    cmd = 'ssh {user}@{frontend} squeue --noheader --format %N -j {job_id}'.format(**spec)
    if verbose: print(cmd)
    stdout, stderr = execute(cmd)
    stdout = stdout.decode()
    m = regex.search(stdout)

    while not m or m.group(1) == 'None':
        time.sleep(10)
        if verbose: print(cmd)
        stdout, stderr = execute(cmd)
        stdout = stdout.decode()
        m = regex.search(stdout)
    node_id = m.group(1)
    if verbose: print(stdout)
    
    # cmd = 'ssh {user}@{frontend} squeue --noheader --format %N -j {job_id}'.format(**spec)        
    # stdout, stderr = execute(cmd)
    # stdout = stdout.decode()
    # node_id = stdout.strip()

    # while not node_id: #not m or m.group(1) == 'None':
    #     time.sleep(10)
    #     stdout, stderr = execute(cmd)
    #     stdout = stdout.decode()
    #     # m = regex.search(stdout)
    #     node_id = stdout.strip()
    # if verbose: print(stdout)

    # node_id = m.group(1)
    return node_id


def enqueue_output(out, queue):
    """Enqueues output from stream.

    Args:
        out (io.TextIOWrapper): Input stream.
        queue (Queue.Queue): The queue to add input from stream to.
    """
    while RUN_EVENT.is_set():
        for line in iter(out.readline, b''):
            queue.put(line)
        time.sleep(.1)


def open_output_connection(cmd, spec):
    """Opens connection to stdout of a command and makes a thread where output is enqueued.

    Args:
        cmd (str): Command.
        spec (dict): Parameter specification.

    Returns:
        (subprocess.Popen, threading.Thread, Queue.Queue): Process, Thread and Queue.
    """      
    # p = Popen(cmd.split(), stdout=PIPE, stderr=PIPE, bufsize=0, close_fds=ON_POSIX)
    cmd = shlex.split(cmd)
    cmd[0] = shutil.which(cmd[0])     
    p = Popen(cmd, shell=False, stdout=PIPE, stderr=PIPE, bufsize=0, close_fds=ON_POSIX)
    q = Queue()
    t = Thread(target=enqueue_output, args=(p.stdout, q))
    t.daemon = True # thread dies with the program
    t.start()
    return p, t, q


def open_jupyter_stdout_connection(spec, verbose=False):
    """Opens connection to stdout of a to a tail command on the cluster reading stdout from jupyter. 
    Makes a thread where output is enqueued.

    Args:
        cmd (str): Command.
        spec (dict): Parameter specification.

    Returns:
        (subprocess.Popen, threading.Thread, Queue.Queue): Process, Thread and Queue.
    """

    file_created = False
    cmd = 'ssh -q {user}@{frontend} [[ -f {tmp_dir}/{tmp_name}.{job_id}.out ]] && echo "File exists"'.format(**spec)
    while not file_created:
        if verbose: print("testing existence:", cmd)
        stdout, stderr = execute(cmd, check_failure=False)
        if "File exists" in stdout.decode():
            file_created = True
        else:
            time.sleep(10)

    # cmd = "ssh {user}@{frontend} 'tail --pid=`ps -o ppid= $$` -F -n +1 {tmp_dir}/{tmp_name}.{job_id}.out'".format(**spec)
    cmd = "ssh {user}@{frontend} 'tail -F -n +1 {tmp_dir}/{tmp_name}.{job_id}.out'".format(**spec)

    if verbose: print("jupyter stdout connection:", cmd)
    return open_output_connection(cmd, spec)


def open_jupyter_stderr_connection(spec, verbose=False):
    """Opens connection to stderr of a to a tail command on the cluster reading stderr from jupyter. 
    Makes a thread where output is enqueued.

    Args:
        cmd (str): Command.
        spec (dict): Parameter specification.

    Returns:
        (subprocess.Popen, threading.Thread, Queue.Queue): Process, Thread and Queue.
    """

    file_created = False
    cmd = 'ssh -q {user}@{frontend} [[ -f {tmp_dir}/{tmp_name}.{job_id}.err ]] && echo "File exists"'.format(**spec)
    while not file_created:
        if verbose: print("testing existence:", cmd)
        stdout, stderr = execute(cmd, check_failure=False)
        if "File exists" in stdout.decode():
            file_created = True
        else:
            time.sleep(10)

    # cmd = "ssh {user}@{frontend} 'tail --pid=`ps -o ppid= $$` -F -n +1 {tmp_dir}/{tmp_name}.{job_id}.err'".format(**spec)
    cmd = "ssh {user}@{frontend} 'tail -F -n +1 {tmp_dir}/{tmp_name}.{job_id}.err'".format(**spec)

    if verbose: print("jupyter stderr connection:", cmd)
    return open_output_connection(cmd, spec)


def open_memory_stdout_connection(spec, verbose=False):
    """Opens connection to stdout from python script on the cluster producing memory status.
    Makes a thread where output is enqueued.

    Args:
        cmd (str): Command.
        spec (dict): Parameter specification.

    Returns:
        (subprocess.Popen, threading.Thread, Queue.Queue): Process, Thread and Queue.
    """     
    # cmd = 'ssh {user}@{frontend} "echo \\\"trap \\\'kill -HUP $(jobs -lp) 2>/dev/null || true\\\' exit; ssh {user}@{node} python {tmp_dir}/mem_jupyter.py\\\" > {tmp_dir}/{tmp_name}.{job_id}.mem.sh"'.format(**spec)
    # cmd = 'ssh {user}@{frontend} "echo \\\"trap \\\'kill -HUP -$$\\\' exit; ssh {user}@{node} python {tmp_dir}/mem_jupyter.py\\\" > {tmp_dir}/{tmp_name}.{job_id}.mem.sh"'.format(**spec)
    # cmd = 'ssh {user}@{frontend} "echo \\\"trap \\\'kill -9 $(ps -s $$ -o pid=)\\\' exit; ssh {user}@{node} python {tmp_dir}/mem_jupyter.py\\\" > {tmp_dir}/{tmp_name}.{job_id}.mem.sh"'.format(**spec)
    # cmd = 'ssh {user}@{frontend} "bash {tmp_dir}/{tmp_name}.{job_id}.mem.sh"'.format(**spec)
    # cmd = 'ssh -t -t {user}@{frontend} ssh {user}@{node} python {tmp_dir}/mem_jupyter.py'.format(**spec)
    cmd = 'ssh {user}@{frontend} ssh {user}@{node} conda run -n {environment_name} --no-capture-output python {tmp_dir}/mem_jupyter.py'.format(**spec)

    if verbose: print("memory stdout connection:", cmd)
    return open_output_connection(cmd, spec)


def open_port(spec, verbose=False):
    """Opens port to cluster node so that Jupyter is forwarded to localhost.

    Args:
        spec (dict): Parameter specification.
        verbose (bool, optional): Verbose if True. Defaults to False.

    Returns:
        (subprocess.Popen, threading.Thread, Queue.Queue): Process, Thread and Queue.
    """
    cmd = 'ssh -L {port}:{node}:{hostport} {user}@{frontend}'.format(**spec)
    if verbose: print("forwarding port:", cmd)
    cmd = shlex.split(cmd)
    cmd[0] = shutil.which(cmd[0])        
    port_p = Popen(cmd, shell=False, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    # we have to set stdin=PIPE even though we eodn't use it because this
    # makes sure the process does not inherrit stdin from the parent process (this).
    # Otherwise signals are sent to the process and not to the python script

    # TODO: Make some kind of check to make sure the port forwarding is working
    # MAC:
    # lsof -i -P | grep LISTEN 
    # Linux:
    # netstat -a | grep LISTEN

    port_q = Queue()
    port_t = Thread(target=enqueue_output, args=(port_p.stderr, port_q))
    port_t.daemon = True # thread dies with the program
    port_t.start()
    return port_p, port_t, port_q


def open_browser(spec, force_chrome=False):
    """Opens default browser on localhost and port.

    Args:
        spec (dict): Parameter specification.
    """
    if not spec['url']:
        spec['url'] = 'https://localhost:{port}'.format(**spec)
    if platform.platform().startswith('Darwin') or platform.platform().startswith('macOS-'):
        chrome_path = r'open -a /Applications/Google\ Chrome.app %s'
        if force_chrome and os.path.exists('/Applications/Google Chrome.app'):
            webbrowser.get(chrome_path).open(spec['url'], new=2)
        else:
            webbrowser.open(spec['url'], new=2)
    elif platform.platform().startswith('Windows'):
        chrome_path = 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe %s'
        if force_chrome and os.path.exists(os.path.abspath(os.path.join(os.sep, 'Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe'))):
            webbrowser.get(chrome_path).open(spec['url'], new=2)
        else:
            webbrowser.open(spec['url'], new=2)
    else:
        chrome_path = '/usr/bin/google-chrome %s'
        if force_chrome and os.path.exists('/usr/bin/google-chrome'):
            webbrowser.get(chrome_path).open(spec['url'], new=2)
        else:
            webbrowser.open(spec['url'], new=2)

# TODO: make a check of jupyter lab version and give a user warning or abort if it is not 3
def check_jupyterlab_version(spec):
    """Check that jupyter lab version is >=3

    Args:
        spec (dict): Parameter specification.

    Returns:
        bool: whether version is 3
    """
    cmd = 'ssh {user}@{frontend} "conda activate simons_jupyter && conda list | grep grep \"jupyterlab \""'.format(**spec)
    cmd = shlex.split(cmd)
    cmd[0] = shutil.which(cmd[0])    
    process = Popen(
        cmd,
        shell=False,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    assert not process.returncode
    name, version, package = stdout.split()
    return version.parse(version) >= version.parse("3.0.0")

def transfer_memory_script(spec, verbose=False):
    """Transvers the a python script to the cluster, which monitors memory use on the node.

    Args:
        spec (dict): Parameter specification.
        verbose (bool, optional): Verbose if True. Defaults to False.
    """
    script = mem_script.format(**spec)

    # cmd = 'ssh {user}@{frontend} cat - > {tmp_dir}/{mem_script} ; mkdir -p {tmp_dir}'.format(**spec)
    cmd = 'ssh {user}@{frontend} cat - > {tmp_dir}/{mem_script} ; mkdir -p {tmp_dir}'.format(**spec)
        
    if verbose: print("memory script:", script, sep='\n')

    script = script.encode()
    stdout, stderr = execute(cmd, stdin=script) # hangs untill submission


def add_slurm_arguments(parser):
    """Adds slurm-relevant command line arguments to parser.

    Args:
        parser (argparse.ArgumentParser): Argument parser to add arguments to.
    """
    parser.add_argument("-c", "--cores",
                    dest="cores",
                    type=int,
                    default=1,
                    help="Number of cores. For multiprocessing or for running more than one notebook simultaneously.")
    parser.add_argument("-t", "--time",
                    dest="time",
                    type=str,
                    default="05:00:00",
                    help="Max wall time. specify as HH:MM:SS (or any other format supported by the cluster). The jupyter server is killed automatically after this time.")

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--memory-per-cpu",
                    dest="memory_per_cpu",
                    type=str,
                    help="Max memory for each core in gigabytes or megabytes e.g. 4g or 50m")
    group.add_argument("-m", "--total-memory",
                    dest="total_memory",
                    type=str,
                    default='8g',
                    help="Max memory total for all cores in gigabytes or megabytes . e.g. 4g or 50m") 

    parser.add_argument("-n", "--nodes",
                    dest="nodes",
                    type=int,
                    default=1,
                    help="Number of nodes (machines) to allocate.")
    parser.add_argument("-q", "--queue",
                    dest="queue",
                    type=str,
                    choices=['short', 'normal', 'express', 'fat2', 'gpu'],
                    default="normal",
                    help="Cluster queue to submit to.")
    parser.add_argument("-N", "--name",
                    dest="name",
                    type=str,
                    default="nn",
                    help="Name prefix of job. Only needed if you run multiple servers and want to be able to recognize a particular one in the cluster queue.")
    parser.add_argument("-u", "--user",
                    dest="user",
                    type=str,
                    default=getpass.getuser(),
                    help="User name on the cluster. Only needed if your user name on the cluster is different from the one you use on your own computer.")
    parser.add_argument("-e", "--environment",
                    dest="environment",
                    type=str,
                    default='',
                    # required=True,                    
                    help="Conda environment to run jupyter in.")
    parser.add_argument("-A", "--account",
                    dest="account",
                    type=str,
                    default=None,
                    help="Account/Project to run under. This is typically the name of the shared folder you work in. Not specifying an account decreases your priority in the cluster queue.")
    parser.add_argument("-f", "--frontend", 
                    dest="frontend", 
                    type=str, 
                    default="login.genome.au.dk", 
                    help="URL to cluster frontend.")
    parser.add_argument("--ipcluster",
                    dest="ipcluster",
                    action='store_true',
                    default=False,
                    help="Start an ipcluster")                    


def log_prefix():
    return f'[I {str(datetime.now())[:-3]} SlurmJptr] '

def slurm_jupyter():
    """Command line script for use on a local machine. Runs and connects to a jupyter server on a slurm node.
    """ 

    description = """
    The script handles everything required to run jupyter on the cluster but show the notebook or jupyterlab 
    in your local browser."""

    not_wrapped = """See github.com/kaspermunch/slurm_jupyter for documentation and common use cases."""

    description = "\n".join(wrap(description.strip(), 80)) + "\n\n" + not_wrapped

    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                        description=description)

    add_slurm_arguments(parser)                  

    parser.add_argument("--run", 
                    dest="run", 
                    type=str, 
                    choices=['notebook', 'lab'],
                    default='lab',
                    help="URL to cluster frontend.")
    parser.add_argument("--port",
                    dest="port",
                    type=int,
                    default=None,
                    help="Local port for port forwarding")
    parser.add_argument("--hostport",
                    dest="hostport",
                    type=int,
                    default=None,
                    help="Remote port (on the cluster) for port forwarding")
    parser.add_argument("--timeout",
                    dest="timeout",
                    default=0.1,
                    type=float,
                    help="Time out in seconds for cross thread operations")
    parser.add_argument("-C", "--chrome",
                    dest="chrome",
                    action='store_true',
                    help="View in Chrome if available (ignoring default browser)")                    
    parser.add_argument("-v", "--verbose",
                    dest="verbose",
                    action='store_true',
                    help="Print debugging information")
    parser.add_argument("-a", "--attach",
                    dest="attach",
                    action='store_true',
                    help="Slurm job id of running jupyter server")
    parser.add_argument("-j", "--slurm-jobid",
                    dest="slurm_jobid",
                    type=int,
                    default=None,
                    help="Slurm job id of running jupyter server")
    parser.add_argument("-s", "--skip-port-check",
                    dest="skip_port_check",
                    action='store_true',
                    help="Skip searching for an available port. Saves time when only running a single instance.")

    args = parser.parse_args()

    if args.nodes != 1:
        print("Multiprocessing across multiple nodes not supported yet - sorry")
        sys.exit()

    if args.time[-1] in 'smhdSMHD':
        unit = args.time[-1].lower()
        value = int(args.time[:-1])
        args.time = human2walltime(**{unit:value})
    elif not re.match(r'(\d+-)?\d+:\d+:\d+', args.time):
        print("Wrongly formatted walltime spec:", args.time)

    spec = {'user': args.user,
            'port': args.port,
            'environment': "\nconda activate " + args.environment,
            'environment_name': args.environment,
            'run': args.run,
            'walltime': args.time,
            'account': args.account,
            'queue': args.queue,
            'nr_nodes': args.nodes,
            'nr_cores': args.cores,
            'memory_per_cpu': args.memory_per_cpu,
            'total_memory': args.total_memory,
            'cwd': os.getcwd(),
            'sources_loaded': '',
            'mem_script': 'mem_jupyter.py',
            'tmp_script': 'slurm_jupyter_{}.sh'.format(int(time.time())),
            'tmp_name': 'slurm_jupyter',
            'tmp_dir': '.slurm_jupyter',
            'frontend': args.frontend,
            'hostport': args.hostport,
            'job_name': "sjup_{}_{}_{}_{}".format(args.name, getpass.getuser(), args.environment, int(time.time())),
            'job_id': None,
            'url': None}

    check_for_conda_update()

    # test ssh connection:
    cmd = 'ssh -q {user}@{frontend} exit'.format(**spec)
    if args.verbose: print(cmd)
    cmd = shlex.split(cmd)
    cmd[0] = shutil.which(cmd[0])  
    process = subprocess.Popen(
        cmd,
        shell=False,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode:
        print("Cannot make ssh connection: {user}@{frontend}".format(**spec))
        sys.exit()

    if not args.attach:
        # check environment exists on the cluster:
        cmd = r'''ssh kmt@login.genome.au.dk "conda info --envs | grep '{environment_name}\s'"'''.format(**spec)
        if args.verbose: print(cmd)
        stdout, stderr = execute(cmd)
        if args.verbose: print(stdout.decode())
        if not args.attach:
            if stdout.decode().split()[0] != spec['environment_name']:
                print("Specified environment {environment_name} was not found at {user}@{frontend}".format(**spec))
                sys.exit()

        # get environment manager:
        cmd = r"""ssh -q {user}@{frontend} 'conda info --envs | sed -n "s/^base\s*\**\s*\/home\/$USER\/\(.*\)/\\1/p"' """.format(**spec)
        if args.verbose: print(cmd)
        process = subprocess.Popen(
            cmd,
            shell=True,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if process.returncode:
            print("Cannot identify cluster package mannager.")

            print("Cannot make ssh connection: {user}@{frontend}".format(**spec))
            sys.exit()
        else:
            spec['package_manager'] = stdout.strip()

        # in case the cluster bash string comes back with profile formatting around the manager name
        for manager in ['miniconda3', 'anaconda3', 'miniforge3', 'mambaforge']:
            if manager in spec['package_manager']:
                spec['package_manager'] = manager

        if not spec['package_manager'] or spec['package_manager'] not in ['miniconda3', 'anaconda3', 'miniforge3', 'mambaforge']:
            print("Conda package manager should be either miniconda3, anaconda3, miniforge3, or mambaforge.")
            sys.exit()

        # TODO: test port check and make sure it works
        if spec['port'] is None and spec['hostport'] is None and not args.skip_port_check:
            spec['port'] = get_cluster_uid(spec)        
            if sys.platform == "darwin":
                cmd = f"lsof -i -P | grep LISTEN"           
                if args.verbose: print(cmd)
                stdout, stderr = execute(cmd, shell=True, check_failure=False)
                stdout = stdout.decode()
                for port_bump in range(10):
                    if args.verbose: print(f"Checking if port {spec['port']} is free")
                    if f"localhost:{spec['port']}" not in stdout:
                        # port not in use
                        break
                    else:
                        spec['port'] += 1
                if port_bump:
                    print(BLUE+log_prefix()+f"Default port {spec['port']-port_bump} in busy. Using port {spec['port']}"+ENDC)

        if spec['hostport'] is None:
            spec['hostport'] = spec['port']

        # tup = spec['walltime'].split('-')
        # if len(tup) == 1:
        #     days, (hours, mins, secs) = 0, tup[0].split(':')
        # else:
        #     days, (hours, mins, secs) = tup[0], tup[1].split(':')
        # end_time = int(time.time()) + int(days) * 86400 + int(hours) * 3600 + int(mins) * 60 + int(secs)

        spec['gres'] = ''
        if args.queue == 'gpu':
            spec['gres'] = '#SBATCH --gres=gpu:1'
            
        if args.total_memory:
            spec['memory_spec'] = '#SBATCH --mem {}'.format(int(str_to_mb(args.total_memory)))
        else:
            spec['memory_spec'] = '#SBATCH --mem-per-cpu {}'.format(int(str_to_mb(args.memory_per_cpu)))

        # if args.environment:
        #     spec['environment'] = "\nconda activate " + args.environment
        #     spec['environment_name'] = args.environment

        if args.ipcluster:
            spec['ipcluster'] = "ipcluster start -n {} &".format(args.cores)
        else:   
            spec['ipcluster'] = ''

        if args.account:
            spec['account_spec'] = "#SBATCH -A {}".format(args.account)
        else:
            spec['account_spec'] = ""


    # incept keyboard interrupt with user prompt
    signal.signal(signal.SIGINT, keyboard_interrupt_handler)

    try:

        # event to communicate with threads (except memory thread)
        global RUN_EVENT
        RUN_EVENT = Event()
        RUN_EVENT.set()

        if args.attach:
            # populate spec

            if args.slurm_jobid:
                spec['job_id'] = args.slurm_jobid
            else:
                cmd = 'ssh {user}@{frontend} sacct -X --noheader --state=RUNNING --format="jobid,jobname%50"'.format(**spec)
                if args.verbose: print(cmd)
                stdout, stderr = execute(cmd)
                for line in stdout.decode().split('\n'):
                    if line:
                        job_id, job_name = line.split()
                        match = re.match(r'sjup_([^_]+)_([^_]+)_([^_]+)_\d+', job_name)
                        if match:
                            spec['name'], spec['user'], spec['environment_name'] = match.groups()
                            spec['job_id'] = job_id
                            break
            if not spec['job_id']:
                print("No running jupyter server found")
                sys.exit()

            cmd = 'ssh {user}@{frontend} sacct -X --noheader --state=RUNNING --format="jobid,NodeList,jobname%30,ReqMem,ReqCPUS,Account%30,time" | grep {job_id}'.format(**spec)
            if args.verbose: print(cmd)
            stdout, stderr = execute(cmd)
            (spec['job_id'], spec['node'], spec['job_name'], spec['total_memory'], 
                spec['cores'], spec['account'], spec['walltime']) = stdout.decode().split()

            # get active port on host
            cmd = """ssh {user}@{frontend} "ssh {node} 'lsof -i -P | grep LISTEN'" """.format(**spec)
            if args.verbose: print(cmd)
            stdout, stderr = execute(cmd)
            for line in stdout.decode().split('\n'):
                if line.startswith("jupyter"):
                    spec['hostport'] = re.search(r':(\d+) \(LISTEN\)', line).group(1)
                    if args.verbose: print('Found hostport:', spec['hostport'])
                    break

        else:
            spec['job_id'] = submit_slurm_server_job(spec, verbose=args.verbose)
            print(BLUE+log_prefix()+'Waiting for slurm job allocation'+ENDC)

            spec['node'] = wait_for_job_allocation(spec, verbose=args.verbose)
            print(BLUE+log_prefix()+'Compute node(s) allocated:', spec['node'], ENDC)

            assert spec['node']
            print(BLUE+log_prefix()+'Jupyter server: (to stop the server press Ctrl-C)'+ENDC)

            time.sleep(5)

        tup = spec['walltime'].split('-')
        if len(tup) == 1:
            days, (hours, mins, secs) = 0, tup[0].split(':')
        else:
            days, (hours, mins, secs) = tup[0], tup[1].split(':')
        end_time = int(time.time()) + int(days) * 86400 + int(hours) * 3600 + int(mins) * 60 + int(secs)

        # open connections to stdout and stderr from jupyter server
        stdout_p, stdout_t, stdout_q = open_jupyter_stdout_connection(spec, verbose=args.verbose)
        stderr_p, stderr_t, stderr_q = open_jupyter_stderr_connection(spec, verbose=args.verbose)

        # open connections to stdout from memory monitoring script
        transfer_memory_script(spec, verbose=args.verbose)
        mem_stdout_p, mem_stdout_t, mem_stdout_q = open_memory_stdout_connection(spec, verbose=args.verbose)

        # # start thread monitoring memory usage
        # mem_print_t = StoppableThread(target=memory_monitor, args=[spec])
        # mem_print_t.daemon = True # thread dies with the program
        # mem_print_t.start()

        while True:

            # stop to cleanup before slurm cancels the job
            if end_time - int(time.time()) < 30:
                print('\n'+RED+log_prefix()+'Scheduled slurm job expires in 30 sec. Stopping server.'+ENDC)
                raise StopServerException

            while True:
                try:  
                    line = stdout_q.get(timeout=args.timeout)#get_nowait()
                except Empty:
                    break
                else:
                    line = line.decode()
                    line = line.replace('\r', '\n')
                    print(line, end="")

            while True:
                try:  
                    mem_line = mem_stdout_q.get(timeout=args.timeout)#get_nowait()
                except Empty:
                    break
                else:
                    mem_line = mem_line.decode().strip() 
                    secs_left = end_time - int(time.time())
                    color = secs_left > 600 and BLUE or RED
                    mem_line += '  '+color+'Time: '+seconds2string(secs_left)+ENDC
                    mem_line = color+log_prefix()+ENDC + mem_line
                    print(mem_line)

                    # if secs_left <= 5*60:
                    #     stdout, stderr = execute('ssh {user}@{frontend} pkill -9 -f "tail -F -n +1 {tmp_dir}/{tmp_name}.{job_id}"'.format(**spec))

            while True:
                try:  
                    line = stderr_q.get(timeout=args.timeout)#get_nowait()
                except Empty:
                    break
                else:
                    line = line.decode()
                    line = line.replace('\r', '\n')
                    if 'SSLV3_ALERT_CERTIFICATE_UNKNOWN' not in line: # skip warnings about SSL certificate
                        print(line, end="")

                    if re.search(r'Jupyter Notebook[\d. ]+is running', line) or re.search(r'Jupyter Server[\d. ]+is running', line):
                        port_p, port_t, port_q = open_port(spec, verbose=args.verbose)
                        token_url = None # server is runing, we now look for a token url

                    # look for the token url
                    m = re.search(r'https?://127.0.0.1\S+', line)
                    if m and not token_url:
                        token_url = m.group(0)
                        spec['url'] = token_url
                        open_browser(spec, force_chrome=args.chrome)
                        prefix = log_prefix()
                        print(BLUE+prefix+'Your browser may complain that the connection is not private.\n',
                                   prefix+' In Safari, you can proceed to allow this. In Chrome, you need"\n',
                                   prefix+' to simply type the characters "thisisunsafe" while in the Chrome window.\n',
                                   prefix+' Once ready, jupyter may ask for your cluster password.'+ENDC, sep='')

                    # in case we missed the token url
                    m = re.search(r'Use Control-C to stop this server', line)
                    # if m and not token_url:
                    #     open_browser(spec, force_chrome=args.chrome)
                    #     prefix = log_prefix()
                    #     print(BLUE+prefix+'Your browser may complain that the connection is not private.\n',
                    #                prefix+' In Safari, you can proceed to allow this. In Chrome, you need"\n',
                    #                prefix+' to simply type the characters "thisisunsafe" while in the Chrome window.\n',
                    #                prefix+' Once ready, jupyter may ask for your cluster password.'+ENDC, sep='')

                    if "CANCELLED" in line:
                        print('\n'+RED+log_prefix()+'Scheduled slurm job cancelled.'+ENDC)
                        raise StopServerException  

                    if "EnvironmentNameNotFound" in line:
                        print('\n'+RED+log_prefix()+'Specified environment does not exist.'+ENDC)
                        raise StopServerException  
                                   
    except StopServerException:

        # not possible to do Keyboard interrupt from here on out
        signal.signal(signal.SIGINT, keyboard_interrupt_repressor)

        # TODO: Double Ctrl-C bypasses canceling of slurm job

        try:
            RUN_EVENT.clear()
            time.sleep(1)

            port_p.kill()
            port_t.join()
        except:
            pass

        try:
            stdout_p.kill() 
            stdout_t.join()
        except:
            pass

        try:
            stderr_p.kill()
            stderr_t.join()
        except:
            pass
            
        try:
            mem_stdout_p.kill()
            mem_stdout_t.join()
            # mem_print_t.stop()
            # mem_print_t.join()
        except:
            pass

        if args.attach:
            print(BLUE+'\nDetached from jupyter server'+ENDC)
        else:
            print(BLUE+'\nCanceling slurm job running jupyter server'+ENDC)
            cmd = 'ssh {user}@{frontend} scancel {job_id}'.format(**spec)
            if args.verbose: print(cmd)
            stdout, stderr = execute(cmd, check_failure=False)
            sys.exit()

    except KeyboardInterrupt:

        # not possible to do Keyboard interrupt from here on out
        signal.signal(signal.SIGINT, keyboard_interrupt_repressor)

        # TODO: Double Ctrl-C bypasses canceling of slurm job

        # in try statements because these variables may not be defined at keyboard interrupt:
        try:
            RUN_EVENT.clear()
            time.sleep(1)

            port_p.kill()
            port_t.join()
        except:
            pass

        try:
            stdout_p.kill() 
            stdout_t.join()
        except:
            pass

        try:
            stderr_p.kill()
            stderr_t.join()
        except:
            pass
            
        try:
            mem_stdout_p.kill()
            mem_stdout_t.join()
            # mem_print_t.stop()
            # mem_print_t.join()
        except:
            pass

        if args.attach:
            print(BLUE+'\nDetached from jupyter server'+ENDC)
        else:
            print(BLUE+'\nCanceling slurm job running jupyter server'+ENDC)
            cmd = 'ssh {user}@{frontend} scancel {job_id}'.format(**spec)
            if args.verbose: print(cmd)
            stdout, stderr = execute(cmd, check_failure=False)
            sys.exit()


def slurm_nb_run():
    """Command line script for use on the cluster. Executes notebooks on a slurm node. 
    E.g. to execute one or more notebooks inplace on a slurm node:

        slurm-nb-run --inplace notebook1.ipynb, notebook2.ipynb

    To create and execute one or more notebooks with two different sets of parameters 
    (param1.py and param2.py):

        slurm-nb-run --spike param1.py --spike param2.py notebook1.ipynb, notebook2.ipynb
    """

    description = """
    The script executes a notebook on the cluster"""

    not_wrapped = """See github.com/kaspermunch/slurm_jupyter_run for documentation and common use cases."""

    description = "\n".join(wrap(description.strip(), 80)) + "\n\n" + not_wrapped

    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                        description=description)

    # TODO: make sure this only shares common  arguments
    add_slurm_arguments(parser)                  

    # nbconvert arguments
    parser.add_argument("--timeout",
                    dest="timeout",
                    type=int,
                    default='-1',
                    help="Cell execution timeout in seconds. Default -1. No timeout.")
    parser.add_argument("--allow-errors",
                    dest="allow_errors",
                    action='store_true',
                    help="Allow errors in cell executions.")
    parser.add_argument("--format",
                    dest="format",
                    choices=['notebook', 'html', 'pdf'],
                    default='notebook',
                    help="Output format.") 
    parser.add_argument("--inplace",
                    dest="inplace",
                    action='store_true',
                    help="Output format.")
    # parser.add_argument("--cleanup",
    #                 dest="cleanup",
    #                 action='store_true',
    #                 help="Removes un-executed notebooks generated using --spike and format other than 'notebook'")                           

    parser.add_argument("-s", "--spike",
                    dest="spike",
                    action='append',
                    help="Adds a cell loading python code from file")       
    parser.add_argument("-r", "--replace-run-magic",
                    dest="replace_first_run_magic",
                    action='store_true',
                    help="Replace first cell with a %%run magic instead of just adding a top %%run magic cell") 

    parser.add_argument("-v", "--verbose",
                    dest="verbose",
                    action='store_true',
                    help="Print debugging information")

    parser.add_argument('notebooks', nargs='*')

    args = parser.parse_args()


    if args.nodes != 1:
        print("Multiprocessign across multiple nodes not supported yet - sorry")
        sys.exit()

    if args.inplace and args.format != 'notebook':
        print('Only not use --inplace with other formats than "notebook" format')
        sys.exit()

    # if args.cleanup and not args.spike:
    #     print("Only use --cleanup with --spike")
    #     sys.exit()

    home = os.path.expanduser("~")

    if args.time[-1] in 'smhdSMHD':
        unit = args.time[-1].lower()
        value = int(args.time[:-1])
        args.time = human2walltime(**{unit:value})
        
    spec = {'environment': args.environment,
            'walltime': args.time,
            'account': args.account,
            'queue': args.queue,
            'nr_cores': args.cores,
            'nr_nodes': args.nodes,
            'cwd': os.getcwd(),
            'sources_loaded': '',
            'slurm': 'source /com/extra/slurm/14.03.0/load.sh',
            'tmp_name': 'slurm_jupyter_run',
            'tmp_dir': home+'/.slurm_jupyter_run',
            'tmp_script': 'slurm_jupyter_run_{}.sh'.format(int(time.time())),
            'job_name': args.name,
            'job_id': None,
            'timeout': args.timeout,
            'format': args.format,
            'inplace': args.inplace,
            }

    if not os.path.exists(spec['tmp_dir']):
        os.makedirs(spec['tmp_dir'])

    tup = spec['walltime'].split('-')
    if len(tup) == 1:
        days, (hours, mins, secs) = 0, tup[0].split(':')
    else:
        days, (hours, mins, secs) = tup[0], tup[1].split(':')
    end_time = time.time() + int(days) * 86400 + int(hours) * 3600 + int(mins) * 60 + int(secs)

    if args.total_memory:
        spec['memory_spec'] = '#SBATCH --mem {}'.format(int(str_to_mb(args.total_memory)))
    else:
        spec['memory_spec'] = '#SBATCH --mem-per-cpu {}'.format(int(str_to_mb(args.memory_per_cpu)))

    if args.environment:
        spec['environment'] = "\nsource activate " + args.environment
        spec['environment_name'] = args.environment

    if args.account:
        spec['account_spec'] = "#SBATCH -A {}".format(args.account)
    else:
        spec['account_spec'] = ""

    if args.ipcluster:
        spec['ipcluster'] = "ipcluster start -n {} &".format(args.cores)
    else:   
        spec['ipcluster'] = ''


    if args.allow_errors:
        spec['allow_errors'] = '--allow-errors'
    else:
        spec['allow_errors'] = ''

    if args.inplace or args.spike and args.format == 'notebook':
        spec['inplace'] = '--inplace'
    else:
        spec['inplace'] = ''

    nbconvert_cmd = "jupyter nbconvert --ClearOutputPreprocessor.enabled=True --ExecutePreprocessor.timeout={timeout} {allow_errors} {inplace} --to {format} --execute {notebook}"

    notebook_list = args.notebooks

    import nbformat


    # TODO: submit jobs trough GWF Do the whole thing in a tmp dir and only cp
    # back to the destination as last command so that we do not get notebooks
    # that are not run

    # make a template that runs one notebook

    from gwf import Workflow, AnonymousTarget

    gwf = Workflow(defaults={'account': args.account})

    def run_workflow(workflow):
        from gwf.backends import Backend
        from gwf.core import Graph, Scheduler
        from gwf.conf import config
        for t in workflow.targets.values():
            print(t)
        graph = Graph.from_targets(workflow.targets)
        backend_cls = Backend.from_name('slurm')

        with backend_cls() as backend:
            scheduler = Scheduler(graph=graph, backend=backend, dry_run=False)
            scheduler.schedule_many(list(graph))

    def nbconvert(notebook_file_name, output_file, dependencies=[], inplace=False, 
                  output_format='notebook', allow_errors=False, timeout=-1):
        inputs = dependencies
        outputs = [output_file]
        options = {
            'cores': args.cores,
            'memory': args.total_memory,
        }

        if allow_errors:
            allow_errors = '--allow-errors'
        else:
            allow_errors = ''

        if inplace:
            inplace = '--inplace'
        else:
            inplace = ''

        spec = f'''
        cp {notebook_file_name} $TMPDIR/`basename {notebook_file_name}` && \
        nbconvert_cmd = "jupyter nbconvert --ClearOutputPreprocessor.enabled=True \
            --ExecutePreprocessor.timeout={timeout} {allow_errors} {inplace and '--allow-errors' or ''} \
                --to {output_format} --execute {notebook_file_name}" && \
        cp $TMPDIR/`basename {notebook_file_name}` {output_file}
        '''

        return AnonymousTarget(inputs=inputs, outputs=outputs, options=options, spec=spec)




    if not args.spike:
        dependencies = []
        for notebook in notebook_list:
            gwf.target_from_template(
                name=modpath(notebook, parent=''),
                template=nbconvert(
                    notebook_file_name=notebook,
                    dependencies=dependencies,
                    inplace=True,
                    allow_errors=False, 
                    timeout=args.timeout,
                    output_format=args.format
                )
            )
            dependencies.append(notebook)

        # command_list = [nbconvert_cmd.format(notebook=notebook, **spec) for notebook in notebook_list]
        # spec['commands'] = ' && '.join(command_list)
        # submit_slurm_batch_job(spec, verbose=args.verbose)

    else:
        for spike_file in args.spike:

            # new cell to add/replace:
            new_cell_source = '%run {}'.format(os.path.abspath(spike_file))

            new_notebook_list = list()

            for notebook_path in notebook_list:

                # TODO: instead add gwf targets with dependencies
                # TODO: disallow --allow-errors when running more than one notebook

                # find cell with %run magic if any
                with open(notebook_path) as f:
                    nb = nbformat.read(f, as_version=4)
                for i in range(len(nb.cells)):
                    cell = nb.cells[i]
                    if r'%run' in cell.source:
                        cell_idx = i
                        break
                else:
                    cell_idx = None

                if cell_idx is None or not args.replace_first_run_magic:
                    # insert new cell at top
                    if nb.nbformat == 4:
                        new_cell = nbformat.v4.new_code_cell(source=new_cell_source)
                    else:
                        print("Notebook format is not 4", file=sys.stderr)
                        sys.exit()
                    nb.cells.insert(0, new_cell)
                else:
                    # replace argument to first %run magic
                    nb.cells[cell_idx].source = re.sub(r'%run\s+\S+', 
                        new_cell_source, nb.cells[cell_idx].source, 1)

                notebook_base_name = modpath(notebook_path, parent='', suffix='')
                out_dir = modpath(notebook_path, suffix='')
                os.makedirs(out_dir, exist_ok=True)

                suffix = modpath(spike_file, suffix='', parent='')

                new_notebook_path = modpath(notebook_path, base=notebook_base_name + '_' + suffix, parent=out_dir)
                with open(new_notebook_path, 'w') as f:
                    nbformat.write(nb, f)

                new_notebook_list.append(new_notebook_path)

            ###################################
            dependencies = [os.path.abspath(spike_file)]
            for notebook in notebook_list:
                gwf.target_from_template(
                    name=modpath(notebook, parent='', suffix='') + '_' + modpath(spike_file, parent='', suffix=''),
                    template=nbconvert(
                        notebook_file_name=os.path.abspath(notebook),
                        output_file=os.path.abspath(new_notebook_path),
                        dependencies=dependencies,
                        inplace=True,
                        allow_errors=False, 
                        timeout=args.timeout,
                        output_format=args.format
                    )
                )
                dependencies.append(os.path.abspath(notebook))

            ###################################

            # if args.format != 'notebook' and args.cleanup:
            #     param_nbconvert_cmd = nbconvert_cmd + ' && rm -f {notebook}'
            # else:
            #     param_nbconvert_cmd = nbconvert_cmd

            # command_list = [param_nbconvert_cmd.format(notebook=notebook, **spec) for notebook in new_notebook_list]
            # spec['commands'] = ' && '.join(command_list)
            # submit_slurm_batch_job(spec, verbose=args.verbose)

    run_workflow(gwf)
