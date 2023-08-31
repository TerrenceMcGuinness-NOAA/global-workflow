#!/usr/bin/env bash

#set -eux

EXPDIR=$1
job=$2
SDATE=$3
PSLOT=$(basename "${EXPDIR}")

rocotorun -d "${EXPDIR}/${PSLOT}.db" -w "${EXPDIR}/${PSLOT}.xml" -c "${SDATE}00" -t $job
list_jobs=$(rocotostat -d "${EXPDIR}/${PSLOT}.db" -w "${EXPDIR}/${PSLOT}.xml" | grep -Ev 'CYCLE|===' | awk '{print $2}' || true)

regex="\{\{(.*)\}\}"

if [[ "${list_jobs}}" == *"${job}"* ]]; then
 echo "Createing batch scripts for: ${job}"
else
 echo "ERROR: ${job} is not in Task List for ${PSLOT}"
 echo "/nFull job list: ${list_jobs}/n"
 exit 1
fi

rm -f /tmp/temp.txt
echo "rocotoboot -v 10 -d ${EXPDIR}/${PSLOT}.db -w ${EXPDIR}/${PSLOT}.xml -c ${SDATE}00 -t ${job}"
rocotoboot -v 10 -d "${EXPDIR}/${PSLOT}.db" -w "${EXPDIR}/${PSLOT}.xml" -c "${SDATE}00" -t "${job}" >& /tmp/temp.txt || true
sub_script=$(cat /tmp/temp.txt)
echo "'rocotorewind -d ${EXPDIR}/${PSLOT}.db -w ${EXPDIR}/${PSLOT}.xml -c ${SDATE}00 -t ${job}"
rocotorewind -d "${EXPDIR}/${PSLOT}.db" -w "${EXPDIR}/${PSLOT}.xml" -c "${SDATE}00" -t "${job}"
if [[ "${sub_script}" =~ ${regex} ]]; then
   echo "${BASH_REMATCH[1]}" | tr -s '\n' > "${job}"_"${PSLOT}".sub
fi
