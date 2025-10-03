FROM ubuntu:latest

ARG USER
ARG USER_ID
ARG PROJECT

ENV DEBCONF_NOWARNINGS=yes
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get -y upgrade  && \
    # apt-get -y install <packages common to all services>
    apt-get -y clean

RUN groupadd -g ${USER_ID} ${USER}
RUN useradd ${USER} -u ${USER_ID} -g ${USER_ID} -m -s /bin/bash
USER ${USER}

RUN mkdir /home/${USER}/${PROJECT}

# Directories for any additional volumes common to all services must be
# created here to ensure writing permissions from within the container.
