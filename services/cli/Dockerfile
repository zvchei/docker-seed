FROM ubuntu:latest

ARG USER
ARG USER_ID
ARG PROJECT

ENV DEBCONF_NOWARNINGS=yes
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update
RUN apt-get -y upgrade

RUN groupadd -g ${USER_ID} ${USER}
RUN useradd ${USER} -u ${USER_ID} -g ${USER_ID} -m -s /bin/bash
USER ${USER}

RUN mkdir /home/${USER}/${PROJECT}
# Directories for additional repositories must be created here, otherwise they
# won't be writable from within the container.

WORKDIR /home/${USER}/${PROJECT}
