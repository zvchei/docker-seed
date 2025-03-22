FROM ubuntu:latest

ARG USER
ARG USER_ID
ARG PROJECT

ENV DEBCONF_NOWARNINGS=yes
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get -y install python3-venv python3-dev
        
RUN groupadd -g ${USER_ID} ${USER}
RUN useradd ${USER} -u ${USER_ID} -g ${USER_ID} -m -s /bin/bash
USER ${USER}

# Directories for additional repositories must be created here, otherwise they
# won't be writable from within the container.

RUN mkdir /home/${USER}/${PROJECT}
RUN mkdir -p /home/${USER}/env-jupyter

WORKDIR /home/${USER}

RUN python3 -m venv env-jupyter
RUN env-jupyter/bin/pip install --upgrade pip
RUN env-jupyter/bin/pip install jupyterlab

WORKDIR /home/${USER}/${PROJECT}

CMD ["bash", "-c", "source ../env-jupyter/bin/activate; jupyter lab --ip=0.0.0.0"]
