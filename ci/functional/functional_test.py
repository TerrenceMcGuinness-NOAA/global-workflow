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

from testtask import TestTasks

logger = getLogger(__name__.split('.')[-1])

_here = path.dirname(__file__)
_top = path.abspath(path.join(path.abspath(_here), '../..'))

#####################################################################################
#
# Script description: Top level driver for running Functional Tests
#
# Abstract:
#    Takes a YAML file that defines a Functional Test:
#        - Base name of file is the Rocoto Task Name to be tested
#        - PSLOT: Name of experment found in $FUNCTESTS_DATA_ROOT/RUDIRS
#                 that has the Rocoto XML with corrsponding Task Name
#        - SDSATE: Stert date of test
#        - stage_date:  copy information for moving inputs to ROTDIR


def input_args():
    """
    Method to collect user arguments fucntional test driver
    """

    description = """
       --yaml YAML file for defining a functional test
        """

    parser = ArgumentParser(description=description,
                            formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument('yaml', help='yaml config file for running a specific functional test', type=str)

    args = parser.parse_args()

    return args

if __name__ == '__main__':

    user_inputs = input_args()

    # Stage the runtime environment
    # i.e. clone build global-workflow and create experiment directories
    exec_name = 'stage_environment.sh'
    exec  = os.path.join(_top,'ci','functional', 'ush', exec_name)
    exec_cmd = Executable(exec)
    exec_cmd()

    # Get platform information
    tasks = TestTasks()
    # Get config objects from staged runtime environment
    tasks.initialize()
    # Get all necessary configure objects for specific functional test
    task_config = tasks.configure(user_inputs.yaml)

    #  Move the requisite data running functional test
    print( f'mkdir: {task_config.stage_data.mkdir}\n')
    FileHandler(task_config.stage_data).sync()

    # Get batch script using get_batchscripts.sh
    batch_script = tasks.get_batch_script(task_config)
    print( f'practice batch file: {batch_script}\n' )

    #tasks.execute(task_config, batch_script)

    # TODO Run the batch script TODO wrap the submision in a CTEST
    # TODO Do the Filesync of results
    # TODO Validate the results (need to know what the results are first in the yaml)
    # TODO Cleanup the Run directory
