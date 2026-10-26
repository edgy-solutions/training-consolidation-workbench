#!/bin/sh
# Writes /tmp/config.js from the VITE_* env the chart sets; nginx serves it at /config.js.
set -eu

out="${RUNTIME_CONFIG_OUT:-/tmp/config.js}"

# JSON-string escape: backslash and double quote; drop CR and LF.
esc() { printf '%s' "$1" | tr -d '\r\n' | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }

{
    printf 'window.__RUNTIME_CONFIG__ = {'
    sep=''
    for key in VITE_API_URL VITE_KEYCLOAK_REALM_URL VITE_KEYCLOAK_CLIENT_ID VITE_NO_AUTH; do
        eval "val=\${$key-}"
        [ -n "$val" ] || continue
        printf '%s"%s": "%s"' "$sep" "$key" "$(esc "$val")"
        sep=', '
    done
    printf '};\n'
} > "$out"

echo "40-runtime-config.sh: wrote $out"
