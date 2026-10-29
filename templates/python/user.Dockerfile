RUN python3 -m venv env && \
    env/bin/pip install --upgrade pip && \
    echo "source $HOME/env/bin/activate" >> $HOME/.bashrc
ENV PATH="$HOME/env/bin:$PATH"
