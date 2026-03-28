FROM localhost/base

ARG USER
ARG PROJECT
ENV HOME=/home/${USER}

USER root
RUN apt-get -y update && \
    apt-get -y install python3-venv python3-dev && \
    apt-get -y clean && rm -rf /var/lib/apt/lists/*

USER ${USER}
WORKDIR $HOME

# --- python ---
RUN mkdir -p $HOME/.cache/pip
RUN python3 -m venv env && \
    env/bin/pip install --upgrade pip && \
    echo "source $HOME/env/bin/activate" >> $HOME/.bashrc

WORKDIR $HOME/${PROJECT}
