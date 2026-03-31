COPY --from=assets vscode.deb /tmp/
RUN apt-get -y update && \
    apt-get -y install /tmp/vscode.deb && \
    rm -f /tmp/vscode.deb && \
    apt-get -y clean && rm -rf /var/lib/apt/lists/*
