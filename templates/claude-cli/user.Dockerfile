
COPY --from=assets claude-install.sh ./
# Upstream installs under ~/.local/share/claude, but chrome (and similar)
# mounts .local at runtime, which hides that tree. Keep the payload under
# ~/.claude-code so symlinks in ~/.local/bin stay valid.
# Version binaries are named by version (e.g. 2.1.274), not "claude".
RUN bash claude-install.sh && \
    mv "$HOME/.local/share/claude" "$HOME/.claude-code" && \
    BIN="$(find "$HOME/.claude-code/versions" -type f | sort -V | tail -n1)" && \
    test -n "$BIN" && test -x "$BIN" && \
    mkdir -p "$HOME/.local/bin" && \
    ln -sfn "$BIN" "$HOME/.local/bin/claude"
ENV PATH="$HOME/.local/bin:$PATH"
RUN printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
