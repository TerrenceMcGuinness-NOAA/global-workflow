#!/usr/bin/env python3

import os, sys
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

    list_files=list(map(path.basename, cfg.config_files))
    col=5;l=len(list_files)
    list_files.extend([' ']*(col*ceil(l/col)-l))
    config_files=[list_files[i:i+col] for i in range(0,l,col)]
    table=columnar(config_files, headers=None, no_borders=True)

    print(f'\nUsing EXPDIR: {user_inputs.expdir}\n')
    print('Containing the configfiles:')
    print(table)

    base = cfg.parse_config('config.base')
    sdate = base['SDATE'].strftime("%Y%m%d%H") 

    print(f'config.base: {cfg.find_config("config.base")}')

    print( '' )
    print(f'EXPDIR: {cfg.config_dir}')
    print( 'DATAROOT:\t', base['DATAROOT'] )
    print( 'COMROOT:\t', base['COMROOT'] )
    print( '')
    print( 'SDATE:\t\t', sdate )
    print( 'machine:\t', base['machine'] )   
    print( 'CASE:\t\t', base['CASE'] )   
    print( 'RUN:\t\t', base['RUN'] )   


    if 'config.anal' in '\n'.join(cfg.config_files):
       print('config.anal...')
       #cfg.print_config(['config.base', 'config.anal'])


    for val,env in base.items():
        os.environ[val] = str(env)

    if 'config.coupled_ic' in '\n'.join(cfg.config_files):
        coupled_ic  = cfg.parse_config('config.coupled_ic')
        cfg.print_config(['config.base', 'config.coupled_ic'])
        IC = path.join(str(base['BASE_CPLIC']),str(coupled_ic['CPL_ATMIC']),sdate,str(base['RUN']),str(base['CASE']),'INPUT')
        print()
        print(IC)
        print()

    #staged_files_path = os.path.join(_here,'forecast_test.yaml')
    #staged_files_list = parse_yamltmpl(staged_files_path)
    #FileHandler(staged_files_list).sync()
