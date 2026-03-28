RUN mkdir -p $HOME/.cache/pip
RUN python3 -m venv env && \
    env/bin/pip install --upgrade pip && \
    echo "source $HOME/env/bin/activate" >> $HOME/.bashrc
