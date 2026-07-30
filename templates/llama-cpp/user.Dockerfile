COPY --from=assets llama-b10173-bin-ubuntu-vulkan-x64.tar.gz ./
RUN mkdir -p "$HOME/.local/bin" && \
    tar -xzf llama-b10173-bin-ubuntu-vulkan-x64.tar.gz && \
    mkdir -p "$HOME/.local/lib" && \
    cp -a llama-b10173/lib*.so* "$HOME/.local/lib/" && \
    find llama-b10173 -maxdepth 1 -type f -perm /111 -exec cp -a {} "$HOME/.local/bin/" \; && \
    find "$HOME/.local/bin" -maxdepth 1 -type f -name 'llama*' -exec chmod +x {} + && \
    rm -rf llama-b10173-bin-ubuntu-vulkan-x64.tar.gz llama-b10173
ENV PATH="$HOME/.local/bin:$PATH"
ENV LD_LIBRARY_PATH="$HOME/.local/lib:$LD_LIBRARY_PATH"
RUN printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
RUN printf '%s\n' 'export LD_LIBRARY_PATH="$HOME/.local/lib:$LD_LIBRARY_PATH"' >> "$HOME/.bashrc"
