FROM localhost/base

ARG USER
ARG PROJECT

USER root
RUN apt-get -y update && \
    apt-get -y install python3-venv python3-dev && \
    apt-get -y clean && \
    rm -rf /var/lib/apt/lists/*
USER ${USER}

WORKDIR /home/${USER}

RUN mkdir -p /home/${USER}/.cache/pip

RUN python3 -m venv env && \
    env/bin/pip install --upgrade pip && \
    echo "source /home/${USER}/env/bin/activate" >> /home/${USER}/.bashrc

WORKDIR /home/${USER}/${PROJECT}
