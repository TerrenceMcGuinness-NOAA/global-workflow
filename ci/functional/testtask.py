#!/usr/bin/env python3

import os
import re
from os import path
from logging import getLogger
from typing import Dict, Any, Union

from workflow.hosts import Host

from wxflow import (AttrDict,
                    Configuration,
                    YAMLFile,
                    parse_j2yaml,
                    FileHandler,
                    Jinja,
                    logit,
                    Task,
                    add_to_datetime, to_timedelta,
                    WorkflowException,
                    Executable, which)

logger = getLogger(__name__.split('.')[-1])

_here = path.dirname(__file__)
_top = path.abspath(path.join(path.abspath(_here), '../..'))

class TestTasks(Task):
    """Unified Post Processor Task
    """

    @logit(logger, name="TestTasks")
    def __init__(self):
        """Constructor for the TestTask task
        The constructor is responsible for getting a collection of Configure objects
        each for the experiments directories that are used for the functional tests.

        Returns
        -------
        Dictionary of experiment configurations indexed by the pslot
        """
        host = Host()
        cfg = Configuration(f'{_top}/ci/platforms')
        self.host_info = cfg.parse_config(f'config.{host.machine}')
   
    @logit(logger)
    def initialize(self):
        """Initialize TestTasks gets the collection of Configure objects
        each for the experiments directories that are used for the functional tests.

        Returns
        -------
        Dict[str, Any]
            Dictionary of configuration parameters for the specific task    
        """
        # Get the list of the experiment directories 
        subdirectories = []
        directory = os.path.join(self.host_info.FUNCTESTS_DATA_ROOT,'RUNTESTS','EXPDIR')
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if os.path.isdir(path):
                subdirectories.append(path)

        self.configs = AttrDict()
        for subdirectory in subdirectories:
            base_name = os.path.basename(subdirectory)
            pslot = re.sub(r"_[^_]*$","", base_name)
            self.configs[pslot] = Configuration(subdirectory)
            self.configs[pslot].PSLOT = base_name

        # Read the upp.yaml file for common configuration
        logger.info(f"Created {len(self.configs)} experiment configurations")
        print(f"Created {len(self.configs)} experiment configurations")


    def configure(self, path: Union[str, os.PathLike]) -> Dict[str, Any]:    

        config = YAMLFile(path=path)
        config.current_cycle = str(config.SDATE)[0:8]
        config.forecast_hour = str(config.SDATE)[8:10]

        config.update(self.host_info)
        config.ROTDIR = self.configs[config.PSLOT].parse_config(['config.base'])['ROTDIR']
        config = parse_j2yaml(path=path, data=config)

        config.ROTDIR = self.configs[config.PSLOT].parse_config(['config.base'])['ROTDIR']
        config.EXPDIR = self.configs[config.PSLOT].config_dir
        config.job = os.path.basename(path).split('.')[0]

        config.config = self.configs[config.PSLOT]

        return config

    @staticmethod
    @logit(logger)
    def  get_batch_script(task_config: Dict[str, Any]) -> str:
        PSLOT_sha = task_config.PSLOT
        SDATE = task_config.SDATE
        EXPDIR = task_config.config.config_dir
        job = task_config.job
        print( f'Arguments for get_batch_script:\n  {EXPDIR}\n  {job}\n  {SDATE}\n  {PSLOT_sha}\n')
        batch_file = os.path.join(_top, 'ci', 'functional', 'ush', 'misc', 'gfsfcst_C48_ATM.sbatch')
        return batch_file


    @staticmethod
    @logit(logger)
    def execute(task_config: Dict[str, Any], batch_script: str) -> None:
        """Run the batch script
        Parameters
        ----------
        pathdir : str | os.PathLike
            work directory where the batch script is located
        batch_script : str
            name of the batch script to run
        batch_type : str
            type of batch script to run (Slurm, PBS, etc.)

        Returns
        -------
        None
        """
        print(f'Executing {batch_script}')
        return None

    @staticmethod
    @logit(logger)
    def finalize(upp_run: Dict, upp_yaml: Dict) -> None:
        """Perform closing actions of the task.
        """

        return None
