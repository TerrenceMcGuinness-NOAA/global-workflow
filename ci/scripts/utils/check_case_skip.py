#!/usr/bin/env python3
import os
import sys
from wxflow import parse_j2yaml
from wxflow import AttrDict
from workflow import hosts

_here = os.path.dirname(__file__)
_top = os.path.abspath(os.path.join(os.path.abspath(_here), '../../..'))

if __name__ == '__main__':

    HOMEgfs = _top
    data = AttrDict(HOMEgfs=_top)
    host = hosts.Host()

    case_name = sys.argv[1]
    case_yaml = HOMEgfs + '/ci/cases/pr/'+case_name+'.yaml'
    data.update(os.environ)
    case_conf = parse_j2yaml(path=case_yaml, data=data)

    if 'skip_ci_on_hosts' not in case_conf:
        print('true')
        sys.exit(0)

    if host.machine.lower() in [machine.lower() for machine in case_conf.skip_ci_on_hosts]:
        #print(f'Skipping creation of case: {case_name} on {host.machine.capitalize()}')
        print('false')
    else:
        print('true')

