
    #TODO fix this to run test_configuration once!!
    SDATE=$("${HOMEgfs}"/ci/functional/test_configuration.py "${PWD}" | grep SDATE | cut -d ":" -f 2 | tr -d " \t\n\r") || true
    MODE=$("${HOMEgfs}"/ci/functional/test_configuration.py "${PWD}" | grep MODE | cut -d ":" -f 2 | tr -d " \t\n\r") || true
    # TODO get a list of jobs tested by yamls in config dir similar to the cases dir
    if [[ "${MODE}" == "cycled" ]]; then
      job=gdasfcst
    else
      job=gfsfcst
    fi
    "${HOMEgfs}"/ci/functional/get_batchscripts.sh "${PWD}" "${job}" "${SDATE}" || true
