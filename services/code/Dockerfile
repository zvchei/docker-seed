FROM localhost/base

ARG USER
ARG PROJECT

USER root
RUN apt-get -y update && \
    apt-get -y install curl gpg git
RUN curl -L "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64" -o /tmp/vscode.deb
RUN apt-get -y install /tmp/vscode.deb && \
    rm -f /tmp/vscode.deb && \
    apt-get -y clean && \
    rm -rf /var/lib/apt/lists/*
USER ${USER}

COPY --chown=${USER} --from=base configure-git.sh /home/${USER}/
ARG GIT_AUTHOR_NAME
ARG GIT_AUTHOR_EMAIL
ENV GIT_AUTHOR_NAME=${GIT_AUTHOR_NAME}
ENV GIT_AUTHOR_EMAIL=${GIT_AUTHOR_EMAIL}
RUN bash /home/${USER}/configure-git.sh

RUN mkdir /home/${USER}/.vscode
RUN mkdir /home/${USER}/.vscode-server
RUN mkdir /home/${USER}/.cache

# Directories for any additional volumes must be created here to ensure writing
# permissions from within the container.

CMD ["code", "serve-web", "--host", "0.0.0.0", "--port", "8080", "--without-connection-token"]
