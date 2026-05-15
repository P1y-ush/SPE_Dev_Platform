from flask import Flask, request, jsonify
import uuid
import subprocess
import threading
import time
from datetime import datetime, timezone
from flask_cors import CORS
import json
import os
from pymongo import MongoClient
import logging
from elasticsearch import Elasticsearch
import bcrypt
import requests
from kubernetes import client, config, utils
import yaml
import concurrent.futures

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Global HPA Cache for instant dashboard loads
HPA_CACHE = {} 

# Ensure kubectl can find the config even when run via sudo/Jenkins
os.environ["HOME"] = os.path.expanduser("~") # Fixed hardcoded path
if "/snap/bin" not in os.environ.get("PATH", ""):
    os.environ["PATH"] += ":/snap/bin"

try:
    config.load_kube_config()
    print("Kubernetes config loaded ✅")
except Exception as e:
    print(f"Error loading kube config: {e}")

# Discover Minikube IP in background to avoid blocking main thread
MINIKUBE_IP = "127.0.0.1"
def discover_minikube_ip():
    global MINIKUBE_IP
    while True:
        try:
            ip = subprocess.check_output(["minikube", "ip"], text=True).strip()
            if ip and ip != MINIKUBE_IP:
                MINIKUBE_IP = ip
                print(f"Minikube IP discovered: {MINIKUBE_IP} ✅")
                break
        except:
            time.sleep(5)

if not os.environ.get("TESTING"):
    threading.Thread(target=discover_minikube_ip, daemon=True).start()

# ---------------- CONFIG ----------------
STACK_CONFIG = {
    "flask": {"image": "p1yush123/flask-env:latest", "port": 5001},
    "mern": {"image": "p1yush123/mern-env:latest", "port": 3000},
    "java": {"image": "p1yush123/java-env:latest", "port": 8082},
    "ml": {"image": "p1yush123/ml-env:latest", "port": 8888}
}

# ---------------- BACKGROUND SYNC ----------------
def sync_hpa_background():
    global HPA_CACHE
    autoscaling_v1 = client.AutoscalingV1Api()
    while True:
        try:
            hpas = autoscaling_v1.list_namespaced_horizontal_pod_autoscaler(namespace=NAMESPACE)
            new_cache = {}
            for hpa in hpas.items:
                hpa_name = hpa.metadata.name.rsplit("-", 1)[0]
                current = hpa.status.current_replicas or 0
                desired = hpa.spec.max_replicas or 3
                new_cache[hpa_name] = f"{current}/{desired}"
            HPA_CACHE = new_cache
        except Exception as e:
            logging.error(f"HPA sync error: {e}")
        time.sleep(10)

threading.Thread(target=sync_hpa_background, daemon=True).start()

logging.basicConfig(
    filename="/tmp/app.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

# ---------------- ELASTICSEARCH ----------------
# Non-blocking: connect in background so Flask starts instantly
es = None
ELASTICSEARCH_URI = os.getenv("ELASTICSEARCH_URI", "http://127.0.0.1:9200")

def _connect_es():
    global es
    for i in range(5):
        try:
            client = Elasticsearch(ELASTICSEARCH_URI)
            client.info()
            es = client
            print("Elasticsearch connected ✅")
            return
        except:
            print("Retrying Elasticsearch...", i + 1)
            time.sleep(5)
    print("Elasticsearch not available ⚠️")

threading.Thread(target=_connect_es, daemon=True).start()

LOGSTASH_URL = os.getenv("LOGSTASH_URL", "http://127.0.0.1:5044")

def log_to_es_async(index_name, doc):
    """Event Logger: Sends structured logs to Logstash via HTTP"""
    def task():
        try:
            # Include metadata for Logstash processing
            doc["log_index"] = index_name
            doc["timestamp"] = time.time()
            requests.post(LOGSTASH_URL, json=doc, timeout=2)
        except Exception as e:
            logging.error(f"Logstash logging failed: {e}")
    threading.Thread(target=task, daemon=True).start()


NAMESPACE = "dev-platform"

# ---------------- MONGODB ----------------
import os

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)

db = client["dev_platform"]
users_col = db["users"]
envs_col = db["environments"]

# ---------------- HELPERS ----------------
def load_yaml_template(path, replacements):
    with open(path, "r") as f:
        content = f.read()

    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", str(value))

    return content


def delete_k8s_resources(name):
    apps_v1 = client.AppsV1Api()
    core_v1 = client.CoreV1Api()
    autoscaling_v1 = client.AutoscalingV1Api()
    
    try:
        apps_v1.delete_namespaced_deployment(name=name, namespace=NAMESPACE)
    except client.exceptions.ApiException: pass
    
    try:
        core_v1.delete_namespaced_service(name=f"{name}-svc", namespace=NAMESPACE)
    except client.exceptions.ApiException: pass
    
    try:
        core_v1.delete_namespaced_persistent_volume_claim(name=f"{name}-pvc", namespace=NAMESPACE)
    except client.exceptions.ApiException: pass
    
    try:
        autoscaling_v1.delete_namespaced_horizontal_pod_autoscaler(name=f"{name}-hpa", namespace=NAMESPACE)
    except client.exceptions.ApiException: pass


