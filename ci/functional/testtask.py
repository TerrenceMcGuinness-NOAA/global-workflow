#!/usr/bin/env python3

import os
import re
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
class TestTask(Task):
    """Unified Post Processor Task
    """

    @logit(logger, name="TestTask")
    def __init__(self, config : Dict[str, Any]) -> Dict[str, Any]:
        """Constructor for the TestTask task
        The constructor is responsible for getting a collection of Configure objects
        each for the experiments directories that are used for the functional tests.

        Returns
        -------
        Dictionary of experiment configurations indexed by the pslot
        """

        host = Host()
        machine = host.machine.lower()

        cfg = Configuration(f'{_top}/ci/platforms')
        self.host_info = cfg.parse_config(f'config.{machine}')
   
        # Get the list of the experiment directories 
        subdirectories = []
        directory = os.path.join(config.FUNCTESTS_DATA_ROOT,'RUNTESTS','EXPDIR')
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if os.path.isdir(path):
                subdirectories.append(path)

        exp_configs = AttrDict()
        for subdirectory in subdirectories:
            base_name = os.path.basename(subdirectory)
            pslot = re.sub(r"_[^_]*$","", base_name)
            exp_configs[pslot] = Configuration(subdirectory)
            exp_configs[pslot].PSLOT = base_name

        # Read the upp.yaml file for common configuration
        logger.info(f"Created {len(self.exp_configs)} experiment configurations")
        print(f"Created {len(self.exp_configs)} experiment configurations")

        return exp_configs

    @staticmethod
    @logit(logger)
    def initialize(self, path: str) ->  Dict[str, Any]:
        """Initialize a single specific task

        Parameters
        ----------
        path : str 
            path to YAML file for the specific task

        Returns
        -------
        Dict[str, Any]
            Dictionary of configuration parameters for the specific task    
        """

        config = YAMLFile(path=path)
        config.current_cycle = str(config.SDATE)[0:8]
        config.forecast_hour = str(config.SDATE)[8:10]
        config.job = os.path.basename(path).split('.')[0]

        config.ROTDIR = self[config.PSLOT].parse_config(['config.base'])['ROTDIR']

        config.update(self.host_info)
        config = parse_j2yaml(path=path, data=config)

        return config

    @staticmethod
    @logit(logger)
    def configure(task_dict: Dict, task_yaml: Dict) -> None:
        """Configure a specific task
        Parameters
        ----------
        task_dict : Dict
            Task specific keys
        """
        return None

    @staticmethod
    @logit(logger)
    def execute(pathdir: Union[str, os.PathLike], batch_script, batch_type) -> None:
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

        return None

    @staticmethod
    @logit(logger)
    def finalize(upp_run: Dict, upp_yaml: Dict) -> None:
        """Perform closing actions of the task.
        """

        return None
