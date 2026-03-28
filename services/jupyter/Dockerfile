FROM localhost/base

ARG USER
ARG PROJECT
ENV HOME=/home/${USER}

USER root
RUN apt-get -y update && \
    apt-get -y install python3-venv python3-dev && \
    apt-get -y clean && rm -rf /var/lib/apt/lists/*

# --- jupyter ---
RUN mkdir -p $HOME/.local && \
    mkdir -p $HOME/.jupyter

USER ${USER}
WORKDIR $HOME

# --- python ---
RUN mkdir -p $HOME/.cache/pip
RUN python3 -m venv env && \
    env/bin/pip install --upgrade pip && \
    echo "source $HOME/env/bin/activate" >> $HOME/.bashrc

# --- jupyter ---
RUN env/bin/pip install jupyterlab

WORKDIR $HOME/${PROJECT}

CMD ["bash", "-c", "source ../env/bin/activate; jupyter lab --ip=0.0.0.0"]
