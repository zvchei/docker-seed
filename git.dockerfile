FROM ubuntu:22.04

ARG USER
ARG REPOSITORY

ENV DEBCONF_NOWARNINGS=yes
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get install git -y

RUN useradd -m ${USER}
USER ${USER}

RUN mkdir --mode=0700 /home/${USER}/.ssh
COPY --chown=${USER} credentials/* /home/${USER}/.ssh/

COPY --chown=${USER} scripts/git-setup.sh /home/${USER}/

ARG GIT_AUTHOR_NAME
ARG GIT_AUTHOR_EMAIL
ENV GIT_AUTHOR_NAME=${GIT_AUTHOR_NAME}
ENV GIT_AUTHOR_EMAIL=${GIT_AUTHOR_EMAIL}
RUN bash /home/${USER}/git-setup.sh

RUN mkdir /home/${USER}/${REPOSITORY}
# Directories for additional repositories must be created here, otherwise they
# won't be writable from within the container.

WORKDIR /home/${USER}/${REPOSITORY}
