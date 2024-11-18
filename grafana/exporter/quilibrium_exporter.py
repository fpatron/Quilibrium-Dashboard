from flask import Flask, Response
from prometheus_client import start_http_server, Gauge, CollectorRegistry, generate_latest
import subprocess
import socket
import re
import os
import platform
import logging

from dotenv import load_dotenv # type: ignore
load_dotenv()

app = Flask(__name__)

# Configure the logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define the working directory
current_dir = os.path.dirname(os.path.abspath(__file__))
working_directory = os.getenv("node_path") or f'{current_dir}/../ceremonyclient/node'

# Systemd name
service_name= os.getenv("service_name") or 'quilibrium'

# Define the registry
registry = CollectorRegistry()

# Define custom metrics
peer_score_metric = Gauge('quilibrium_peer_score', 'Peer score of the node', ['peer_id', 'hostname'], registry=registry)
max_frame_metric = Gauge('quilibrium_max_frame', 'Max frame of the node', ['peer_id', 'hostname'], registry=registry)
unclaimed_balance_metric = Gauge('quilibrium_unclaimed_balance', 'Unclaimed balance of the node', ['peer_id', 'hostname'], registry=registry)
peer_store_count_metric = Gauge('quilibrium_peer_store_count', 'Peers in store', ['peer_id', 'hostname'], registry=registry)
network_peer_count_metric = Gauge('quilibrium_network_peer_count', 'Network peer count', ['peer_id', 'hostname'], registry=registry)
ring_metric = Gauge('quilibrium_ring', 'Ring', ['peer_id', 'hostname'], registry=registry)
seniority_metric = Gauge('quilibrium_seniority', 'Seniority', ['peer_id', 'hostname'], registry=registry)
creating_data_proof_metric = Gauge('quilibrium_creating_data_proof', 'Creating data proof', ['peer_id', 'hostname'], registry=registry)
submitted_data_proof_metric = Gauge('quilibrium_submitted_data_proof', 'Submitted data proof', ['peer_id', 'hostname'], registry=registry)
active_workers_metric = Gauge('quilibrium_active_workers', 'Active workers', ['peer_id', 'hostname'], registry=registry)
proof_increment_metric = Gauge('quilibrium_proof_increment', 'Proof increment', ['peer_id', 'hostname'], registry=registry)

# Function to find main node binary
def find_node_binary():
    os_type = platform.system().lower()
    arch = platform.machine()
    if os_type == "linux":
        if arch == "aarch64":
            command = "find . -type f -name '*linux*arm64' | head -n 1"
        else:
            command = "find . -type f -name '*linux*amd64' | head -n 1"
    elif os_type == "darwin":
        command = "find . -type f -name '*darwin*arm64' | head -n 1"
    else:
        return None

    result = result = subprocess.run(command, shell=True, cwd=working_directory, capture_output=True, text=True)
    file = result.stdout.strip()
    
    if result.returncode != 0 or not file:
        return None

    return file

# Function to fetch data from command
def fetch_data_from_node():
    try:
        node_binary= find_node_binary()
        if (node_binary is not None):
            result = subprocess.run([node_binary, '-node-info'], cwd=working_directory, capture_output=True, text=True)
            output = result.stdout
            
            peer_id_match = re.search(r'Peer ID: (\S+)', output)
            peer_id = peer_id_match.group(1) if peer_id_match else 'unknown'
            
            peer_score_match = re.search(r'Peer Score: (\d+)', output)
            peer_score = float(peer_score_match.group(1)) if peer_score_match else 0
            
            unclaimed_balance_match = re.search(r'Owned balance: ([\d\.]+) (\S+)', output)
            unclaimed_balance = float(unclaimed_balance_match.group(1)) if unclaimed_balance_match else 0
            
            seniority_match = re.search(r'Seniority: (\d+)', output)
            seniority = int(seniority_match.group(1)) if seniority_match else 0
            
            hostname = socket.gethostname()
            
            peer_score_metric.labels(peer_id=peer_id, hostname=hostname).set(peer_score)
            unclaimed_balance_metric.labels(peer_id=peer_id, hostname=hostname).set(unclaimed_balance)
            seniority_metric.labels(peer_id=peer_id, hostname=hostname).set(seniority)

        return peer_id, hostname

    except Exception as e:
        logger.error(f"Error fetching data from command: {e}")
        return None, None

