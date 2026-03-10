#!/usr/bin/env bash

push_image_to_cluster() {
  set -euo pipefail

  cluster_hostname="app-services.${5}-${6}.cust.az.mandg.com"
  source_image_ref="${8}.azurecr.io/${9}"

  printf '%s\n' "Pushing image '${source_image_ref}' to image stream '${10}' on cluster '${cluster_hostname}'"

  source scripts/helpers/get_project_deploy_token.sh
  source scripts/helpers/login_to_az.sh

  login_to_az \
    "${1}" \
    "${2}" \
    "${3}" \
    "${4}"

  acr_access_token=$(az acr login \
    --name "${8}" \
    --expose-token \
    --only-show-errors \
    | jq -r '.accessToken')

  az logout

  get_project_deploy_token \
    "${1}" \
    "${2}" \
    "${3}" \
    "${4}" \
    "${5}" \
    "${6}" \
    "${7}"

  oc login \
    --server "https://api.${cluster_hostname}:6443" \
    --token "${project_deploy_token}" \
    > /dev/null

  oc project "${7}" \
    > /dev/null

  registry_hostname=$(oc registry info)

  oc logout \
    > /dev/null

  skopeo copy \
    --src-creds "00000000-0000-0000-0000-000000000000:${acr_access_token}" \
    --dest-creds "nobody:${project_deploy_token}" \
    "docker://${source_image_ref}" \
    "docker://${registry_hostname}/${10}"
}
