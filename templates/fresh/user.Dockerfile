
COPY --from=assets fresh-editor-x86_64-unknown-linux-musl.tar.gz ./
RUN mkdir -p "$HOME/.local/bin" && \
    tar -xzf fresh-editor-x86_64-unknown-linux-musl.tar.gz && \
    mv fresh-editor-x86_64-unknown-linux-musl/fresh "$HOME/.local/bin/fresh" && \
    chmod +x "$HOME/.local/bin/fresh" && \
    rm -rf fresh-editor-x86_64-unknown-linux-musl.tar.gz fresh-editor-x86_64-unknown-linux-musl
ENV PATH="$HOME/.local/bin:$PATH"
RUN printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
