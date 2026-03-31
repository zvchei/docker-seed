
COPY --from=assets cursor-install.sh ./
RUN bash cursor-install.sh
ENV PATH="$HOME/.local/bin:$PATH"
RUN printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
