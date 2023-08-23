#!/usr/env bash

EXPDIR=$1
SDATE=$2
PSLOT=$(basename "${EXPDIR}")

rocotorun -v 10 -d "${EXPDIR}/${PSLOT}.db" -w "${EXPDIR}${PSLOT}.xml" -c "${SDATE}00" -t gfsfcst 2>/dev/null
list_jobs=$(rocotostat -v 10 -d "${EXPDIR}/${PSLOT}.db" -w "${EXPDIR}/${PSLOT}.xml" | grep -Ev 'CYCLE|===' | awk '{print $2}' || true)

regex="\{\{(.*)\}\}"

echo "Full job list: ${list_jobs}"
list_jobs="gfsfcst gfsvrfy gfsarch"
echo "Createing batch scripts for: ${list_jobs}"

for job in ${list_jobs}; do
  echo $job
  rm -f /tmp/temp.txt
  rocotoboot -v 10 -d "${EXPDIR}/${PSLOT}.db" -w "${EXPDIR}/${PSLOT}.xml" -c "${SDATE}00" -t $job >& /tmp/temp.txt || true
  sub_script=$(cat /tmp/temp.txt)
  echo "'rocotorewind -d ${EXPDIR}/${PSLOT}.db -w ${EXPDIR}/${PSLOT}.xml -c ${SDATE}00 -t ${job}"
  rocotorewind -d "${EXPDIR}/${PSLOT}.db" -w "${EXPDIR}/${PSLOT}.xml" -c "${SDATE}00" -t "${job}"
  if [[ $sub_script =~ $regex ]]; then
     echo "${BASH_REMATCH[1]}" | tr -s '\n' > ${job}_${PSLOT}.sub
  fi
done
