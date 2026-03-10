#!/usr/bin/env bash

get_cluster_security_key_vault_name() {
  set -euo pipefail

  cluster_hostname="app-services.${5}-${6}.cust.az.mandg.com"

  printf '%s\n' "Getting security Key Vault name for cluster '${cluster_hostname}'"

  source scripts/helpers/login_to_az.sh

  login_to_az \
    "${1}" \
    "${2}" \
    "${3}" \
    "${4}"

  results=$(az keyvault list \
    --query "[?tags.ClusterHostname == '${cluster_hostname}']")

  if [[ "$?" != "0" ]]; then
    printf '%s\n' "Query for Key Vaults with tag 'ClusterHostname=${cluster_hostname}' failed" >&2
    exit 1
  fi

  az logout

  results_count=$(echo "${results}" | jq '. | length')
  if [[ "${results_count}" == "1" ]]; then
    cluster_security_key_vault_name=$(echo "${results}" | jq -r '.[0].name')
  elif [[ "${results_count}" == "0" ]]; then
    printf '%s\n' "No Key Vaults with tag 'ClusterHostname=${cluster_hostname}' found" >&2
    exit 1
  else
    printf '%s\n' "Multiple Key Vaults with tag 'ClusterHostname=${cluster_hostname}' found" >&2
    exit 1
  fi
}