# Function to fetch data from logs
def fetch_data_from_logs(peer_id, hostname):
    try:
        result = subprocess.run(['journalctl', '-u', service_name, '--since', '1 hour ago', '--no-pager'], capture_output=True, text=True)
        output = result.stdout.splitlines()

        max_frame = 0
        peer_store_count = None
        network_peer_count = None
        ring = 9999
        creating_data_proof = None
        submitted_data_proof = None
        active_workers = None
        proof_increment = None

        for line in reversed(output):
            if max_frame == 0 and 'frame_number' in line:
                max_frame_match = re.search(r'"frame_number":(\d+)', line)
                if max_frame_match:
                    max_frame = int(max_frame_match.group(1))
                    max_frame_metric.labels(peer_id=peer_id, hostname=hostname).set(max_frame)
            if peer_store_count is None and 'peers in store' in line:
                peer_store_count_match = re.search(r'"peer_store_count":(\d+)', line)
                network_peer_count_match = re.search(r'"network_peer_count":(\d+)', line)
                if peer_store_count_match and network_peer_count_match:
                    peer_store_count = int(peer_store_count_match.group(1))
                    network_peer_count = int(network_peer_count_match.group(1))
                    peer_store_count_metric.labels(peer_id=peer_id, hostname=hostname).set(peer_store_count)
                    network_peer_count_metric.labels(peer_id=peer_id, hostname=hostname).set(network_peer_count)
            if ring == 9999 and 'creating data shard ring proof' in line:
                ring_match = re.search(r'"ring":(\d+)', line)
                if ring_match:
                    ring = int(ring_match.group(1))
                    ring_metric.labels(peer_id=peer_id, hostname=hostname).set(ring)
            if creating_data_proof is None and 'creating data shard ring proof' in line:
                creating_data_proof_match = re.search(r'"frame_age":(\d+)', line)
                if creating_data_proof_match:
                    creating_data_proof = int(creating_data_proof_match.group(1))
                    creating_data_proof_metric.labels(peer_id=peer_id, hostname=hostname).set(creating_data_proof)
            if submitted_data_proof is None and 'submitting data proof' in line:
                submitted_data_proof_match = re.search(r'"frame_age":(\d+)', line)
                if submitted_data_proof_match:
                    submitted_data_proof = int(submitted_data_proof_match.group(1))
                    submitted_data_proof_metric.labels(peer_id=peer_id, hostname=hostname).set(submitted_data_proof)
            if active_workers is None and 'active_workers' in line:
                active_workers_match = re.search(r'"active_workers":(\d+)', line)
                if active_workers_match:
                    active_workers = int(active_workers_match.group(1))
                    active_workers_metric.labels(peer_id=peer_id, hostname=hostname).set(active_workers)
            if proof_increment is None and 'publishing proof batch' in line:
                proof_increment_match = re.search(r'"increment":(\d+)', line)
                if proof_increment_match:
                    proof_increment = int(proof_increment_match.group(1))
                    proof_increment_metric.labels(peer_id=peer_id, hostname=hostname).set(proof_increment)
            
            if (max_frame is not None and peer_store_count is not None and 
                network_peer_count is not None and proof_increment is not None):
                break

    except Exception as e:
        logger.error(f"Error fetching data from logs: {e}")

@app.route('/metrics')
def metrics():
    peer_score_metric.clear()
    max_frame_metric.clear()
    unclaimed_balance_metric.clear()
    peer_store_count_metric.clear()
    network_peer_count_metric.clear()
    ring_metric.clear()
    seniority_metric.clear()
    creating_data_proof_metric.clear()
    submitted_data_proof_metric.clear()
    active_workers_metric.clear()
    proof_increment_metric.clear()
    
    peer_id, hostname = fetch_data_from_node()
    if peer_id and hostname:
        fetch_data_from_logs(peer_id, hostname)
    return Response(generate_latest(registry), mimetype='text/plain')

if __name__ == '__main__':
    start_http_server(8000)
    app.run(host='127.0.0.1', port=5001)
