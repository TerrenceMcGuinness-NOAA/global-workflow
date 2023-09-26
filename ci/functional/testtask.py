#!/usr/bin/env python3

import os
from logging import getLogger
from typing import Dict, Any, Union
from pprint import pformat

from wxflow import (AttrDict,
                    parse_j2yaml,
                    FileHandler,
                    Jinja,
                    logit,
                    Task,
                    add_to_datetime, to_timedelta,
                    WorkflowException,
                    Executable, which)

logger = getLogger(__name__.split('.')[-1])


class Test(Task):
    """Unified Post Processor Task
    """

    @logit(logger, name="TestTask")
    def __init__(self, config: Dict[str, Any]) -> None:
        """Constructor for the TestTask task
        The constructor is responsible for resolving the "FUNCTIONAL_CONFIG"
        that is passed in as an argument to the functional test driver
        it will have all the necessary configuration to run the test

        Parameters
        ----------
        config : Dict[str, Any]
            Incoming configuration for the task from the environment

        Returns
        -------
        None
        """
        super().__init__(config)

        localdict = AttrDict(
            {'PSLOT': self.config.PSLOT,
             'SDATE': self.config.SDATE,
             'ICSDIR': self.config.ICSDIR,
             'forecast_hour': str(self.config.SDATE)[8:10],
             'current_cycle': str(self.config.SDATE)[0:8],
             }
        )
        self.task_config = AttrDict(**self.config, **self.runtime_config, **localdict)

        # Read the upp.yaml file for common configuration
        logger.info(f"Read the TestTask configuration yaml file {self.config.TASK_CONFIG}")
        self.task_config.test_yaml = parse_j2yaml(self.config.TASK_CONFIG, self.task_config)
        logger.debug(f"task_yaml:\n{pformat(self.task_config.test_yaml)}")

    @staticmethod
    @logit(logger)
    def initialize(task_yaml: Dict) -> None:
        """Initialize the staged directory by copying all the required input data

        Parameters
        ----------
        task_yaml: Dict
            Fully resolved task.yaml dictionary
        """

        # Copy input data to run directory
        logger.info("Copy input data to run directory")
        FileHandler(task_yaml.upp.stage_data).sync()

    @staticmethod
    @logit(logger)
    def configure(upp_dict: Dict, upp_yaml: Dict) -> None:
        """Configure the artifacts in the work directory.
        Copy run specific data to run directory
        Create namelist 'itag' from template

        Parameters
        ----------
        upp_dict : Dict
            Task specific keys e.g. upp_run
        upp_yaml : Dict
            Fully resolved upp.yaml dictionary
        """

        # Copy "upp_run" specific data to run directory
        logger.info(f"Copy '{upp_dict.upp_run}' data to run directory")
        FileHandler(upp_yaml[upp_dict.upp_run].data_in).sync()

        # Make a localconf with the upp_run specific configuration
        # First make a shallow copy for local use
        localconf = upp_dict.copy()
        # Update 'config' part of the 'run'
        localconf.update(upp_yaml.upp.config)
        localconf.update(upp_yaml[localconf.upp_run].config)
        logger.debug(f"Updated localconf with upp_run='{localconf.upp_run}':\n{pformat(localconf)}")

    @staticmethod
    @logit(logger)
    def execute(workdir: Union[str, os.PathLike], aprun_cmd: str, forecast_hour: int = 0) -> None:
        """Run the UPP executable and index the output master and flux files

        Parameters
        ----------
        workdir : str | os.PathLike
            work directory with the staged data, parm files, namelists, etc.
        aprun_cmd : str
            launcher command for UPP.x
        forecast_hour : int
            default: 0
            forecast hour being processed

        Returns
        -------
        None
        """

        # Run the UPP executable
        UPP.run(workdir, aprun_cmd)

        # Index the output grib2 file
        UPP.index(workdir, forecast_hour)

    @classmethod
    @logit(logger)
    def run(cls, workdir: Union[str, os.PathLike], aprun_cmd: str, exec_name: str = 'upp.x') -> None:
        """
        Run the UPP executable

        Parameters
        ----------
        workdir : str | os.PathLike
            Working directory where to run containing the necessary files and executable
        aprun_cmd : str
            Launcher command e.g. mpirun -np <ntasks> or srun, etc.
        exec_name : str
            Name of the UPP executable e.g. upp.x

        Returns
        -------
        None
        """
        os.chdir(workdir)

        exec_cmd = Executable(aprun_cmd)
        exec_cmd.add_default_arg(os.path.join(workdir, exec_name))

        UPP._call_executable(exec_cmd)


    @staticmethod
    @logit(logger)
    def _call_executable(exec_cmd: Executable) -> None:
        """Internal method to call executable

        Parameters
        ----------
        exec_cmd : Executable
            Executable to run

        Raises
        ------
        OSError
            Failure due to OS issues
        WorkflowException
            All other exceptions
        """

        logger.info(f"Executing {exec_cmd}")
        try:
            exec_cmd()
        except OSError:
            logger.exception(f"FATAL ERROR: Failed to execute {exec_cmd}")
            raise OSError(f"{exec_cmd}")
        except Exception:
            logger.exception(f"FATAL ERROR: Error occurred during execution of {exec_cmd}")
            raise WorkflowException(f"{exec_cmd}")

    @staticmethod
    @logit(logger)
    def finalize(upp_run: Dict, upp_yaml: Dict) -> None:
        """Perform closing actions of the task.
        Copy data back from the DATA/ directory to COM/

        Parameters
        ----------
        upp_run: str
           Run type of UPP
        upp_yaml: Dict
            Fully resolved upp.yaml dictionary
        """

        # Copy "upp_run" specific generated data to COM/ directory
        logger.info(f"Copy '{upp_run}' processed data to COM/ directory")
        FileHandler(upp_yaml[upp_run].data_out).sync()
