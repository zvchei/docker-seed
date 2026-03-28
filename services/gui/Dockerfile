FROM localhost/base

ARG USER
ARG PROJECT
ENV HOME=/home/${USER}

USER root

# --- gui ---
ENV DEBCONF_NOWARNINGS=yes
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get -y install xvfb x11vnc && \
    apt-get -y clean && \
    rm -rf /var/lib/apt/lists/*

USER ${USER}
WORKDIR $HOME

# --- gui ---
# Override $ENTRY with the project actual entrypoint:
ENV ENTRY="xmessage 'Hello, world!'"

WORKDIR $HOME/${PROJECT}

ENTRYPOINT ["xvfb-run", "bash", "-c", "x11vnc -forever & ${ENTRY}"]
