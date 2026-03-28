FROM localhost/base

ARG USER
ARG PROJECT
ENV HOME=/home/${USER}
ARG GIT_AUTHOR_NAME
ENV GIT_AUTHOR_NAME=${GIT_AUTHOR_NAME}
ARG GIT_AUTHOR_EMAIL
ENV GIT_AUTHOR_EMAIL=${GIT_AUTHOR_EMAIL}

USER root
RUN apt-get -y update && \
    apt-get -y install git && \
    apt-get -y clean && rm -rf /var/lib/apt/lists/*

USER ${USER}
WORKDIR $HOME

# --- git ---
RUN git config --global user.name "$GIT_AUTHOR_NAME" && \
    git config --global user.email "$GIT_AUTHOR_EMAIL" && \
    git config --global alias.co checkout && \
    git config --global alias.br branch && \
    git config --global alias.ci commit && \
    git config --global alias.st status && \
    git config --global alias.ll "log --oneline -45" && \
    git config --global init.defaultBranch main

# --- ssh_keys ---
RUN mkdir --mode=0700 $HOME/.ssh
COPY --chown=${USER} --from=ssh_keys * $HOME/.ssh/

WORKDIR $HOME/${PROJECT}
