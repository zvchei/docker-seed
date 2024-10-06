FROM node:lts-bookworm AS theia

ARG USER
ARG USER_ID
ARG PROJECT

ENV DEBCONF_NOWARNINGS=yes
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update
RUN apt-get -y upgrade
RUN apt-get -y install libsecret-1-dev libxkbfile-dev

RUN groupadd -g ${USER_ID} ${USER}
RUN useradd ${USER} -u ${USER_ID} -g ${USER_ID} -m -s /bin/bash
USER ${USER}

WORKDIR /home/${USER}/theia

COPY --chown=node:node scripts/theia.package.json package.json
RUN yarn install
RUN yarn theia build

# To install the built-in plugins defined in theia's package.json file uncomment the next line.
# RUN yarn theia download:plugins --ignore-errors

# To install custom plugins, unpack them in a directory called 'plugins' and uncomment the next line.
# COPY --chown=node:node plugins plugins/

FROM node:lts-bookworm AS dev

ARG USER
ARG USER_ID
ARG PROJECT

ENV DEBCONF_NOWARNINGS=yes
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update
RUN apt-get -y upgrade

RUN groupadd -g ${USER_ID} ${USER}
RUN useradd ${USER} -u ${USER_ID} -g ${USER_ID} -m -s /bin/bash
USER ${USER}

ENV PROJECT=${PROJECT}
ENV SHELL=/bin/bash
ENV THEIA_DEFAULT_PLUGINS=local-dir:/home/${USER}/theia/plugins

RUN mkdir /home/${USER}/theia
WORKDIR /home/${USER}/theia
COPY --from=theia --chown=node:node /home/${USER}/theia .

RUN mkdir /home/${USER}/${PROJECT}

CMD bash -c "yarn theia start /home/${USER}/${PROJECT} --hostname 0.0.0.0 --port 8080"
