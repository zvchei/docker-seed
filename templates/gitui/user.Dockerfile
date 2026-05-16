
COPY --from=assets gitui-linux-x86_64.tar.gz ./
RUN mkdir -p "$HOME/.local/bin" && \
    tar -xzf gitui-linux-x86_64.tar.gz && \
    mv gitui "$HOME/.local/bin/gitui" && \
    chmod +x "$HOME/.local/bin/gitui" && \
    rm -f gitui-linux-x86_64.tar.gz gitui
ENV PATH="$HOME/.local/bin:$PATH"
RUN printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
