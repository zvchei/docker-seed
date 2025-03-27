FROM localhost/base

ARG USER

USER root
RUN apt-get -y install python3-venv python3-dev
USER ${USER}

WORKDIR /home/${USER}

RUN python3 -m venv env
RUN env/bin/pip install --upgrade pip
