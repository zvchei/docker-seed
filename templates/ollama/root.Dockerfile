COPY --from=assets ollama-install.sh /tmp/
RUN bash /tmp/ollama-install.sh
