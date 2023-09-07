#!/usr/bin/env python3

import os
import sys
from os import path

from logging import getLogger

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
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

    parser.add_argument('yaml',help='yaml config file for running a specific functional test',type=str)

    args = parser.parse_args()

    return args


if __name__ == '__main__':

    user_inputs = input_args()
    config = YAMLFile(path=user_inputs.yaml)
    config = parse_j2yaml(user_inputs.yaml,data=config)
    print( config.stage_data )
    sys.exit(0)
    FileHandler(stage_files).sync()
