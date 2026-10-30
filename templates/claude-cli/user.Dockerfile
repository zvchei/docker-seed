
COPY --from=assets claude-install.sh ./
# The root filesystem is read-only at runtime, so the build that ships with the
# image lives under ~/.claude-code, and the auto-updater installs newer builds
# into the claude_versions volume (~/.local/share/claude). Its staging and lock
# directories are volumes too, and must start out empty.
RUN bash claude-install.sh && \
    mkdir -p "$HOME/.claude-code" && \
    mv "$HOME/.local/share/claude/versions" "$HOME/.claude-code/versions" && \
    find "$HOME/.local/share/claude" "$HOME/.local/state/claude" "$HOME/.cache/claude" \
        -mindepth 1 -delete && \
    rm -f "$HOME/.local/bin/claude" claude-install.sh

# ~/.local/bin is read-only too, so ~/.local/bin/claude is a launcher rather
# than the updater's symlink. The updater leaves a launcher alone and skips
# its own cleanup of old builds, so the launcher does both jobs.
COPY --chown=${USER} --chmod=755 <<'EOF' $HOME/.local/bin/claude
#!/bin/sh
# Run the newest Claude Code build: the image's own, or a newer one the
# auto-updater installed into the claude_versions volume.
updates="$HOME/.local/share/claude/versions"
builds() {
    find "$@" -maxdepth 1 -type f -size +0 -perm -u+x \
        -regex '.*/[0-9]+\.[0-9]+\.[0-9]+' -printf '%f %p\n' 2>/dev/null |
        sort -V -k1,1 | cut -d' ' -f2-
}
# Keep the three newest updates; older ones only take up volume space.
builds "$updates" | head -n -3 | xargs -r rm -f --
newest=$(builds "$updates" "$HOME/.claude-code/versions" | tail -n1)
if [ -z "$newest" ]; then
    echo "claude: no Claude Code build found" >&2
    exit 1
fi
exec "$newest" "$@"
EOF
ENV PATH="$HOME/.local/bin:$PATH"
RUN printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
