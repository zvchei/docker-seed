FROM localhost/base

ARG USER
ARG PROJECT

RUN mkdir -p /home/${USER}/.local && \
    mkdir -p /home/${USER}/.jupyter

RUN env/bin/pip install jupyterlab

WORKDIR /home/${USER}/${PROJECT}

CMD ["bash", "-c", "source ../env/bin/activate; jupyter lab --ip=0.0.0.0"]
