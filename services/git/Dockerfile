FROM localhost/base

ARG USER
ARG PROJECT

USER root
RUN apt-get -y install git
USER ${USER}

RUN mkdir --mode=0700 /home/${USER}/.ssh
COPY --chown=${USER} --from=credentials * /home/${USER}/.ssh/

COPY --chown=${USER} --from=base configure-git.sh /home/${USER}/

ARG GIT_AUTHOR_NAME
ARG GIT_AUTHOR_EMAIL
ENV GIT_AUTHOR_NAME=${GIT_AUTHOR_NAME}
ENV GIT_AUTHOR_EMAIL=${GIT_AUTHOR_EMAIL}
RUN bash /home/${USER}/configure-git.sh

# Directories for any additional volumes must be created here to ensure writing
# permissions from within the container.

WORKDIR /home/${USER}/${PROJECT}
