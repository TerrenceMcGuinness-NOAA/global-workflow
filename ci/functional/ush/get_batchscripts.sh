#!/usr/bin/env bash

#set -eux

EXPDIR=$1
job=$2
SDATE=$3
PSLOT=$(basename "${EXPDIR}")

rocotorun -d "${EXPDIR}/${PSLOT}.db" -w "${EXPDIR}/${PSLOT}.xml" -c "${SDATE}00" -t $job
list_jobs=$(rocotostat -d "${EXPDIR}/${PSLOT}.db" -w "${EXPDIR}/${PSLOT}.xml" | grep -Ev 'CYCLE|===' | awk '{print $2}' || true)

regex="\{\{(.*)\}\}"

if [[ "${list_jobs}}" != *"${job}"* ]]; then
 echo "ERROR: ${job} is not in Task List for ${PSLOT}"
 echo -e "\nFull job list: ${list_jobs}\n"
 exit 1
fi

rm -f /tmp/temp.txt
rocotoboot -v 10 -d "${EXPDIR}/${PSLOT}.db" -w "${EXPDIR}/${PSLOT}.xml" -c "${SDATE}00" -t "${job}" >& /tmp/temp.txt || true
sub_script=$(cat /tmp/temp.txt)
rocotorewind -d "${EXPDIR}/${PSLOT}.db" -w "${EXPDIR}/${PSLOT}.xml" -c "${SDATE}00" -t "${job}"
batch_script="${job}".sub
if [[ "${sub_script}" =~ ${regex} ]]; then
   echo "${BASH_REMATCH[1]}" | tr -s '\n' > "${EXPDIR}/${batch_script}"
fi
sed -i "/^\s*$/d" "${EXPDIR}/${batch_script}"
