
def run_cases = [:]

pipeline {
    agent{ label 'orion-emc'}

    environment {
        RUNTESTS = "${WORKSPACE}/RUNTESTS"
    }

    stages {

        stage('Checkout') {
        agent{ label 'orion-emc'}
            steps {
                checkout scm
                script {
                   pullRequest.removeLabel('CI-Orion-Ready')
                   pullRequest.addLabel('CI-Orion-Building')
                }
                sh 'git submodule update --init --recursive'
            }
        }

        stage('Build') {
        agent{ label 'orion-emc'}
          steps {
            //sh 'sorc/build_all.sh'
            sh 'sorc/link_workflow.sh'
          }
        }
 
        stage('Create Experiments') {
        agent{ label 'orion-emc'}
            steps {
                sh 'mkdir -p ${RUNTESTS}'
                script {
                    pullRequest.removeLabel('CI-Orion-Building')
                    pullRequest.addLabel('CI-Orion-Running')
                    case_list = sh( script: "${WORKSPACE}/ci/scripts/utils/ci_utils_wrapper.sh get_pr_case_list", returnStdout: true ).trim()
                    cases = case_list.tokenize('\n')
                    cases.each { case_name ->
                        stage("Create ${case_name}") {
                        run_cases["${case_name}"] = {
                              agent { node { label 'case-creator'} {
                              script { env.case = case_name }
                              sh '${WORKSPACE}/ci/scripts/utils/ci_utils_wrapper.sh create_experiment ci/cases/pr/${case}.yaml'
                              } 
                        }
                        }
                    }
                    parallel run_cases 
                    script { pullRequest.comment("SUCCESS creating cases: ${cases} on Orion") }
                }
            }
        }
    }    

    post {
        success {
            script {
                pullRequest.removeLabel('CI-Orion-Running')
                pullRequest.addLabel('CI-Orion-Passed')  
            }
        }
        failure {
            script {
                pullRequest.removeLabel('CI-Orion-Running')
                pullRequest.addLabel('CI-Orion-Failed')  
            }
        }
    }
}