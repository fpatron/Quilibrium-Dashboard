#!/bin/bash

# Function to ask for input
ask() {
    local prompt="$1"
    local default="$2"
    read -p "$prompt [$default]: " input
    echo "${input:-$default}"
}

# Function to check if a directory contains an executable file starting with "node-"
is_valid_node_path() {
    local path=$1
    if [[ -d $path && $(ls "$path" | grep -E '^node-' | xargs -I {} test -x "$path/{}" && echo 1) ]]; then
        return 0
    else
        return 1
    fi
}

# Function to check if a string is a valid URL
is_valid_url() {
    local url=$1
    if [[ $url =~ ^(http|https):\/\/[a-zA-Z0-9.-]+(:[0-9]+)?(\/.*)?$ ]]; then
        return 0
    else
        return 1
    fi
}

# Function to check if a systemd service exists
service_exists() {
    local service=$1
    if systemctl list-units --type=service --all | grep -q "$service.service"; then
        return 0
    else
        return 1
    fi
}

# Check the operating system and version
os_check() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        if [[ "$ID" == "ubuntu" && "${VERSION_ID%.*}" -ge 22 ]]; then
            return 0
        elif [[ "$ID" == "debian" && "${VERSION_ID%.*}" -ge 12 ]]; then
            return 0
        fi
    fi
    return 1
}

# Validate the OS version
validate_os() {
    if ! os_check; then
        echo "Error: This script requires Ubuntu 22.04 or higher, Debian 12 or higher"
        exit 1
    fi
}

# Validate the node path
validate_node_path() {
    if ! is_valid_node_path "$node_path"; then
        echo "Error: The path '$node_path' does not exist or does not contain a Quilibrium node executable file."
        exit 1
    fi
}

# Validate the service name
validate_service_name() {
    if [[ -z "$service_name" ]]; then
        echo "Error: The Quilibrium service name cannot be empty."
        exit 1
    fi

    if ! service_exists "$service_name"; then
        echo "Error: The Quilibrium systemd service '$service_name' does not exist."
        exit 1
    fi
}

# Validate URLs
validate_urls() {
    if ! is_valid_url "$loki_url"; then
        echo "Error: The Loki URL '$loki_url' is not valid ."
        exit 1
    fi
    if ! is_valid_url "$prometheus_url"; then
        echo "Error: The Prometheus URL '$prometheus_url' is not valid."
        exit 1
    fi
}

# Install Quilibrium exporter
install_quilibrium_exporter() {

    echo "Creating necessary directory structure..."
    mkdir -p ~/quilibrium/exporter
    cd ~/quilibrium/exporter

    username=$(whoami)
    exporter_path=$(pwd)

    echo "Downloading the Quilibrium exporter script and requirements..."
    wget https://github.com/fpatron/Quilibrium-Dashboard/raw/master/grafana/exporter/quilibrium_exporter.py
    wget https://github.com/fpatron/Quilibrium-Dashboard/raw/master/grafana/exporter/requirements.txt

    echo "Installing Python3, pip, and virtualenv..."
    sudo apt update
    sudo apt install -y python3 python3-pip python3-virtualenv

    echo "Setting up a virtual environment..."
    virtualenv venv

    echo "Installing required Python packages..."
    venv/bin/pip install -r requirements.txt

    # Create the .env file with the necessary parameters
    echo "Creating .env file with service_name and node_path..."
    cat <<EOL > .env
service_name=$service_name
node_path=$node_path
EOL

    # Create the systemd service file
    echo "Creating systemd service file for Quilibrium exporter..."
    sudo bash -c "cat <<EOL > /lib/systemd/system/quilibrium_exporter.service
[Unit]
Description=Quilibrium Exporter Service
After=network.target
[Service]
User=$username
Group=$username
WorkingDirectory=$exporter_path
ExecStart=$exporter_path/venv/bin/python $exporter_path/quilibrium_exporter.py
Restart=always
[Install]
WantedBy=multi-user.target
EOL"

    echo "Enabling systemd daemon..."
    sudo systemctl daemon-reload
    sudo systemctl enable quilibrium_exporter
    sudo systemctl start quilibrium_exporter
}

