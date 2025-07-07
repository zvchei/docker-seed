FROM localhost/base

ARG USER
ARG PROJECT

USER root
RUN apt-get -y update && \
    apt-get -y install curl xz-utils
USER ${USER}

ENV HOME=/home/${USER}
WORKDIR $HOME

ARG NODE_VERSION=v22.17.0
ARG NODE_NAME=node-${NODE_VERSION}-linux-x64

RUN curl -sLO https://nodejs.org/dist/${NODE_VERSION}/${NODE_NAME}.tar.xz && \
    tar xJf ${NODE_NAME}.tar.xz -C $HOME && \
    rm ${NODE_NAME}.tar.xz
ENV PATH="${PATH}:$HOME/${NODE_NAME}/bin"

WORKDIR /home/${USER}/${PROJECT}
