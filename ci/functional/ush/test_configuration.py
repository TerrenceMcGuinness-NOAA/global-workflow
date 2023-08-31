#!/usr/bin/env python3

import os
import sys
from os import path
from columnar import columnar
from math import ceil

from wxflow import Task
import logging

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from wxflow import Configuration, Task

_here = path.dirname(__file__)
_top = path.abspath(path.join(path.abspath(_here), '../..'))

logger = logging.getLogger(__name__.split('.')[-1])


def input_args():
    """
    Method to collect user arguments for `setup_xml.py`
    """

    description = """
        foo
        """

    parser = ArgumentParser(description=description,
                            formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument('expdir', help='full path to experiment directory containing config files',
                        type=str, default=os.environ['PWD'])

    args = parser.parse_args()

    return args


if __name__ == '__main__':

    user_inputs = input_args()
    cfg = Configuration(user_inputs.expdir)

    list_files = list(map(path.basename, cfg.config_files))
    col = 5
    length = len(list_files)
    list_files.extend([' '] * (col * ceil(length / col) - length))
    config_files = [list_files[i:i + col] for i in range(0, length, col)]
    table = columnar(config_files, headers=None, no_borders=True)

    print(f'\nUsing EXPDIR: {user_inputs.expdir}\n')
    print('Containing the configfiles:')
    print(table)

    base = cfg.parse_config('config.base')
    sdate = base['SDATE'].strftime("%Y%m%d%H")

    print(f'config.base: {cfg.find_config("config.base")}')
    print('')
    print('machine:', base['machine'])
    print('SDATE:\t', sdate)
    print('CASE:\t', base['CASE'])
    print('RUN:\t', base['RUN'])
    print('MODE:\t', base['MODE'])
    print('')
    print('EXPDIR:\t', cfg.config_dir)
    print('COMROOT:', base['COMROOT'])
    print('ROTDIR:\t', base['ROTDIR'])
    print('DATAROOT:', base['DATAROOT'])

    if 'config.anal' in '\n'.join(cfg.config_files):
        print('\nconfig.anal...configured: ', end='')
        # cfg.print_config(['config.base', 'config.anal'])
        anal = cfg.parse_config(['config.base', 'config.anal'])
        print("DO_ATM", anal['DO_ATM'])
        print('')

    if 'config.coupled_ic' in '\n'.join(cfg.config_files) and base['MODE']=='forecast-only':
        coupled_ic = cfg.parse_config(['config.base', 'config.coupled_ic'])
        print('coupled ic configured:')
        IC = path.join(str(base['BASE_CPLIC']), str(coupled_ic['CPL_ATMIC']), sdate, str(base['RUN']), str(base['CASE']), 'INPUT')
        print('\t', IC, end='')
        if os.path.exists(IC):
            print(' IC path exists', end='')
        else:
            print(' Warning: IC PATH not on file system', end='')
        if sdate in IC:
            print(' and sdate is in path of ICs')
        else:
            print(' Warning: sdate is not in path of ICs')

    print()

# staged_files_path = os.path.join(_here,'forecast_test.yaml')
# staged_files_list = parse_yamltmpl(staged_files_path)
# FileHandler(staged_files_list).sync()
