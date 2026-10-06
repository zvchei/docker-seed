COPY --from=assets uv-x86_64-unknown-linux-gnu.tar.gz ./
RUN mkdir -p $HOME/.local/bin && \
    tar xzf uv-x86_64-unknown-linux-gnu.tar.gz --strip-components=1 -C $HOME/.local/bin && \
    rm uv-x86_64-unknown-linux-gnu.tar.gz
ENV PATH="$HOME/.local/bin:${PATH}"
# Interpreter lives in the image, outside any volume, so the venv's symlinks
# always resolve and a PYTHON_VERSION change takes effect on rebuild.
ENV UV_PYTHON_INSTALL_DIR=$HOME/.python

RUN uv python install ${PYTHON_VERSION} && \
    uv venv --clear --seed --python ${PYTHON_VERSION} env && \
    env/bin/pip install --upgrade pip && \
    echo "source $HOME/env/bin/activate" >> $HOME/.bashrc
