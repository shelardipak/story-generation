#!/usr/bin/env bash

write_config_values() {
    config_dir_path=".config"
    if [ ! -d "${config_dir_path}" ]; then
        echo "No config directory found"
        return
    fi

    for file in ${config_dir_path}/*.json; do
        [ -f "${file}" ] || continue

        filename=$(basename ${file} .json)

        jq \
            --arg config_name "${filename}" \
            --argjson config_value "$(cat ${file})" \
            --arg name "${1}" \
            --arg version "${2}" \
            '.configMaps += [{
                compoundName: $name,
                compoundVersion: $version,
                name: $config_name,
                data: $config_value,
            }]' \
            "${values_file_path}" \
            > "${values_file_path}.tmp" \
            && mv "${values_file_path}.tmp" "${values_file_path}"

        jq \
            --arg config_name "${filename}" \
            '.deployment.envFrom += [{
                configMapRef: {
                    name: $config_name,
                },
            }]' \
            "${values_file_path}" \
            > "${values_file_path}.tmp" \
            && mv "${values_file_path}.tmp" "${values_file_path}"
    done
}