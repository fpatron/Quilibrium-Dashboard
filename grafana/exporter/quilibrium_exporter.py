from decimal import Decimal
from flask import Flask, Response
from prometheus_client import start_http_server, Gauge, CollectorRegistry, generate_latest
import subprocess
import socket
import re
import os
import requests
import logging
import base64
import struct
import shutil

from dotenv import load_dotenv # type: ignore
load_dotenv()

app = Flask(__name__)

# Configure the logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

# Api
api_port = os.getenv("api_port") or '8338'
api_url = f"http://127.0.0.1:{api_port}/quilibrium.node.node.pb.NodeService"

def decode_value(value):
    try:
        value_bytes = base64.b64decode(value)
        return struct.unpack('>Q', value_bytes[-8:])[0]
    except requests.RequestException as e:
        return None

# Function to fetch data from command
def fetch_data_from_api():
    try:
        hostname= socket.gethostname()
        
        peer_id = None
        peer_score = 0
        max_frame = 0
        unclaimed_balance = 0
        seniority = 0
        ring = -1
        active_workers = 0
                
        node_info_response = requests.post(f"{api_url}/GetNodeInfo")
        if node_info_response.status_code == 200:
            node_info = node_info_response.json()
            peer_id = node_info.get("peerId")
            peer_score = float(node_info.get("peerScore")) if node_info.get("peerScore") else 0
            max_frame =  int(node_info.get("maxFrame")) if node_info.get("maxFrame") else 0
            seniority =  int(decode_value(node_info.get("peerSeniority"))) if node_info.get("peerSeniority") else 0
            ring =  int(node_info.get("proverRing"))
            active_workers =  int(node_info.get("workers")) if node_info.get("workers") else 0
        else:
            print(f"Unable to fetch API {api_url}/GetNodeInfo")
            
        token_info_response = requests.post(f"{api_url}/GetTokenInfo")
        if token_info_response.status_code == 200:
            token_info = token_info_response.json()
            balance = 0
            owned_tokens = decode_value(token_info.get("ownedTokens")) if token_info.get("ownedTokens") else 0
            if owned_tokens is not None and owned_tokens > 0:
                conversion_factor_hex = "1DCD65000"
                conversion_factor = Decimal(int(conversion_factor_hex, 16))
                balance = owned_tokens / conversion_factor
            unclaimed_balance = balance
        else:
            print(f"Unable to fetch API {api_url}/GetTokenInfo")
            
        if peer_id is not None and hostname is not None:
            peer_score_metric.labels(peer_id=peer_id, hostname=hostname).set(peer_score)
            max_frame_metric.labels(peer_id=peer_id, hostname=hostname).set(max_frame)
            unclaimed_balance_metric.labels(peer_id=peer_id, hostname=hostname).set(unclaimed_balance)
            seniority_metric.labels(peer_id=peer_id, hostname=hostname).set(seniority)
            ring_metric.labels(peer_id=peer_id, hostname=hostname).set(ring)
            active_workers_metric.labels(peer_id=peer_id, hostname=hostname).set(active_workers)

        return peer_id, hostname

    except Exception as e:
        logger.error(f"Error fetching data from command: {e}")
        return None, None

# Function to fetch data from logs
def fetch_data_from_logs(peer_id, hostname):
    try:
        peer_store_count = 0
        network_peer_count = 0
        creating_data_proof = 0
        submitted_data_proof = 0

        if shutil.which("journalctl"):
            result = subprocess.run(['journalctl', '-u', service_name, '--since', '1 hour ago', '--no-pager'], capture_output=True, text=True)
            if result.returncode == 0:
                output = result.stdout.splitlines()
                if len(output) > 0:
                    for line in reversed(output):
                        if peer_store_count == 0 and 'peers in store' in line:
                            peer_store_count_match = re.search(r'"peer_store_count":(\d+)', line)
                            if peer_store_count_match:
                                peer_store_count = int(peer_store_count_match.group(1))
                        if network_peer_count == 0 and 'peers in store' in line:
                            network_peer_count_match = re.search(r'"network_peer_count":(\d+)', line)
                            if network_peer_count_match:
                                network_peer_count = int(network_peer_count_match.group(1))
                    
                        if creating_data_proof == 0 and 'creating data shard ring proof' in line:
                            creating_data_proof_match = re.search(r'"frame_age":(\d+)', line)
                            if creating_data_proof_match:
                                creating_data_proof = int(creating_data_proof_match.group(1))
                        if submitted_data_proof == 0 and 'submitting data proof' in line:
                            submitted_data_proof_match = re.search(r'"frame_age":(\d+)', line)
                            if submitted_data_proof_match:
                                submitted_data_proof = int(submitted_data_proof_match.group(1))
                        
                        if (network_peer_count > 0 and peer_store_count > 0 and creating_data_proof > 0 and submitted_data_proof > 0):
                            break

        peer_store_count_metric.labels(peer_id=peer_id, hostname=hostname).set(peer_store_count)
        network_peer_count_metric.labels(peer_id=peer_id, hostname=hostname).set(network_peer_count)
        creating_data_proof_metric.labels(peer_id=peer_id, hostname=hostname).set(creating_data_proof)
        submitted_data_proof_metric.labels(peer_id=peer_id, hostname=hostname).set(submitted_data_proof)

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
    
    peer_id, hostname = fetch_data_from_api()
    if peer_id and hostname:
        fetch_data_from_logs(peer_id, hostname)
    return Response(generate_latest(registry), mimetype='text/plain')

if __name__ == '__main__':
    start_http_server(8000)
    app.run(host='127.0.0.1', port=5001)
