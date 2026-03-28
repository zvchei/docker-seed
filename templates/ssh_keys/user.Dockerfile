RUN mkdir --mode=0700 $HOME/.ssh
COPY --chown=${USER} --from=ssh_keys * $HOME/.ssh/
