#!/usr/bin/env python3

import os
import sys
import re
from os import path

from logging import getLogger
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from workflow.hosts import Host

from wxflow import (Configuration,
                    AttrDict,
                    FileHandler,
                    chdir,
                    YAMLFile, parse_yamltmpl, parse_j2yaml, save_as_yaml,
                    logit,
                    Executable,
                    WorkflowException)

from testtask import TestTask

logger = getLogger(__name__.split('.')[-1])

_here = path.dirname(__file__)
_top = path.abspath(path.join(path.abspath(_here), '../..'))


def input_args():
    """
    Method to collect user arguments fucntional test driver
    """

    description = """
        foo
        """

    parser = ArgumentParser(description=description,
                            formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument('yaml', help='yaml config file for running a specific functional test', type=str)

    args = parser.parse_args()

    return args

if __name__ == '__main__':



    # Stage the runtime environment
    # i.e. clone build global-workflow and create experiment directories
    exec_name = 'stage_environment.sh'
    exec  = os.path.join(_top,'ci','functional',exec_name)
    exec_cmd = Executable(exec)
    #exec_cmd()

    host = Host()
    test_tasks = TestTask(host.machine)

    # TODO This should be a loop over all the tests tasks
    # but for now we are going to take in a single yaml
    # file and run the test task for that yaml file

    user_inputs = input_args()

    task = test_tasks.initialize(path=user_inputs.yaml)

    # TODO Move this data
    print( f'mkdir: {task.stage_data.mkdir}\n')

    PSLOT_sha = task.PSLOT
    SDATE = task.SDATE
    EXPDIR = task.config.config_dir
    job = task.job

    print( f'Arguments for get_batch_script:\n  {EXPDIR}\n  {job}\n  {SDATE}\n  {PSLOT_sha}\n')

    # TODO Get batch script using get_batchscripts.sh
    # and the above four variables
    
    batch_file = os.path.join(_top, 'ci', 'functional', 'ush', 'misc', 'gfsfcst_C48_ATM.sbatch')

    print( f'practice batch file: {batch_file}\n' )

    # TODO Run the batch script TODO wrap the submision in a CTEST
    # TODO Do the Filesync of results
    # TODO Validate the results (need to know what the results are first in the yaml)
    # TODO Cleanup the Run directory
