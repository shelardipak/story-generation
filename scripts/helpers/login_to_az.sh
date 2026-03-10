#!/usr/bin/env bash

login_to_az() {
  set -euo pipefail

  printf '%s\n' "Logging into az"

  az login \
    --service-principal \
    --username "${1}" \
    --password "${2}" \
    --tenant "${4}" \
    > /dev/null

  az account set \
    --subscription "${3}" \
    > /dev/null
}
