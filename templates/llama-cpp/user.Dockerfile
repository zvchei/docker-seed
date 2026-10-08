COPY --from=assets llama-b11476-bin-ubuntu-cuda-12.8-x64.tar.gz cudart-llama-b11476-bin-ubuntu-cuda-12.8-x64.tar.gz ./
RUN mkdir -p "$HOME/.local/bin" "$HOME/.local/lib" && \
    tar -xzf llama-b11476-bin-ubuntu-cuda-12.8-x64.tar.gz && \
    cp -a llama-b11476/lib*.so* "$HOME/.local/lib/" && \
    find llama-b11476 -maxdepth 1 -type f -perm /111 -exec cp -a {} "$HOME/.local/bin/" \; && \
    find "$HOME/.local/bin" -maxdepth 1 -type f -name 'llama*' -exec chmod +x {} + && \
    rm -rf llama-b11476-bin-ubuntu-cuda-12.8-x64.tar.gz llama-b11476

# Bundled CUDA runtime matching the binaries' build (b11476/CUDA 12.8), since
# Ubuntu's packaged libcudart12/libcublas12 lag behind at an older CUDA minor version.
RUN tar -xzf cudart-llama-b11476-bin-ubuntu-cuda-12.8-x64.tar.gz && \
    cp -a cudart-llama-b11476-bin-ubuntu-cuda-12.8-x64/lib*.so* "$HOME/.local/lib/" && \
    rm -rf cudart-llama-b11476-bin-ubuntu-cuda-12.8-x64.tar.gz cudart-llama-b11476-bin-ubuntu-cuda-12.8-x64
ENV PATH="$HOME/.local/bin:$PATH"
ENV LD_LIBRARY_PATH="$HOME/.local/lib:$LD_LIBRARY_PATH"
RUN printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
RUN printf '%s\n' 'export LD_LIBRARY_PATH="$HOME/.local/lib:$LD_LIBRARY_PATH"' >> "$HOME/.bashrc"
