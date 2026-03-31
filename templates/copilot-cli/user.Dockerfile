
COPY --from=assets copilot-install.sh ./
RUN bash copilot-install.sh
ENV PATH="$HOME/.local/bin:$PATH"
RUN printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
