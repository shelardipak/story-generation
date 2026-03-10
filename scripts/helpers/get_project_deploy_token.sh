#!/usr/bin/env bash

get_project_deploy_token () {
  set -euo pipefail

  cluster_hostname="app-services.${5}-${6}.cust.az.mandg.com"

  printf '%s\n' "Getting deploy token for project '${7}' on cluster '${cluster_hostname}'"

  source scripts/helpers/get_cluster_security_key_vault_name.sh
  source scripts/helpers/login_to_az.sh

  get_cluster_security_key_vault_name \
    "${1}" \
    "${2}" \
    "${3}" \
    "${4}" \
    "${5}" \
    "${6}"

  login_to_az \
    "${1}" \
    "${2}" \
    "${3}" \
    "${4}"

  project_provisioner_token=$(az keyvault secret show \
    --vault-name "${cluster_security_key_vault_name}" \
    --name "pas-project-provisioner-token" \
    | jq -r '.value')

  az logout

  oc login \
    --server "https://api.${cluster_hostname}:6443" \
    --token "${project_provisioner_token}" \
    > /dev/null

  oc project "${7}" \
    > /dev/null

  project_deploy_token=$(oc create token "pas-deployer")

  oc logout \
    > /dev/null
}
