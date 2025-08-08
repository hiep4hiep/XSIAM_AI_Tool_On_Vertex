for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do sudo apt-get remove $pkg; done
# Add Docker's official GPG key:
sudo apt-get update
sudo apt-get install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

IMAGE_NAME="flask-gunicorn"

# Check if the image exists
if docker image inspect "$IMAGE_NAME" > /dev/null 2>&1; then
    echo "✅ Docker image '$IMAGE_NAME' already exists. Skipping build."
else
    echo "🔨 Building Docker image '$IMAGE_NAME'..."
    docker build -t "$IMAGE_NAME" .
    
    # Check build result
    if [ $? -eq 0 ]; then
        echo "✅ Build completed successfully."
    else
        echo "❌ Build failed."
        exit 1
    fi
fi
# Run the containers
docker compose up -d