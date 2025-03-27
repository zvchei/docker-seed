FROM localhost/base

ARG USER
ARG PROJECT

RUN env/bin/pip install jupyterlab

WORKDIR /home/${USER}/${PROJECT}

CMD ["bash", "-c", "source ../env/bin/activate; jupyter lab --ip=0.0.0.0"]
