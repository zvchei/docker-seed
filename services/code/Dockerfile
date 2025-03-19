FROM ubuntu:latest

ARG USER
ARG USER_ID
ARG PROJECT

ENV DEBCONF_NOWARNINGS=yes
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update
RUN apt-get -y upgrade
RUN apt-get -y install curl gpg git

RUN curl -L "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64" -o /tmp/vscode.deb
RUN apt-get -y install /tmp/vscode.deb

RUN groupadd -g ${USER_ID} ${USER}
RUN useradd ${USER} -u ${USER_ID} -g ${USER_ID} -m -s /bin/bash
USER ${USER}

COPY --chown=${USER} --from=common configure-git.sh /home/${USER}/
ARG GIT_AUTHOR_NAME
ARG GIT_AUTHOR_EMAIL
ENV GIT_AUTHOR_NAME=${GIT_AUTHOR_NAME}
ENV GIT_AUTHOR_EMAIL=${GIT_AUTHOR_EMAIL}
RUN bash /home/${USER}/configure-git.sh

RUN mkdir /home/${USER}/.vscode
RUN mkdir /home/${USER}/.vscode-server
RUN mkdir /home/${USER}/${PROJECT}

CMD ["code", "serve-web", "--host", "0.0.0.0", "--port", "8080", "--without-connection-token"]
