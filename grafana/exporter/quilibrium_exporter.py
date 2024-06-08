from flask import Flask, Response
from prometheus_client import start_http_server, Gauge, CollectorRegistry, generate_latest
import subprocess
import socket
import re
import os

app = Flask(__name__)

# Define the working directory
current_dir = os.path.dirname(os.path.abspath(__file__))
working_directory = f'{current_dir}/../ceremonyclient/node'

# Define the registry
registry = CollectorRegistry()

# Define custom metrics
peer_score_metric = Gauge('quilibrium_peer_score', 'Peer score of the node', ['peer_id', 'hostname'], registry=registry)
max_frame_metric = Gauge('quilibrium_max_frame', 'Max frame of the node', ['peer_id', 'hostname'], registry=registry)
unclaimed_balance_metric = Gauge('quilibrium_unclaimed_balance', 'Unclaimed balance of the node', ['peer_id', 'hostname'], registry=registry)
peer_store_count_metric = Gauge('quilibrium_peer_store_count', 'Peers in store', ['peer_id', 'hostname'], registry=registry)
network_peer_count_metric = Gauge('quilibrium_network_peer_count', 'Network peer count', ['peer_id', 'hostname'], registry=registry)
proof_increment_metric = Gauge('quilibrium_proof_increment', 'Proof increment', ['peer_id', 'hostname'], registry=registry)
proof_time_taken_metric = Gauge('quilibrium_proof_time_taken', 'Proof time taken', ['peer_id', 'hostname'], registry=registry)

# Function to fetch data from command
def fetch_data_from_node():
    try:
        result = subprocess.run(['./node', '-node-info'], cwd=working_directory, capture_output=True, text=True)
        output = result.stdout
        
        peer_id_match = re.search(r'Peer ID: (\S+)', output)
        peer_id = peer_id_match.group(1) if peer_id_match else 'unknown'
        
        peer_score_match = re.search(r'Peer Score: (\d+)', output)
        peer_score = float(peer_score_match.group(1)) if peer_score_match else 0
        
        max_frame_match = re.search(r'Max Frame: (\d+)', output)
        max_frame = float(max_frame_match.group(1)) if max_frame_match else 0
        
        unclaimed_balance_match = re.search(r'Unclaimed balance: ([\d\.]+)', output)
        unclaimed_balance = float(unclaimed_balance_match.group(1)) if unclaimed_balance_match else 0
        
        hostname = socket.gethostname()
        
        peer_score_metric.labels(peer_id=peer_id, hostname=hostname).set(peer_score)
        max_frame_metric.labels(peer_id=peer_id, hostname=hostname).set(max_frame)
        unclaimed_balance_metric.labels(peer_id=peer_id, hostname=hostname).set(unclaimed_balance)

        return peer_id, hostname

    except Exception as e:
        print(f"Error fetching data from command: {e}")
        return None, None

# Function to fetch data from logs
def fetch_data_from_logs(peer_id, hostname):
    try:
        result = subprocess.run(['journalctl', '-u', 'quilibrium', '--since', '1 hour ago', '--no-pager'], capture_output=True, text=True)
        output = result.stdout.splitlines()

        peer_store_count = None
        network_peer_count = None
        proof_increment = None
        proof_time_taken = None

        for line in reversed(output):
            if peer_store_count is None and 'peers in store' in line:
                peer_store_count_match = re.search(r'"peer_store_count":(\d+)', line)
                network_peer_count_match = re.search(r'"network_peer_count":(\d+)', line)
                if peer_store_count_match and network_peer_count_match:
                    peer_store_count = int(peer_store_count_match.group(1))
                    network_peer_count = int(network_peer_count_match.group(1))
                    peer_store_count_metric.labels(peer_id=peer_id, hostname=hostname).set(peer_store_count)
                    network_peer_count_metric.labels(peer_id=peer_id, hostname=hostname).set(network_peer_count)
            if proof_increment is None and 'completed duration proof' in line:
                proof_increment_match = re.search(r'"increment":(\d+)', line)
                proof_time_taken_match = re.search(r'"time_taken":([\d\.]+)', line)
                if proof_increment_match and proof_time_taken_match:
                    proof_increment = int(proof_increment_match.group(1))
                    proof_time_taken = float(proof_time_taken_match.group(1))
                    proof_increment_metric.labels(peer_id=peer_id, hostname=hostname).set(proof_increment)
                    proof_time_taken_metric.labels(peer_id=peer_id, hostname=hostname).set(proof_time_taken)
            
            if (peer_store_count is not None and network_peer_count is not None and 
                proof_increment is not None and proof_time_taken is not None):
                break

    except Exception as e:
        print(f"Error fetching data from logs: {e}")

@app.route('/metrics')
def metrics():
    peer_id, hostname = fetch_data_from_node()
    if peer_id and hostname:
        fetch_data_from_logs(peer_id, hostname)
    return Response(generate_latest(registry), mimetype='text/plain')

if __name__ == '__main__':
    start_http_server(8000)
    app.run(host='127.0.0.1', port=5001)
