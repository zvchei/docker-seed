#!/bin/bash

DOTNET_FILE="dotnet-sdk-8.0.413-linux-x64.tar.gz"
DOTNET_URL="https://builds.dotnet.microsoft.com/dotnet/Sdk/8.0.413/$DOTNET_FILE"

CREDSPROVIDER_FILE="installcredprovider.sh"
CREDSPROVIDER_URL="https://raw.githubusercontent.com/microsoft/artifacts-credprovider/master/helpers/$CREDSPROVIDER_FILE"

FILES=("$DOTNET_FILE" "$CREDSPROVIDER_FILE")
URLS=("$DOTNET_URL" "$CREDSPROVIDER_URL")

SCRIPT_DIR="$(pwd)"

mkdir -p downloads
cd downloads

for i in "${!FILES[@]}"; do
    FILE="${FILES[$i]}"
    URL="${URLS[$i]}"

    if [ -f "$FILE" ]; then
        echo -en "\t\033[37m◦\033[0m "
        echo "$FILE already exists. Skipping download."
    else
        echo -en "\t\033[37m◦\033[0m "
        echo "$FILE not found. Downloading..."
        tmp="${FILE}.partial"

        if curl -L --fail --show-error --progress-bar -o "$tmp" "$URL"; then
            mv "$tmp" "$FILE"
        else
            rm -f "$tmp"
            false
        fi
    fi
    if [ $? -eq 0 ]; then
        echo -en "\t\033[32m✓\033[0m "
        echo "Download completed."
    else
        echo -en "\t\033[33m!\033[0m "
        echo "Download failed!" >&2
        cd "$SCRIPT_DIR"
        exit 1
    fi
done

# Create or update symlink to the dotnet file
ln -sf "$DOTNET_FILE" dotnet.tar.gz

# Return to the original directory
cd "$SCRIPT_DIR"
