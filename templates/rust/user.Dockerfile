COPY --from=assets rustup-init.sh ./
RUN sh rustup-init.sh -y --no-modify-path
ENV PATH="${PATH}:$HOME/.cargo/bin"
RUN echo 'export PATH="$PATH:$HOME/.cargo/bin"' >> $HOME/.bashrc
