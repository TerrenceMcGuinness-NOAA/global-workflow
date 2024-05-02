#!/usr/bin/env bash
#  --data-urlencode json='{"parameter": [{"name":"machine", "value":"orion"}, {"name":"Node", "value":"Orion-EMC]}'

curl -X POST http://localhost:8080/job/global-workflow/job/EMC-Global-Pipeline/job/PR-283/buildWithParameters --user tmcguinness:11febef402b1ba0d72f602c70a4164e05b --data machine=orion --data Node="Orion-EMC"
