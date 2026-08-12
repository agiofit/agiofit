#!/usr/bin/env sh
# fetch-licenses.sh — run from the repository root.
# Licence texts are never edited by hand; see LICENSING.md.
set -eu

curl -fsSL https://www.apache.org/licenses/LICENSE-2.0.txt -o LICENSE
curl -fsSL https://creativecommons.org/licenses/by/4.0/legalcode.txt -o LICENSE-SPEC

printf '\n--- sanity check ---\n'
wc -l LICENSE LICENSE-SPEC
printf '\nLICENSE starts with:\n'
head -3 LICENSE
printf '\nLICENSE-SPEC starts with:\n'
head -3 LICENSE-SPEC
printf '\nExpected: "Apache License / Version 2.0, January 2004" and "Attribution 4.0 International".\n'
