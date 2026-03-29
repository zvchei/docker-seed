RUN printf '#!/bin/sh\nexec socat TCP-LISTEN:${EXPOSE_PORT},fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:${EXPOSE_PORT}\n' \
    > /usr/local/bin/ex_port.sh && chmod +x /usr/local/bin/ex_port.sh
