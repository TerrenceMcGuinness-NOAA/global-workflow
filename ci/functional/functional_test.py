#!/usr/bin/env python3

import os
import sys
import re
from os import path

from logging import getLogger

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from  workflow.hosts import Host

from logging import getLogger

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

    host = Host()
    machine = host.machine.lower()

    cfg = Configuration(f'{_top}/ci/platforms')
    host_info = cfg.parse_config(f'config.{machine}')

    # Stage the runtime environment
    # i.e. clone build global-workflow and create experiment directories
    exec_name = 'stage_environment.sh'
    exec  = os.path.join(_top,'ci','functional',exec_name)
    exec_cmd = Executable(exec)
    #exec_cmd()

    test_tasks = TestTask(host_info)

    # TODO This should be a loop over all the tests tasks
    # but for now we are going to take in a single yaml
    # file and run the test task for that yaml file

    user_inputs = input_args()
    config = YAMLFile(path=user_inputs.yaml)
    config.current_cycle = str(config.SDATE)[0:8]
    config.forecast_hour = str(config.SDATE)[8:10]

    config.update(host_info)
    config = parse_j2yaml(user_inputs.yaml, data=config)

    print(config.stage_data.mkdir)

    EXPDIR = test_tasks.exp_configs[config.PSLOT].find_config('config.base')
    job = os.path.basename(user_inputs.yaml)  # job name and task name are the same
    SDATE = config.SDATE
    PSLOT = config.PSLOT

    print( EXPDIR, job, SDATE, PSLOT )

    # task = test_tasks.get_task(task_name) 
    # TODO Get batch script using get_batchscripts.sh
    # and the above four v
    
    batch_file = os.path.join(_top,'ci','functional','ush','misc','gfsfcst_C48_ATM.sbatch')

    print( batch_file )

    # TODO Do the Filesync staging from config.stage_data
    # TODO Run the batch script TODO wrap the submision in a CTEST
    # TODO Do the Filesync of results
    # TODO Validate the results (need to know what the results are first in the yaml)
    # TODO Cleanup the Run directory
       