# ---------------- TTL CLEANUP ----------------
TTL = 1800


def cleanup_expired_envs():
    """Background process to automatically dispose of expired environments"""
    while True:
        # Reduced sleep from 60s to 10s for more responsive disposal
        time.sleep(10)
        
        if "/snap/bin" not in os.environ.get("PATH", ""):
            os.environ["PATH"] += ":/snap/bin"
        os.environ["HOME"] = "/home/piyush"

        try:
            now = time.time()
            cutoff_time = now - TTL

            expired_envs = list(envs_col.find({"created_at": {"$lte": cutoff_time}}))

            for env in expired_envs:
                env_name = env["env_name"]
                print(f"🧹 TTL: Cleaning up expired environment: {env_name}")
                
                delete_k8s_resources(env_name)
                envs_col.delete_one({"env_name": env_name})

                logging.info(f"TTL DELETE SUCCESS: {env_name}")
                log_to_es_async(index_name="app-logs", doc={
                    "event": "ttl_delete",
                    "env": env_name
                })
                print(f"✅ TTL: Successfully purged {env_name}")

        except Exception as e:
            print(f"❌ TTL Error: {e}")
            logging.error(f"TTL Error: {e}")


# ---------------- ROUTES ----------------
@app.route('/')
def home():
    return "Dev Platform Backend Running 🚀"


@app.route('/envs', methods=['GET'])
def list_envs():
    result = {}
    
    # Read from instant background cache
    for env in envs_col.find():
        user = env["user"]
        env_name = env["env_name"]

        if user not in result:
            result[user] = []

        result[user].append({
            "name": env_name,
            "stack": env.get("stack", "unknown"),
            "port": env["port"],
            "pods": HPA_CACHE.get(env_name, "1/3"),
            "created_at": env.get("created_at", time.time())
        })

    return jsonify(result)


@app.route('/delete-env', methods=['POST'])
def delete_env():
    data = request.get_json()
    env_name = data["env_name"]

    delete_k8s_resources(env_name)
    envs_col.delete_one({"env_name": env_name})

    logging.info(f"ENV DELETED: {env_name}")

    log_to_es_async(index_name="app-logs", doc={
        "event": "delete_env",
        "env": env_name
    })

    return jsonify({"status": "deleted"})


@app.route('/stress-env', methods=['POST'])
def stress_env():
    """Trigger CPU load to demonstrate HPA scaling via external HTTP requests"""
    try:
        data = request.get_json()
        env_name = data["env_name"]
        
        env_record = envs_col.find_one({"env_name": env_name})
        if not env_record:
            return jsonify({"error": "Environment not found"}), 404
            
        env_node_port = env_record["port"]
        target_url = f"http://{MINIKUBE_IP}:{env_node_port}/"

        def generate_http_load():
            end_time = time.time() + 120  # Run for 120 seconds
            
            def make_request():
                try:
                    requests.get(target_url, timeout=2)
                except: pass
                
            with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
                while time.time() < end_time:
                    # Submit a batch of 50 concurrent requests
                    futures = [executor.submit(make_request) for _ in range(50)]
                    concurrent.futures.wait(futures)
                    
        threading.Thread(target=generate_http_load, daemon=True).start()
        
        logging.info(f"STRESS TEST TRIGGERED (HTTP Load): {env_name} on {target_url}")
        log_to_es_async(index_name="app-logs", doc={
            "event": "stress_test_http",
            "env": env_name
        })
        
        return jsonify({"status": "stressing", "message": f"HTTP load triggered for 120s against {target_url}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/open-env', methods=['POST'])
def open_env():
    try:
        data = request.json
        env_name = data.get("env_name")
        
        # Get NodePort from DB for immediate redirection
        env_record = envs_col.find_one({"env_name": env_name})
        if not env_record:
            return jsonify({"error": "Environment not found"}), 404
            
        env_node_port = env_record["port"]

        # INSTANT REDIRECTION - Reliability polling shifted to Frontend
        url = f"http://{MINIKUBE_IP}:{env_node_port}"
        return jsonify({"url": url})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------- AUTH --------
@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"status": False, "error": "Username and password required"}), 400

    if users_col.find_one({"username": username}):
        return jsonify({"status": False, "error": "User already exists"}), 200

    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

    users_col.insert_one({
        "username": username,
        "password": hashed_pw
    })

    logging.info(f"SIGNUP SUCCESS: {username}")

    log_to_es_async(index_name="app-logs", doc={
        "event": "signup",
        "user": username
    })

    return jsonify({"status": True, "message": "Signup successful"})


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    user = users_col.find_one({"username": username})

    if not user:
        return jsonify({"status": False, "error": "Invalid username or password"}), 404

    if not bcrypt.checkpw(password.encode(), user["password"]):
        return jsonify({"status": False, "error": "Invalid username or password"}), 401

    logging.info(f"LOGIN SUCCESS: {username}")

    log_to_es_async(index_name="app-logs", doc={
        "event": "login",
        "user": username
    })

    return jsonify({"status": True, "message": "Login successful"})


