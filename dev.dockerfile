FROM ubuntu:22.04

ARG USER
ARG REPOSITORY

ENV DEBCONF_NOWARNINGS=yes
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update
RUN apt-get upgrade -y

RUN useradd -m ${USER}
USER ${USER}

RUN mkdir /home/${USER}/${REPOSITORY}
# Directories for additional repositories must be created here, otherwise they
# won't be writable from within the container.

WORKDIR /home/${USER}/${REPOSITORY}
