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

from subprocess import PIPE, Popen
from threading  import Thread, Event, Timer
import webbrowser

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


def check_for_conda_update():
    """Checks for a more recent conda version and prints a message.
    """
    cmd = 'conda search -c kaspermunch slurm-jupyter'
    conda_search = subprocess.check_output(cmd, shell=True).decode()
    newest_version = conda_search.strip().splitlines()[-1].split()[1]
    cmd = 'conda list -f slurm-jupyter'
    conda_search = subprocess.check_output(cmd, shell=True).decode()
    this_version = conda_search.strip().splitlines()[-1].split()[1]
    if LooseVersion(newest_version) > LooseVersion(this_version):
        msg = '\nA newer version of slurm-jupyter exists ({}). To update run:\n'.format(newest_version)
        msg += '\n\tconda update -c kaspermunch slurm-jupyter\n'
        print(RED + msg + ENDC)


# Ask for confirmation on keyboard interrupt
def kbintr_handler(signal, frame):
    """Intercepts KeyboardInterrupt and asks for confirmation.
    """
    msg = BLUE+'\nAre you sure? y/n: '+ENDC
    try:
        if input(msg) == 'y':
            raise KeyboardInterrupt
    except RuntimeError: # in case user does Ctrl-C instead of y
        raise KeyboardInterrupt


def kbintr_repressor(signal, frame):
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
    process = subprocess.Popen(
        'ssh {user}@{frontend} id'.format(**spec),
        shell=True,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    uid = int(re.search('uid=(\d+)', stdout).group(1))
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
    stdout, stderr = execute(cmd, stdin=script) # hangs untill submission

    # get stdour and stderr and get jobid
    stdout = stdout.decode()
    stderr = stderr.decode()
    try:
        job_id = re.search('Submitted batch job (\d+)', stdout).group(1)
    except AttributeError:
        print(BLUE+'Slurm job submission failed'+ENDC)
        print(stdout)
        print(stderr)
        sys.exit()
    print(BLUE+"Submitted slurm with job id:", job_id, ENDC)

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
   
    stdout, stderr = execute(cmd, shell=True) # hangs untill submission

    # get stdour and stderr and get jobid
    stdout = stdout.decode()
    stderr = stderr.decode()
    try:
        job_id = re.search('Submitted batch job (\d+)', stdout).group(1)
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

    cmd = 'ssh {user}@{frontend} squeue --noheader --format %N -j {job_id}'.format(**spec)        
    stdout, stderr = execute(cmd)
    stdout = stdout.decode()
    node_id = stdout.strip()

    while not node_id: #not m or m.group(1) == 'None':
        time.sleep(10)
        stdout, stderr = execute(cmd)
        stdout = stdout.decode()
        # m = regex.search(stdout)
        node_id = stdout.strip()
    if verbose: print(stdout)

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
    p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, bufsize=0, close_fds=ON_POSIX)
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
        stdout, stderr = execute(cmd)
        if "File exists" in stdout.decode():
            file_created = True
        else:
            time.sleep(10)

    cmd = 'ssh {user}@{frontend} tail -F -n +1 {tmp_dir}/{tmp_name}.{job_id}.out'.format(**spec)
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
        stdout, stderr = execute(cmd)
        if "File exists" in stdout.decode():
            file_created = True
        else:
            time.sleep(10)

    cmd = 'ssh {user}@{frontend} tail -F -n +1 {tmp_dir}/{tmp_name}.{job_id}.err'.format(**spec)
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
    cmd = 'ssh {user}@{frontend} ssh {user}@{node} python {tmp_dir}/mem_jupyter.py'.format(**spec)
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
    cmd = 'ssh -L{port}:{node}.genomedk.net:{hostport} {user}@{frontend}'.format(**spec)
    if verbose: print("forwarding port:", cmd)
    port_p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    # we have to set stdin=PIPE even though we eodn't use it because this
    # makes sure the process does not inherrit stdin from the parent process (this).
    # Otherwise signals are sent to the process and not to the python script
    port_q = Queue()
    port_t = Thread(target=enqueue_output, args=(port_p.stderr, port_q))
    port_t.daemon = True # thread dies with the program
    port_t.start()
    return port_p, port_t, port_q


