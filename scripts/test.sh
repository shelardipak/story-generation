#!/usr/bin/env bash

set -euo pipefail

source scripts/helpers/write_values_file.sh

write_values_file \
  "foo" \
  "bar" \
  "1.0.0" \
  "2"
  
helm lint src/helm \
  --values "${values_file_path}"
