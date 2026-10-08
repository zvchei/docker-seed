ARG TWG_VERSION=1.3.5
ARG TWG_SHA256=d66d93220f440f006279c6687274ed4c924835da4ec205cc818bc17f6dd91c08

# Run `twg login` and `twg skills install` inside the container; auth persists under ~/.config/twg.
COPY --chown=${USER}:${USER} --from=assets twg-linux-x64-v${TWG_VERSION} ./
RUN echo "${TWG_SHA256}  twg-linux-x64-v${TWG_VERSION}" | sha256sum -c - && \
    mkdir -p "$HOME/.local/bin" && \
    mv twg-linux-x64-v${TWG_VERSION} "$HOME/.local/bin/twg" && \
    chmod +x "$HOME/.local/bin/twg"
ENV PATH="$HOME/.local/bin:$PATH"
RUN printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