def open_browser(spec):
    """Opens default browser on localhost and port.

    Args:
        spec (dict): Parameter specification.
    """
    url = 'https://localhost:{port}'.format(**spec)
    if platform.platform().startswith('Darwin') or platform.platform().startswith('macOS-'):
        chrome_path = 'open -a /Applications/Google\ Chrome.app %s'
        if os.path.exists('/Applications/Google Chrome.app'):
            webbrowser.get(chrome_path).open(url, new=2)
        else:
            webbrowser.open(url, new=2)
    elif platform.platform().startswith('Windows'):
        webbrowser.open(url, new=2)
    else:
        chrome_path = '/usr/bin/google-chrome %s'
        if os.path.exists('/usr/bin/google-chrome'):
            webbrowser.get(chrome_path).open(url, new=2)
        else:
            webbrowser.open(url, new=2)


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
                    default="jptr_{}_{}".format(getpass.getuser(), int(time.time())),
                    help="Name of job. Only needed if you run multiple servers and want to be able to recognize a particular one in the cluster queue.")
    parser.add_argument("-u", "--user",
                    dest="user",
                    type=str,
                    default=getpass.getuser(),
                    help="User name on the cluster. Only needed if your user name on the cluster is different from the one you use on your own computer.")
    parser.add_argument("-e", "--environment",
                    dest="environment",
                    type=str,
                    default='',
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


def slurm_jupyter():
    """Command line script for use on a local machine. Runs and connects to a jupyter server on a slurm node.
    """ 

    description = """
    The script handles everyting required to run jupyter on the cluster but show the notebook or jupyterlab 
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
    parser.add_argument("-v", "--verbose",
                    dest="verbose",
                    action='store_true',
                    help="Print debugging information")

    args = parser.parse_args()

    if args.nodes != 1:
        print("Multiprocessign across multiple nodes not supported yet - sorry")
        sys.exit()

    if args.time[-1] in 'smhdSMHD':
        unit = args.time[-1].lower()
        value = int(args.time[:-1])
        args.time = human2walltime(**{unit:value})

    spec = {'user': args.user,
            'port': args.port,
            'environment': args.environment,
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
            'job_name': args.name,
            'job_id': None }


    # test ssh connection:
    process = subprocess.Popen(
        'ssh -q {user}@{frontend} exit'.format(**spec),
        shell=True,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode:
        print("Cannot make ssh connection: {user}@{frontend}".format(**spec))
        sys.exit()

    check_for_conda_update()

    if spec['port'] is None:
        spec['port'] = get_cluster_uid(spec)

    if spec['hostport'] is None:
        spec['hostport'] = get_cluster_uid(spec)

    tup = spec['walltime'].split('-')
    if len(tup) == 1:
        days, (hours, mins, secs) = 0, tup[0].split(':')
    else:
        days, (hours, mins, secs) = tup[0], tup[1].split(':')
    end_time = int(time.time()) + int(days) * 86400 + int(hours) * 3600 + int(mins) * 60 + int(secs)

    if args.total_memory:
        spec['memory_spec'] = '#SBATCH --mem {}'.format(int(str_to_mb(args.total_memory)))
    else:
        spec['memory_spec'] = '#SBATCH --mem-per-cpu {}'.format(int(str_to_mb(args.memory_per_cpu)))

    if args.environment:
        spec['environment'] = "\nconda activate " + args.environment

    if args.ipcluster:
        spec['ipcluster'] = "ipcluster start -n {} &".format(args.cores)
    else:   
        spec['ipcluster'] = ''

    if args.account:
        spec['account_spec'] = "#SBATCH -A {}".format(args.account)
    else:
        spec['account_spec'] = ""

    # incept keyboard interrupt with user prompt
    signal.signal(signal.SIGINT, kbintr_handler)

    try:
        spec['job_id'] = submit_slurm_server_job(spec, verbose=args.verbose)
        print(BLUE+'Waiting for slurm job allocation'+ENDC)

        spec['node'] = wait_for_job_allocation(spec, verbose=args.verbose)
        print(BLUE+'Compute node(s) allocated:', spec['node'], ENDC)

        # event to communicate with threads (except memory thread)
        global RUN_EVENT
        RUN_EVENT = Event()
        RUN_EVENT.set()

        print(BLUE+'Jupyter server: (to stop the server press Ctrl-C)'+ENDC)

        time.sleep(5)

        # open connections to stdout and stderr from jupyter server
        stdout_p, stdout_t, stdout_q = open_jupyter_stdout_connection(spec, verbose=args.verbose)
        stderr_p, stderr_t, stderr_q = open_jupyter_stderr_connection(spec, verbose=args.verbose)

        # open connections to stdout from memory monitoring script
        transfer_memory_script(spec, verbose=args.verbose)
        mem_stdout_p, mem_stdout_t, mem_stdout_q = open_memory_stdout_connection(spec)

        # # start thread monitoring memory usage
        # mem_print_t = StoppableThread(target=memory_monitor, args=[spec])
        # mem_print_t.daemon = True # thread dies with the program
        # mem_print_t.start()

        while True:
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
                    mem_line = mem_line.decode().rstrip() 
                    secs_left = end_time - int(time.time())
                    color = secs_left > 600 and BLUE or RED
                    mem_line += '\t'+color+'Time: '+seconds2string(secs_left)+ENDC
                    print(mem_line)
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

                    if re.search('Jupyter Notebook[\d. ]+is running', line) or re.search('Jupyter Server[\d. ]+is running', line):
                        port_p, port_t, port_q = open_port(spec, verbose=args.verbose)

                        open_browser(spec)
                        print(BLUE+' Your browser may complain that the connection is not private.\n',
                                   'In Safari, you can proceed to allow this. In Chrome, you need"\n',
                                   'to simply type the characters "thisisunsafe" while in the Chrome window.\n',
                                   'Once ready, jupyter may ask for your cluster password.'+ENDC)

    except KeyboardInterrupt:

        # not possible to do Keyboard interrupt from hereon out
        signal.signal(signal.SIGINT, kbintr_repressor)

        # in try statements becuase these vars may not be defined at keyboard interrupt:
        try:
            RUN_EVENT.clear()
            port_t.join()
            port_p.kill()
        except:
            pass

        try:
            stdout_t.join()
            stdout_p.kill()
        except:
            pass

        try:
            stderr_p.kill()
            stderr_t.join()
        except:
            pass
            
        try:
            mem_stdout_t.join()
            mem_stdout_p.kill()
            # mem_print_t.stop()
            # mem_print_t.join()
        except:
            pass

        print(BLUE+'\nCanceling slurm job running jupyter server'+ENDC)
        stdout, stderr = execute('ssh {user}@{frontend} scancel {job_id}'.format(**spec))
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
    parser.add_argument("--cleanup",
                    dest="cleanup",
                    action='store_true',
                    help="Removes un-executed notebooks generated using --spike and format other than 'notebook'")                           

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

    if args.cleanup and not args.spike:
        print("Only use --cleanup with --spike")
        sys.exit()

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

    if not args.spike:
        command_list = [nbconvert_cmd.format(notebook=notebook, **spec) for notebook in notebook_list]
        spec['commands'] = ' && '.join(command_list)
        submit_slurm_batch_job(spec, verbose=args.verbose)

    else:
        for spike_file in args.spike:

            # new cell to add/replace:
            new_cell_source = '%run {}'.format(os.path.abspath(spike_file))

            new_notebook_list = list()

            for notebook_path in notebook_list:

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

            if args.format != 'notebook' and args.cleanup:
                param_nbconvert_cmd = nbconvert_cmd + ' && rm -f {notebook}'
            else:
                param_nbconvert_cmd = nbconvert_cmd

            command_list = [param_nbconvert_cmd.format(notebook=notebook, **spec) for notebook in new_notebook_list]
            spec['commands'] = ' && '.join(command_list)
            submit_slurm_batch_job(spec, verbose=args.verbose)
