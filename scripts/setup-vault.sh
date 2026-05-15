#!/bin/bash

# Script to initialize Vault with Docker Hub credentials for Jenkins
echo " Vault Setup Script"
echo "This script will securely store your Docker Hub password in the local Vault container."
echo ""

# Prompt for password without echoing it to the terminal
read -s -p "Enter Docker Hub Password: " DOCKER_PW
echo ""

if [ -z "$DOCKER_PW" ]; then
    echo " Password cannot be empty. Exiting."
    exit 1
fi

# Ensure vault is running
if ! docker ps | grep vault > /dev/null; then
    echo " Starting Vault container..."
    docker-compose up -d vault
    sleep 3
fi

echo "Injecting secret into Vault..."
docker exec -e VAULT_TOKEN=root vault vault kv put secret/docker-hub password="$DOCKER_PW" > /dev/null

if [ $? -eq 0 ]; then
    echo " Success! Secret securely stored at 'secret/docker-hub'."
else
    echo " Failed to store secret. Please check if Vault is running properly."
    exit 1
fi
