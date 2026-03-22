RUN curl -L "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64" -o /tmp/vscode.deb && \
    apt-get -y update && \
    apt-get -y install /tmp/vscode.deb && \
    rm -f /tmp/vscode.deb && \
    apt-get -y clean && rm -rf /var/lib/apt/lists/*
