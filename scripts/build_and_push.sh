#!/bin/bash

# Configuration
USERNAME="p1yush123"
STACKS=("flask" "java" "mern" "ml")

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting Build & Push process for Intelligent Dev Platform...${NC}"

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Determine the absolute path of the templates directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
TEMPLATES_DIR="$(dirname "$SCRIPT_DIR")/templates"

for stack in "${STACKS[@]}"; do
    echo -e "\n${GREEN}📦 Building image for: ${stack}...${NC}"
    
    cd "${TEMPLATES_DIR}/${stack}" || { echo -e "${RED}Folder not found: ${stack}${NC}"; continue; }
    
    IMAGE_NAME="${USERNAME}/${stack}-env:latest"
    
    # Build image
    docker build -t "${IMAGE_NAME}" .
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Build successful: ${IMAGE_NAME}${NC}"
        
        # Push image
        echo -e "📤 Pushing to Docker Hub..."
        docker push "${IMAGE_NAME}"
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}🚀 Push successful: ${IMAGE_NAME}${NC}"
        else
            echo -e "${RED}❌ Push failed for: ${IMAGE_NAME}. Ensure you are logged in (docker login).${NC}"
        fi
    else
        echo -e "${RED}❌ Build failed for: ${stack}${NC}"
    fi
done

echo -e "\n${GREEN}✨ All operations completed!${NC}"
