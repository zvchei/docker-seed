FROM localhost/base

ARG USER
ARG PROJECT

ENV DEBCONF_NOWARNINGS=yes
ENV DEBIAN_FRONTEND=noninteractive

USER root
RUN apt-get -y install xvfb x11vnc
# RUN apt-get -y install <packages needed to run the project>
USER ${USER}

# Directories for any additional volumes must be created here to ensure writing
# permissions from within the container.

WORKDIR /home/${USER}/${PROJECT}

# Override $ENTRY with the project actual entrypoint:
ENV ENTRY="xmessage 'Hello, world!'"
ENTRYPOINT ["xvfb-run", "bash", "-c", "x11vnc -forever & ${ENTRY}"]
