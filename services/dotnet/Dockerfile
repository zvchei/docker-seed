FROM localhost/base

ARG USER
ARG PROJECT

USER root
RUN apt-get -y update
RUN apt-get -y install curl xz-utils dnsutils libicu74
USER ${USER}

ENV HOME=/home/${USER}
WORKDIR $HOME

COPY --chown=${USER}:${USER} downloads/dotnet.tar.gz .
RUN mkdir -p $HOME/dotnet && tar zxf dotnet.tar.gz -C $HOME/dotnet
RUN rm dotnet.tar.gz
RUN chmod +x $HOME/dotnet/dotnet
ENV PATH="${PATH}:$HOME/dotnet"

COPY --chown=${USER}:${USER} downloads/installcredprovider.sh .
# COPY --chown=${USER}:${USER} --from=secrets secrets.config .

WORKDIR /$HOME/${PROJECT}