# -------- CREATE ENV --------
@app.route('/create-env', methods=['POST'])
def create_env():
    try:
        data = request.json
        user = data.get("user", "default").lower()
        stack = data["stack"]

        current_envs = list(envs_col.find({"user": user}))
        if len(current_envs) >= 3:
            return jsonify({"error": "Max 3 environments"}), 400

        if stack not in STACK_CONFIG:
            return jsonify({"error": f"Unknown stack: {stack}"}), 400 #This comment

        config = STACK_CONFIG[stack]
        image = data.get("image", config["image"])
        port = config["port"]

        cpu = data.get("cpu", "250m")
        memory = data.get("memory", "256Mi")

        cpu_val = min(int(cpu.replace("m", "")), 500)
        mem_val = min(int(memory.replace("Mi", "")), 512)

        cpu = f"{cpu_val}m"
        memory = f"{mem_val}Mi"

        env_id = str(uuid.uuid4())[:6]
        env_name = f"{user}-{stack}-{env_id}"

        base_path = os.path.dirname(os.path.abspath(__file__))
        k8s_path = os.path.join(base_path, "..", "k8s")

        service_name = f"{env_name}-svc"
        node_port = 30000 + int(env_id[:3], 16) % 2000

        # Insert record immediately so dashboard shows it right away
        envs_col.insert_one({
            "user": user,
            "stack": stack,
            "env_name": env_name,
            "port": node_port,
            "status": "provisioning",
            "created_at": time.time()
        })

        # Run kubectl in background so HTTP response is INSTANT
        def provision_k8s():
            try:
                pvc_yaml = load_yaml_template(
                    os.path.join(k8s_path, "pvc.yaml"),
                    {"ENV_NAME": env_name}
                )
                deployment_yaml = load_yaml_template(
                    os.path.join(k8s_path, "deployment.yaml"),
                    {
                        "ENV_NAME": env_name,
                        "IMAGE": image,
                        "PORT": port,
                        "CPU": cpu,
                        "MEMORY": memory
                    }
                )
                service_yaml = load_yaml_template(
                    os.path.join(k8s_path, "service.yaml"),
                    {
                        "ENV_NAME": env_name,
                        "SERVICE_NAME": service_name,
                        "PORT": port,
                        "NODE_PORT": node_port
                    }
                )
                hpa_yaml = load_yaml_template(
                    os.path.join(k8s_path, "hpa.yaml"),
                    {"ENV_NAME": env_name}
                )

                api_client = client.ApiClient()
                
                # Apply PVC
                for obj in yaml.safe_load_all(pvc_yaml):
                    if obj: utils.create_from_dict(api_client, obj)
                
                # Apply Deployment
                for obj in yaml.safe_load_all(deployment_yaml):
                    if obj: utils.create_from_dict(api_client, obj)
                    
                # Apply Service
                for obj in yaml.safe_load_all(service_yaml):
                    if obj: utils.create_from_dict(api_client, obj)
                    
                # Apply HPA
                for obj in yaml.safe_load_all(hpa_yaml):
                    if obj: utils.create_from_dict(api_client, obj)

                threading.Thread(target=verify_deployment, args=(env_name,), daemon=True).start()

            except Exception as e:
                error_msg = str(e)
                envs_col.update_one(
                    {"env_name": env_name},
                    {"$set": {"status": "error", "error": error_msg}}
                )
                logging.error(f"PROVISION FAILED: {env_name} - {error_msg}")

        def verify_deployment(name):
            """Wait for deployment to be ready or fail after 5 mins"""
            apps_v1 = client.AppsV1Api()
            core_v1 = client.CoreV1Api()
            
            start_time = time.time()
            while time.time() - start_time < 300:
                try:
                    dep = apps_v1.read_namespaced_deployment(name=name, namespace=NAMESPACE)
                    if (dep.status.ready_replicas or 0) >= 1:
                        envs_col.update_one({"env_name": name}, {"$set": {"status": "running"}})
                        return
                    
                    # Check for image pull errors
                    pods = core_v1.list_namespaced_pod(namespace=NAMESPACE, label_selector=f"app={name}")
                    for pod in pods.items:
                        if pod.status and pod.status.container_statuses:
                            for cs in pod.status.container_statuses:
                                if cs.state and cs.state.waiting:
                                    reason = cs.state.waiting.reason
                                    if reason in ["ImagePullBackOff", "ErrImagePull"]:
                                        envs_col.update_one({"env_name": name}, {"$set": {"status": "error", "error": f"Image Error: {cs.state.waiting.message}"}})
                                        return
                except:
                    pass
                time.sleep(5)
            
            # Timeout
            envs_col.update_one({"env_name": name}, {"$set": {"status": "error", "error": "Provisioning timed out (5m)"}})

        threading.Thread(target=provision_k8s, daemon=True).start()

        return jsonify({
            "env_name": env_name,
            "access_port": node_port,
            "status": "provisioning"
        }), 202

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- START ----------------
if __name__ == '__main__':
    threading.Thread(target=cleanup_expired_envs, daemon=True).start()
    app.run(debug=True, host='0.0.0.0', port=5002)
#comment