# /usr/bin/env bash

if ! docker-compose up -d dev; then
    echo "Failed to start a development container.";
    exit 1;
fi

source .env

CONTAINERS=(`docker-compose ps -q dev`)
HEX=`printf "${CONTAINERS[0]}" | xxd -ps | tr -d "\n"`
code --folder-uri vscode-remote://attached-container+$HEX/home/$CONTAINER_USER/$REPOSITORY
