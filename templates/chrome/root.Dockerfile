COPY --from=assets google-chrome-stable_current_amd64.deb /tmp/
RUN apt-get -y update && \
    apt-get -y install -y /tmp/google-chrome-stable_current_amd64.deb && \
    rm -f /tmp/google-chrome-stable_current_amd64.deb && \
    apt-get -y clean && rm -rf /var/lib/apt/lists/*
