FROM ubuntu:latest

ARG USER
ARG USER_ID
ARG PROJECT

ENV DEBCONF_NOWARNINGS=yes
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get -y install xvfb x11vnc

RUN groupadd -g ${USER_ID} ${USER}
RUN useradd ${USER} -u ${USER_ID} -g ${USER_ID} -m -s /bin/bash
USER ${USER}

RUN mkdir /home/${USER}/${PROJECT}
# Directories for additional repositories must be created here, otherwise they
# won't be writable from within the container.

WORKDIR /home/${USER}/${PROJECT}

# Override $ENTRY with the project actual entrypoint:
ENV ENTRY="xmessage 'Hello, world!'"
ENTRYPOINT ["xvfb-run", "bash", "-c", "x11vnc -forever & ${ENTRY}"]
