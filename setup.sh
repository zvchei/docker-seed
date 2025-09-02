#!/bin/bash

set -e  # Exit on any error.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICES_DIR="$SCRIPT_DIR/services"
SERVICES_LIST="$SCRIPT_DIR/services.list"

echo "Starting setup..."

# Run the setup scripts for each service

failed_count=0
success_count=0

while IFS= read -r service_name || [ -n "$service_name" ]; do
    # Skip empty lines and comments
    [[ -z "$service_name" || "$service_name" =~ ^# ]] && continue

    service_dir="$SERVICES_DIR/$service_name"

    if [ -f "$service_dir/setup.sh" ]; then
        echo ""
        setup_script="$service_dir/setup.sh"
        if [ ! -x "$setup_script" ]; then
            echo -en "\033[31m✗\033[0m "
            echo "Warning: $setup_script is not executable."
            failed_count=$((failed_count + 1))
        else
            echo -en "\033[34m⚙\033[0m "
            echo "Running setup for $service_name..."
            cd "$service_dir"
            if bash "$(basename "$setup_script")"; then
                echo -en "\033[32m✓\033[0m "
                echo "Setup completed successfully for $service_name."
                success_count=$((success_count + 1))
            else
                echo -en "\033[31m✗\033[0m "
                echo "Setup failed for $service_name!"
                failed_count=$((failed_count + 1))
            fi
            cd "$SCRIPT_DIR"
        fi
    fi
done < "$SERVICES_LIST"

echo ""

if [ $failed_count -gt 0 ]; then
    echo ""
    echo "⚠️  Some setup scripts failed. Please check the output above for details."
    exit 1
else
    echo -en "\033[32m✓\033[0m "
    echo "All setup scripts completed successfully!"
fi

# Generate docker-compose.yaml from the list of services

DOCKER_COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yaml"
echo "include:" > "$DOCKER_COMPOSE_FILE"
echo -e "  - services/common/docker-compose.yaml" >> "$DOCKER_COMPOSE_FILE"

echo ""
echo -en "\033[34m⚙\033[0m "
echo "Generating docker-compose.yaml from the list of services:"
while IFS= read -r service_name || [ -n "$service_name" ]; do
    [[ -z "$service_name" || "$service_name" =~ ^# ]] && continue
    compose_file="services/$service_name/docker-compose.yaml"
    echo -e "  - $compose_file" >> "$DOCKER_COMPOSE_FILE"
    echo -en "\t\033[37m◦\033[0m "
    echo "$service_name"
done < "$SERVICES_LIST"

echo -en "\033[32m✓\033[0m "
echo "Done."

# Configure the project variables

echo ""
echo "Setting up project variables:"
echo ""

ENV_FILE="$SCRIPT_DIR/.env"
ENV_TMP="$SCRIPT_DIR/.env.tmp"

# Load the variables into a dictionary
declare -A env_vars
declare -a env_order  # To maintain order of variables
while IFS= read -r line || [ -n "$line" ]; do
    # Skip empty lines and comments
    if [[ -z "$line" || "$line" =~ ^# ]]; then
        continue
    fi
    
    var_name="${line%%=*}"
    current_value="${line#*=}"
    env_vars["$var_name"]="$current_value"
    env_order+=("$var_name")
done < "$ENV_FILE"

# Loop through the variables and prompt for new values
while true; do
    for var_name in "${env_order[@]}"; do
        current_value="${env_vars[$var_name]}"
        
        # Prompt user for new value
        echo -en "\033[33m?\033[0m "
        read -p "Enter value for $var_name [$current_value]: " new_value
        
        # Update the dictionary with new value if provided
        if [ -n "$new_value" ]; then
            env_vars["$var_name"]="$new_value"
        fi
    done

    echo ""
    echo "Current configuration:"
    echo ""
    
    # Show the updated configuration
    for var_name in "${env_order[@]}"; do
        echo -en "\033[37m◦\033[0m "
        echo "$var_name=${env_vars[$var_name]}"
    done

    echo ""
    while true; do
        read -p "Is this correct? [y/n]: " confirm
        
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            break 2  # Break out of both loops
        elif [[ "$confirm" =~ ^[Nn]$ ]]; then
            echo ""
            echo -en "\033[33m↻\033[0m "
            break  # Break out of inner loop to restart
        fi
    done
done

# Create an empty .env.tmp file
> "$ENV_TMP"

# Populate the .env.tmp file with the new environment variables
while IFS= read -r line || [ -n "$line" ]; do
    # Check if this is a variable line
    if [[ -n "$line" && ! "$line" =~ ^# && "$line" =~ = ]]; then
        var_name="${line%%=*}"
        # Use updated value from dictionary if it exists
        if [[ -n "${env_vars[$var_name]}" ]]; then
            echo "$var_name=${env_vars[$var_name]}" >> "$ENV_TMP"
        else
            # Keep original line if variable not in our dictionary
            echo "$line" >> "$ENV_TMP"
        fi
    else
        # Preserve comments and blank lines as-is
        echo "$line" >> "$ENV_TMP"
    fi
done < "$ENV_FILE"

# Copy .env.tmp to .env
cp "$ENV_TMP" "$ENV_FILE"
rm -f "$ENV_TMP"

echo -en "\033[32m✓\033[0m "
echo "Environment variables saved."

echo ""
read -p "Do you want to proceed with \`docker-compose build\`? [Y/n]: " answer
echo ""
answer=${answer:-y}
if [[ "$answer" =~ ^[Yy]$ ]]; then
    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose build
    else
        echo "⚠️  Error: docker-compose is not installed or not in PATH."
        exit 1
    fi
else
    echo "Use \`docker-compose build\` to manually create the service images."
fi
