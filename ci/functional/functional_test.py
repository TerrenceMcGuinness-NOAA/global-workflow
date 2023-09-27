#!/usr/bin/env python3

import os
import sys
import re
from os import path

from logging import getLogger

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from  workflow.hosts import Host

from wxflow import Configuration, Task

from logging import getLogger

from wxflow import (AttrDict,
                    FileHandler,
                    chdir,
                    YAMLFile, parse_yamltmpl, parse_j2yaml, save_as_yaml,
                    logit,
                    Executable,
                    WorkflowException)

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

    user_inputs = input_args()
    config = YAMLFile(path=user_inputs.yaml)
    config.current_cycle = str(config.SDATE)[0:8]
    config.forecast_hour = str(config.SDATE)[8:10]

    config.update(host_info)
    config = parse_j2yaml(user_inputs.yaml, data=config)
    print(config.stage_data.mkdir)

    # TODO Stage the runtime environment
    # i.e. clone build global-workflow and create experiment directories
    exec_name = 'stage_environment.sh'
    exec  = os.path.join(_top,'ci','functional',exec_name)
    exec_cmd = Executable(exec)
    exec_cmd()

    print(config.stage_data.mkdir)
    #FileHandler(config.stage_data).sync()
