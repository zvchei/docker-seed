ARG NODE_VERSION=v22.23.3
ARG NODE_NAME=node-${NODE_VERSION}-linux-x64

COPY --from=assets ${NODE_NAME}.tar.xz ./
RUN tar xJf ${NODE_NAME}.tar.xz -C $HOME && \
    rm ${NODE_NAME}.tar.xz
ENV PATH="${PATH}:$HOME/${NODE_NAME}/bin"

ENV NODE_REPL_HISTORY=$HOME/.node/.node_repl_history
