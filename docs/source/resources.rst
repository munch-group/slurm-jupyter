

Specifying resources
=======================

The specification of slurm resources is shared between `slurm-jupyter` and `slurm-nb-run`. It is important to know, that once any of the resources allocated are exhausted, the slurm job will terminate and your Jupyter server will shut down without warning.

Number of cores
------------------

The default is a single core, but you can specify how many cores you want available using the `-c` option:

.. code-block:: bash

    slurm-jupyter -c 3


Running time
------------------

The default time available on is 5 hours. If you want your to be allowed to run for up to 11 hours before slurm cancels your job, you can execute it like this using the ``--time`` or ``-t`` option:

.. code-block:: bash

    slurm-jupyter -t 11:00:00

The time format is like this: ``days-hours:minutes:seconds`` like for slurm, but you can also specify seconds, minutes, or hours as a number followed by a ``s``, ``m``, or ``h``: 

.. code-block:: bash

    slurm-jupyter -t 5h


Memory
------------------

The default amount of memory available is eight gigabytes. You can specify any other amount in kilo, mega or giga (k, m, or g). 

To specify that you want 4g of memory available on the slurn node you use the ``--total-memory`` option (or its short form ``-m``):

.. code-block:: bash

    slurm-jupyter -m 4g


As a guide to how much memmory you are using, ``slurm-jupyter`` will show a gaugue with regularly updated with current and max memory usage:


