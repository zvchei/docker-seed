RUN mkdir -p $HOME/.copilot
RUN curl -fsSL https://gh.io/copilot-install | bash
ENV PATH="$HOME/.local/bin:$PATH"
RUN printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
