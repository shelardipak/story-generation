#!/usr/bin/env bash

source scripts/helpers/write_secret_values.sh
source scripts/helpers/write_config_values.sh

write_values_file() {
  temp_dir_path=$(mktemp -d)

  values_file_path="${temp_dir_path}/values.yml"

  jq -n \
    --arg imageRef "${1}/${2}:${3}" \
    --arg name "${2}" \
    --arg replicaCount "${4}" \
    --arg version "${3}" \
    '{
      deployment: {
        compoundName: $name,
        compoundVersion: $version,
        imageRef: $imageRef,
        name: $name,
        ports: [
          {
            containerPort: 8501,
            name: "http",
            protocol: "TCP",
          }
        ],
        replicaCount: $replicaCount,
      },
      service: {
        compoundName: $name,
        compoundVersion: $version,
        name: $name,
        ports: [
          {
            name: "http",
            port: 8080,
            protocol: "TCP",
            targetPort: 8501,
          }
        ],
      },
      route: {
        compoundName: $name,
        compoundVersion: $version,
        name: $name,
        host: "qa-testgen-interactive-dashboard.apps.app-services.fat-weu.cust.az.mandg.com",
        serviceName: "qa-testgen-interactive-dashboard"
      }
    }' \
    > "${values_file_path}"

  write_secret_values ${2} ${3}
  write_config_values ${2} ${3}
}
