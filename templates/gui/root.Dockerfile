ENV DEBCONF_NOWARNINGS=yes
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get -y install xvfb x11vnc && \
    apt-get -y clean && \
    rm -rf /var/lib/apt/lists/*
