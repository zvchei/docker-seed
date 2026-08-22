RUN printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    '' \
    'addr="${CONNECT_ADDRESS:-127.0.0.1}"' \
    '# Allow either "127.0.0.1", "::1", or "[::1]"' \
    'addr="${addr#\[}"' \
    'addr="${addr%\]}"' \
    '' \
    'target="TCP:${addr}:${EXPOSE_PORT}"' \
    'case "$addr" in' \
    '  *:*) target="TCP6:[${addr}]:${EXPOSE_PORT}" ;;' \
    'esac' \
    '' \
    'exec socat TCP-LISTEN:${EXPOSE_PORT},fork,reuseaddr,bind=0.0.0.0 "$target"' \
    > /usr/local/bin/ex_port.sh && chmod +x /usr/local/bin/ex_port.sh
