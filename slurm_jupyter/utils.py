import os
import sys
from subprocess import PIPE, Popen

def seconds2string(sec):
    """Convert seconds to slurm time spec.

    Args:
        sec (int): Seconds

    Returns:
        str: slurm time spec string (days-hours:mins:secs)
    """
    days, sec = sec // 86400, sec % 86400
    hours, sec = sec // 3600, sec % 3600
    minutes, seconds  = sec // 60, sec % 60
    return f'{days}-{hours:02}:{minutes:02}:{seconds:02}'


def human2walltime(d=0, h=0, m=0, s=0):
    return seconds2string(d * 86400 + h * 3600 + m * 60 + s)


def execute(cmd, stdin=None, shell=False):
    """Executes a system command line.

    Args:
        cmd (str): System command.
        stdin (str, optional): Standard input. Defaults to None.
        shell (bool, optional): Run command in a shell. Defaults to False.

    Returns:
        tuple: Two strings holding standard output and standard error respectively.
    """
    if shell:
        process = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True)
    else:
        process = Popen(cmd.split(), stdin=PIPE, stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate(stdin)
    return stdout, stderr


def modpath(p, parent=None, base=None, suffix=None):
    """Standard modifications on a file path.

    Args:
        p (str): File path.
        parent (str, optional): New directory. Defaults to None.
        base (str, optional): New file base name. Defaults to None.
        suffix (str, optional): New file suffix. Defaults to None.

    Returns:
        str: Modified file path.
    """
    par, name = os.path.split(p)
    name_no_suffix, suf = os.path.splitext(name)
    if type(suffix) is str:
        suf = suffix
    if parent is not None:
        par = parent
    if base is not None:
        name_no_suffix = base

    new_path = os.path.join(par, name_no_suffix + suf)
    if type(suffix) is tuple:
        assert len(suffix) == 2
        new_path, nsubs = re.subn(r'{}$'.format(suffix[0]), suffix[1], new_path)
        assert nsubs == 1, nsubs
    return new_path


def on_windows():
    """Tests if on Windows.

    Returns:
        bool: True if on Windows.
    """
    return sys.platform == 'win32'


def str_to_mb(s):
    """Translate string like 1m or 1g to number of megabytes.

    Args:
        s (str): String specifying memory size (E.g. 4k, 7m og 3g)

    Returns:
        float: number of megabytes.
    """
    # compute mem in mb
    scale = s[-1].lower()
    assert scale in ['k', 'm', 'g']
    memory_per_cpu_mb = float(s[:-1])
    if scale == 'g':
        memory_per_cpu_mb *= 1024
    if scale == 'k':
        memory_per_cpu_mb /= 1024.0
    return memory_per_cpu_mb