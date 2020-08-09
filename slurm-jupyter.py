#!/usr/bin/env python
from __future__ import (absolute_import, division, print_function, unicode_literals)
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

from subprocess import PIPE, Popen
from threading  import Thread, Event, Timer

from colorama import init
init()

try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty  # python 3.x

if sys.version_info < (3,0):
    input = raw_input

def execute(cmd, stdin=None):
    process = Popen(cmd.split(), stdin=PIPE, stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate(stdin)
    return stdout, stderr


# terminal colors
BLUE = '\033[94m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
ENDC = '\033[0m'

# string template for slurm script
slurm_script =  """#!/bin/sh
#SBATCH -p {queue}
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

{environment}
{ipcluster}
unset XDG_RUNTIME_DIR
jupyter {run} --ip=0.0.0.0 --no-browser --port={hostport} --NotebookApp.iopub_data_rate_limit=10000000000
"""

mem_script = """
import psutil
import os
for proc in psutil.process_iter():
    try:
        if '/job{job_id}/' in ' '. join(proc.cmdline()) and proc.username() == os.environ['USER']:            
            # print(proc.cmdline())
            print( sum(c.memory_info().rss for c in proc.children(recursive=True)) )
            break
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
"""

def on_windows():
    return sys.platform == 'win32'


# Ask for confirmation on keyboard interrupt
def kbintr_handler(signal, frame):
    msg = BLUE+'\nAre you sure? y/n: '+ENDC
    try:
        if input(msg) == 'y':
            raise KeyboardInterrupt
    except RuntimeError: # in case user does Ctrl-C instead of y
        raise KeyboardInterrupt


def kbintr_repressor(signal, frame):
    pass


def get_cluster_uid(spec):

    process = subprocess.Popen(
        'ssh {user}@{frontend} id'.format(**spec),
        shell=True,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    uid = int(re.match('uid=(\d+)', stdout).group(1))
    return uid


def submit_slurm_job(spec):

    cmd = 'ssh {user}@{frontend} cat - > {tmp_dir}/{tmp_script} ; mkdir -p {tmp_dir} ; {slurm} ; sbatch {tmp_dir}/{tmp_script} '.format(**spec)
        
    if args.verbose: print("script ssh transfer:", cmd, sep='\n')

    script = slurm_script.format(**spec)
    if args.verbose: print("slurm script:", script, sep='\n')

    if sys.version_info >= (3,0): script = script.encode()
    stdout, stderr = execute(cmd, stdin=script) # hangs untill submission

    # get stdour and stderr and get jobid
    if sys.version_info >= (3,0):
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


def wait_for_job_allocation(spec):
    # wait a bit to make sure jobinfo database is updated
    time.sleep(20)

    # wait for job to start and get node it runs on 
    # regex = re.compile('Nodes\s+:\s+(\S+)')
    # cmd = 'ssh {user}@{frontend} {slurm} ; jobinfo {job_id}'.format(**spec)        
    # stdout, stderr = execute(cmd)
    # if sys.version_info >= (3,0): stdout = stdout.decode()
    # m = regex.search(stdout)
    cmd = 'ssh {user}@{frontend} {slurm} ; squeue --noheader --format %N -j {job_id}'.format(**spec)        
    stdout, stderr = execute(cmd)
    if sys.version_info >= (3,0): stdout = stdout.decode()
    node_id = stdout.strip()

    while not node_id: #not m or m.group(1) == 'None':
        time.sleep(10)
        stdout, stderr = execute(cmd)
        if sys.version_info >= (3,0):
            stdout = stdout.decode()
        # m = regex.search(stdout)
        node_id = stdout.strip()
    if args.verbose: print(stdout)

    # node_id = m.group(1)
    return node_id

'''
mport selectors
import subprocess
import sys

p = subprocess.Popen(
    ["python", "random_out.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
)

sel = selectors.DefaultSelector()
sel.register(p.stdout, selectors.EVENT_READ)
sel.register(p.stderr, selectors.EVENT_READ)

while True:
    for key, _ in sel.select():
        data = key.fileobj.read1().decode()
        if not data:
            exit()
        if key.fileobj is p.stdout:
            print(data, end="")
        else:
            print(data, end="", file=sys.stderr)

'''

ON_POSIX = 'posix' in sys.builtin_module_names
#ON_POSIX  = os.name == 'posix'

#ssh -L6358:fe1.genomedk.net:6358 kmt@login.genome.au.dk
#jupyter lab --ip=0.0.0.0 --no-browser --port=6358 --NotebookApp.iopub_data_rate_limit=10000000000

def enqueue_output(out, queue):

    # sel = selectors.DefaultSelector()
    # sel.register(out, selectors.EVENT_READ)
    # while run_event.is_set():
    #     for key, _ in sel.select():
    #         c = key.fileobj.readline()
    #         queue.put(c)
    #     time.sleep(.1)

    while run_event.is_set():
        for line in iter(out.readline, b''):
            queue.put(line)
        time.sleep(.1)

def open_stdout_connection(spec):
    cmd = 'ssh {user}@{frontend} tail -F -n +1 {tmp_dir}/{tmp_name}.{job_id}.out'.format(**spec)
    if args.verbose: print("stdout connection:", cmd)
    stdout_p = Popen(cmd.split(), stdout=PIPE, stderr=PIPE, bufsize=0, close_fds=ON_POSIX)
    stdout_q = Queue()
    stdout_t = Thread(target=enqueue_output, args=(stdout_p.stdout, stdout_q))
    stdout_t.daemon = True # thread dies with the program
    stdout_t.start()
    return stdout_p, stdout_t, stdout_q


def open_stderr_connection(spec):
    cmd = 'ssh {user}@{frontend} tail -F -n +1 {tmp_dir}/{tmp_name}.{job_id}.err'.format(**spec)
    if args.verbose: print("stderr connection:", cmd)
    stderr_p = Popen(cmd.split(), stdout=PIPE, stderr=PIPE, bufsize=0, close_fds=ON_POSIX)
    stderr_q = Queue()
    stderr_t = Thread(target=enqueue_output, args=(stderr_p.stdout, stderr_q))
    stderr_t.daemon = True # thread dies with the program
    stderr_t.start()
    return stderr_p, stderr_t, stderr_q


def open_port(spec):
    cmd = 'ssh -L{port}:{node}.genomedk.net:{hostport} {user}@{frontend}'.format(**spec)
    if args.verbose: print("forwarding port:", cmd)
    port_p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    # we have to set stdin=PIPE even though we eodn't use it because this
    # makes sure the process does not inherrit stdin from the parent process (this).
    # Otherwise signals are sent to the process and not to the python script
    port_q = Queue()
    port_t = Thread(target=enqueue_output, args=(port_p.stderr, port_q))
    port_t.daemon = True # thread dies with the program
    port_t.start()
    return port_p, port_t, port_q


def open_chrome(spec):
    if platform.platform().startswith('Darwin'):
        chrome_path = 'open -a /Applications/Google\ Chrome.app %s'
    else:
        chrome_path = '/usr/bin/google-chrome %s'
    url = 'https://localhost:{port}'.format(**spec)
    print(url)
    webbrowser.get(chrome_path).open(url)


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


def memory_status(spec, max_proportion):

    used_mem, max_used_mem, reserved_mem = 0, 0, 0

    if args.memory_per_cpu:
        reserved_mem = str_to_mb(args.memory_per_cpu) * spec['nr_cores'] 
    else:
        reserved_mem = str_to_mb(args.total_memory)

    process = Popen("ssh {user}@{frontend} ssh {user}@{node} python .slurm_jupyter/mem_jupyter.py".format(**spec).split(),
         stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()
    try:
        used_mem = int(stdout.decode().strip()) / 1024**2
    except ValueError:
        # if called after node shutdown stdout is "Node 's03n24.genomedk.net' not allocated to user(6358)!"
        used_mem = -1 # if slurm job is killed and node is no longer allocated

    width = 50
    proportion = used_mem / reserved_mem
    max_proportion = max(proportion, max_proportion)
    n = int(round(proportion * width, 0))
    m = int(round(max_proportion * width, 0))

    n, m = m - (m - n), m - n
    bar = '[' + '=' * n + '-' * m + ' ' * (width - n - m) + ']'
    line = "{:>6.1f} Gb {} {:.1f} Gb".format(used_mem / 1024.0, bar,
        reserved_mem / 1024.0)
    if proportion < 0.8:
        color = BLUE
    else:
        color = RED
    return proportion, color + line + ENDC


class StoppableThread(Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self, target, args):

        args += [self] # add self to function args to allow function to stop thraed

        super(StoppableThread, self).__init__(target=target, args=args)
        self._stop_event = Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()


def transfer_memory_script(spec):

    script = mem_script.format(**spec)

    cmd = 'ssh {user}@{frontend} cat - > {tmp_dir}/{mem_script} ; mkdir -p {tmp_dir}'.format(**spec)
        
    if args.verbose: print("memory script:", script, sep='\n')

    if sys.version_info >= (3,0): script = script.encode()
    stdout, stderr = execute(cmd, stdin=script) # hangs untill submission


def memory_monitor(spec, thread):

    transfer_memory_script(spec)

    max_proportion = 0
    prev_proportion = 0
    prev_time = 0
    while True:
        if thread.stopped():
            break
        time.sleep(10)
        try:
            max_proportion = max(prev_proportion, max_proportion)
            proportion, status_line = memory_status(spec, max_proportion)
            max_interval = 5 * 60
            if abs(proportion - prev_proportion) > 0.1 or (time.time() - prev_time > max_interval):
                prev_proportion = proportion
                prev_time = time.time()
                print(status_line, file=sys.stderr)
                sys.stdout.flush()
        except UnboundLocalError:
            # This can happen when the function is interrupted halfway
            break

description = """
The script handles everyting required to run jupyter on the cluster but show the notebook or jupyterlab 
in your local browser."""

not_wrapped = """See github.com/kaspermunch/slurm_jupyter for documentation and common use cases."""

description = "\n".join(wrap(description.strip(), 80)) + "\n\n" + not_wrapped

parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=description)
parser.add_argument("--run", 
                  dest="run", 
                  type=str, 
                  choices=['notebook', 'lab'],
                  default='lab',
                  help="URL to cluster frontend.")
parser.add_argument("-f", "--frontend", 
                  dest="frontend", 
                  type=str, 
                  default="login.genome.au.dk", 
                  help="URL to cluster frontend.")
parser.add_argument("-A", "--account",
                  dest="account",
                  type=str,
                  default=None,
                  help="Account/Project to run under. This is typically the name of the shared folder you work in. Not specifying an account decreases your priority in the cluster queue.")
parser.add_argument("-q", "--queue",
                  dest="queue",
                  type=str,
                  choices=['normal', 'express', 'fat1', 'fat2', 'gpu'],
                  default="normal",
                  help="Cluster queue to submit to.")
parser.add_argument("-n", "--nodes",
                  dest="nodes",
                  type=int,
                  default=1,
                  help="Number of nodes (machines) to allocate.")
parser.add_argument("-c", "--cores",
                  dest="cores",
                  type=int,
                  default=1,
                  help="Number of cores. For multiprocessing or for running more than one notebook simultaneously.")
parser.add_argument("-t", "--time",
                  dest="time",
                  type=str,
                  default="08:00:00",
                  help="Max wall time. specify as HH:MM:SS (or any other format supported by the cluster). The jupyter server is killed automatically after this time.")
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
parser.add_argument("-e", "--environment",
                  dest="environment",
                  type=str,
                  default='',
                  help="Conda environment to run jupyter in.")
parser.add_argument("--timeout",
                  dest="timeout",
                  default=0.1,
                  type=float,
                  help="Time out in seconds for cross thread operations")
parser.add_argument("--ipcluster",
                  dest="ipcluster",
                  action='store_true',
                  default=False,
                  help="Start an ipcluster")
parser.add_argument("-v", "--verbose",
                  dest="verbose",
                  action='store_true',
                  help="Print debugging information")

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

args = parser.parse_args()


if args.nodes != 1:
    print("Multiprocessign across multiple nodes not supported yet - sorry")
    sys.exit()

spec = {'user': args.user,
        'port': args.port,
        'environment': args.environment,
        'run': args.run,
        'walltime': args.time,
        'account': args.account,
        'queue': args.queue,
        'nr_nodes': args.nodes,
        'nr_cores': args.cores,
        'cwd': os.getcwd(),
        'sources_loaded': '',
        'slurm': 'source /com/extra/slurm/14.03.0/load.sh',
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


if spec['port'] is None:
    spec['port'] = get_cluster_uid(spec)

if spec['hostport'] is None:
    spec['hostport'] = get_cluster_uid(spec)

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
    spec['job_id'] = submit_slurm_job(spec)
    print(BLUE+'Waiting for slurm job allocation'+ENDC)

    spec['node'] = wait_for_job_allocation(spec)
    print(BLUE+'Compute node(s) allocated:', spec['node'], ENDC)

    # event to communicate with threads (except memory thread)
    run_event = Event()
    run_event.set()

    print(BLUE+'Jupyter server: (to stop the server press Ctrl-C)'+ENDC)

    time.sleep(5)

    # open connections to stdout and stderr from jupyter server
    stdout_p, stdout_t, stdout_q = open_stdout_connection(spec)
    stderr_p, stderr_t, stderr_q = open_stderr_connection(spec)

    # start thread monitoring memory usage
    mem_print_t = StoppableThread(target=memory_monitor, args=[spec])
    mem_print_t.daemon = True # thread dies with the program
    mem_print_t.start()

    while True:
        while True:
            try:  
                line = stdout_q.get(timeout=args.timeout)#get_nowait()
            except Empty:
                break
            else:
                if sys.version_info >= (3,0):
                    line = line.decode()
                line = line.replace('\r', '\n')
                print(line, end="")
        while True:
            try:  
                line = stderr_q.get(timeout=args.timeout)#get_nowait()
            except Empty:
                break
            else:
                if sys.version_info >= (3,0):
                    line = line.decode()
                line = line.replace('\r', '\n')
                if 'SSLV3_ALERT_CERTIFICATE_UNKNOWN' not in line: # skip warnings about SSL certificate
                    print(line, end="")

                if re.search('Jupyter Notebook[\d. ]+is running', line):
                    port_p, port_t, port_q = open_port(spec)

                    open_chrome(spec)
                    print(BLUE+'If your browser says "Your connection is not private",',
                     'click "Advanced" and then "Proceed etc. (unsafe)"\n',
                     '(To skip this step in the future you can type this in the Chrome addres bar:\n',
                     '"chrome://flags/#allow-insecure-localhost"',
                     'and then select "Enable")'+ENDC)
except KeyboardInterrupt:

    # not possible to do Keyboard interrupt from hereon out
    signal.signal(signal.SIGINT, kbintr_repressor)

    # in try statements becuase these vars may not be defined at keyboard interrupt:
    try:
        run_event.clear()
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
        mem_print_t.stop()
        mem_print_t.join()
    except:
        pass

    print(BLUE+'\nCanceling slurm job running jupyter server'+ENDC)
    stdout, stderr = execute('ssh {user}@{frontend} {slurm} ; scancel {job_id}'.format(**spec))
    sys.exit()

