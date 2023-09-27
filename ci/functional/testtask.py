#!/usr/bin/env python3

import os
from logging import getLogger
from typing import Dict, Any, Union
from pprint import pformat

from wxflow import (AttrDict,
                    Configuration,
                    parse_j2yaml,
                    FileHandler,
                    Jinja,
                    logit,
                    Task,
                    add_to_datetime, to_timedelta,
                    WorkflowException,
                    Executable, which)

logger = getLogger(__name__.split('.')[-1])


class TestTask(Task):
    """Unified Post Processor Task
    """

    @logit(logger, name="TestTask")
    def __init__(self, config : Dict[str, Any]) -> None:
        """Constructor for the TestTask task
        The constructor is responsible for getting a collection of Configure objects
        each for the experiments directories that are used for the functional tests.

        Returns
        -------
        None
        """
   
        # Get the list of the experiment directories 
        subdirectories = []
        directory = os.path.join(self.config.FUNCTESTS_DATA_ROOT,'RUNTESTS','EXPTDIR')
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if os.path.isdir(path):
                subdirectories.append(path)

        self.exp_configs = {}
        for subdirectory in subdirectories:
            pslot = re.sub(r"_.*", "", subdirectory)
            self.exp_configs[pslot] = Configuration(subdirectory)

        # Read the upp.yaml file for common configuration
        logger.info(f"Created {len(self.exp_configs)} experiment configurations")

    @staticmethod
    @logit(logger)
    def initialize(task_yaml: Dict) -> None:
        """Initialize a single specific task

        Parameters
        ----------
        task_yaml: Dict
            Fully resolved task.yaml dictionary
        """
        return None

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