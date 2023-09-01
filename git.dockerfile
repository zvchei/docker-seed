ENV USER=
ENV VOLUME_A=
# ENV VOLUME_B=
# ENV VOLUME_C=

FROM ubuntu:22.04

ARG DEBCONF_NOWARNINGS=yes
ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get install git -y

RUN useradd -m ${USER}
USER ${USER}

RUN mkdir --mode=0700 /home/${USER}/.ssh
COPY --chown=${USER} credentials/* /home/${USER}/.ssh/

COPY --chown=${USER} scripts/git-setup.sh /home/${USER}/
RUN bash /home/${USER}/git-setup.sh

RUN mkdir /home/${USER}/${VOLUME_A}
# RUN mkdir /home/${USER}/${VOLUME_B}
# RUN mkdir /home/${USER}/${VOLUME_C}

WORKDIR /home/${USER}/${VOLUME_A}