# Install Grafana Alloy
install_grafana_alloy() {
    echo "Installing Grafana Alloy..."
    sudo mkdir -p /etc/apt/keyrings/
    wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null
    echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
    sudo apt update
    sudo apt-get install alloy -y
}

# Configure Grafana Alloy
configure_grafana_alloy() {
    echo "Configuring Grafana Alloy..."
    sudo mkdir -p /etc/alloy
    wget https://raw.githubusercontent.com/fpatron/Quilibrium-Dashboard/master/grafana/alloy/config.alloy -O /tmp/config.alloy

    # Replace variables in the config file
    sed -i "s|<PROMETHEUS_ENDPOINT>|$prometheus_url|g" /tmp/config.alloy
    sed -i "s|<PROMETHEUS_USERNAME>|$prometheus_user|g" /tmp/config.alloy
    sed -i "s|<PROMETHEUS_PASSWORD>|$prometheus_api_key|g" /tmp/config.alloy
    sed -i "s|<LOKI_ENDPOINT>|$loki_url|g" /tmp/config.alloy
    sed -i "s|<LOKI_USERNAME>|$loki_user|g" /tmp/config.alloy
    sed -i "s|<LOKI_PASSWORD>|$loki_api_key|g" /tmp/config.alloy

    sudo mv /tmp/config.alloy /etc/alloy/config.alloy

    # Restart Alloy service
    echo "Restarting Grafana Alloy service..."
    sudo systemctl restart alloy
}

display_logo() {
    clear

    # display the Quilbackup by Cherry Servers message with ASCII art
    echo "Quilibrium Dashboard installation"
    echo "                   ███████████████
                █████████████████████████
            ███████████████████████████████           
            █████████████████████████████████████        
        ███████████████████████████████████████       
        ██████████████████████████████████████████      
        ██████████████████████████████████████████       
    ████████████████████         ████████████     █   
    ██████████████████              ████████     ████  
    █████████████████                  ███      ███████ 
    █████████████████                         ███████████
    ███████████████                        ██████████████
    ███████████████                        ██████████████
    ██████████████                          █████████████
    ██████████████                          █████████████
    ██████████████                           ████████████
    ██████████████                          █████████████
    ███████████████                         █████████████
    ████████████████                      ███████████████
    █████████████████                  ████████████████ 
    ██████████████████             ██████████████████  
    ███████████████████████████████████████████████   
        █████████████████████████████████████████████    
        ███████████████████████████████████████████     
        ███████████████████████████████████████       
            ████████████████████████████████████        
            ███████████████████████████████           
                █████████████████████████
                    █████████████████                   "

}

# Main script
main() {
    # Display Q logo
    display_logo

    # Validate OS
    validate_os

    # Ask for input
    node_path=$(ask "What is the path to node quilibrium" "ex: /home/user/quilibrium/ceremonyclient/node")
    validate_node_path

    service_name=$(ask "What is the name of the service" "quilibrium")
    validate_service_name

    loki_url=$(ask "Please enter the Loki URL" "ex: http://X.X.X.X:3100/loki/api/v1/push")
    loki_user=$(ask "Please enter the Loki user (optional)" "")
    loki_api_key=$(ask "Please enter the Loki password (optional)" "")

    prometheus_url=$(ask "Please enter the Prometheus URL" "ex: http://X.X.X.X:9090/api/v1/write")
    prometheus_user=$(ask "Please enter the Prometheus user (optional)" "")
    prometheus_api_key=$(ask "Please enter the Prometheus password (optional)" "")

    validate_urls

    # Print out the collected information
    echo "Node Quilibrium path: $node_path"
    echo "Service name: $service_name"
    echo "Loki URL: $loki_url"
    echo "Loki user: $loki_user"
    echo "Loki password: $loki_api_key"
    echo "Prometheus URL: $prometheus_url"
    echo "Prometheus user: $prometheus_user"
    echo "Prometheus password: $prometheus_api_key"

    # Install Quilibrium exporter
    install_quilibrium_exporter

    # Install Grafana Alloy
    install_grafana_alloy

    # Configure Grafana Alloy
    configure_grafana_alloy

    echo "Installation and setup completed successfully."
}

# Run the main function
main
