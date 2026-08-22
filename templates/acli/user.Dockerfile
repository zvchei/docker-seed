
COPY --from=assets acli_1.3.29-stable_linux_amd64.tar.gz ./
RUN mkdir -p "$HOME/.local/bin" && \
    tar -xzf acli_1.3.29-stable_linux_amd64.tar.gz && \
    mv acli_1.3.29-stable_linux_amd64/acli "$HOME/.local/bin/acli" && \
    chmod +x "$HOME/.local/bin/acli" && \
    rm -rf acli_1.3.29-stable_linux_amd64.tar.gz acli_1.3.29-stable_linux_amd64
ENV PATH="$HOME/.local/bin:$PATH"
RUN printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
