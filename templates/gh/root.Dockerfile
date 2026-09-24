# Install GitHub CLI from GitHub's official apt repository.
# User config and credentials persist under ~/.config/gh.
RUN apt-get update && \
    apt-get install -y ca-certificates curl && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg && \
    printf 'Types: deb\nURIs: https://cli.github.com/packages\nSuites: stable\nComponents: main\nArchitectures: %s\nSigned-by: /etc/apt/keyrings/githubcli-archive-keyring.gpg\n' \
        "$(dpkg --print-architecture)" \
        > /etc/apt/sources.list.d/github-cli.sources && \
    apt-get update && \
    apt-get install -y gh && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
