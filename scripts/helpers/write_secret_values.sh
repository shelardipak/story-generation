#!/usr/bin/env bash

format_secret_name() {
    echo "${1}" | tr '[:lower:]' '[:upper:]' | tr '-' '_'
}


write_secret_values() {
    secrets_dir_path=".secrets"
    if [ ! -d "${secrets_dir_path}" ]; then
        echo "No secrets directory found"
        return
    fi

    for file in ${secrets_dir_path}/*.yml; do
        [ -f "${file}" ] || continue

        secret_value=$(yq -r .value ${file})
        filename=$(basename ${file} .yml)

        jq \
            --arg secret_value "${secret_value}" \
            --arg secret_name "${filename}" \
            --arg name "${1}" \
            --arg version "${2}" \
            --arg formatted_secret_name "$(format_secret_name ${filename})" \
            '.secrets += [{
                compoundName: $name,
                compoundVersion: $version,
                name: $secret_name,
                stringData: {
                    ($formatted_secret_name): $secret_value,
                },
            }]' \
            "${values_file_path}" \
            > "${values_file_path}.tmp" \
            && mv "${values_file_path}.tmp" "${values_file_path}"

        jq \
            --arg secret_name "${filename}" \
            '.deployment.envFrom += [{
                secretRef: {
                    name: $secret_name,
                },
            }]' \
            "${values_file_path}" \
            > "${values_file_path}.tmp" \
            && mv "${values_file_path}.tmp" "${values_file_path}"
    done
}