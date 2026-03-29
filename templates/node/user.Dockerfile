ARG NODE_VERSION=v22.17.0
ARG NODE_NAME=node-${NODE_VERSION}-linux-x64

RUN curl -sLO https://nodejs.org/dist/${NODE_VERSION}/${NODE_NAME}.tar.xz && \
    tar xJf ${NODE_NAME}.tar.xz -C $HOME && \
    rm ${NODE_NAME}.tar.xz
ENV PATH="${PATH}:$HOME/${NODE_NAME}/bin"

ENV NODE_REPL_HISTORY=$HOME/.node/.node_repl_history
