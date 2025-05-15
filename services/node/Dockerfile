FROM localhost/base

ARG USER
ARG PROJECT

USER root
RUN apt-get -y update && \
    apt-get -y install curl xz-utils
USER ${USER}

ENV HOME=/home/${USER}
WORKDIR $HOME

RUN curl -sLO https://nodejs.org/dist/v20.10.0/node-v20.10.0-linux-x64.tar.xz && \
    tar xJf node-v20.10.0-linux-x64.tar.xz -C $HOME && \
    rm node-v20.10.0-linux-x64.tar.xz
ENV PATH="${PATH}:$HOME/node-v20.10.0-linux-x64/bin"

WORKDIR /home/${USER}/${PROJECT}
