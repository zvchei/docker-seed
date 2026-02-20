#!/bin/bash

set -e

# Ensure that the ollama_network exists:

NETWORK_NAME="ollama_network"

if docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    echo -en "\033[32m✓\033[0m "
    echo "Docker network $NETWORK_NAME already exists"
else
    echo -en "\033[34m⚙\033[0m "
    echo "Creating Docker network: $NETWORK_NAME"

    if ID=$(docker network create "$NETWORK_NAME" 2>/dev/null); then
        echo -en "\033[32m✓\033[0m "
        echo "Docker network $NETWORK_NAME created with ID: $ID"
    else
        echo -en "\033[31m✗\033[0m "
        echo "Error: Failed to create Docker network $NETWORK_NAME"
        exit 1
    fi
fi
