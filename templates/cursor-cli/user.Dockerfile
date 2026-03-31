
COPY --from=assets cursor-install.sh ./
# Upstream installs under ~/.local/share/cursor-agent, but the stack mounts
# local_share on ~/.local/share at runtime, which hides that tree. Keep the
# payload under ~/.cursor-agent so symlinks in ~/.local/bin stay valid.
RUN bash cursor-install.sh && \
    mv "$HOME/.local/share/cursor-agent" "$HOME/.cursor-agent" && \
    BIN="$(find "$HOME/.cursor-agent/versions" -type f -name cursor-agent | head -n1)" && \
    ln -sf "$BIN" "$HOME/.local/bin/cursor-agent" && \
    ln -sf "$BIN" "$HOME/.local/bin/agent"
ENV PATH="$HOME/.local/bin:$PATH"
RUN printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
