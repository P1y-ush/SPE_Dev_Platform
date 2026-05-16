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

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Global HPA Cache for instant dashboard loads
HPA_CACHE = {} 

# Ensure kubectl can find the config even when run via sudo/Jenkins
os.environ["HOME"] = "/home/piyush"
if "/snap/bin" not in os.environ.get("PATH", ""):
    os.environ["PATH"] += ":/snap/bin"

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
    while True:
        try:
            hpa_out = subprocess.check_output(
                ["kubectl", "get", "hpa", "-n", NAMESPACE, "--no-headers"],
                text=True, stderr=subprocess.DEVNULL
            ).strip().split("\n")
            
            new_cache = {}
            for line in hpa_out:
                parts = line.split()
                if len(parts) >= 7:
                    hpa_name = parts[0].rsplit("-", 1)[0]
                    new_cache[hpa_name] = f"{parts[6]}/{parts[5]}"
            HPA_CACHE = new_cache
        except:
            pass
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
    subprocess.run(
        ["kubectl", "delete", "deployment", name, "-n", NAMESPACE, "--ignore-not-found"],
        check=False
    )
    subprocess.run(
        ["kubectl", "delete", "svc", f"{name}-svc", "-n", NAMESPACE, "--ignore-not-found"],
        check=False
    )
    subprocess.run(
        ["kubectl", "delete", "pvc", f"{name}-pvc", "-n", NAMESPACE, "--ignore-not-found"],
        check=False
    )
    subprocess.run(
        ["kubectl", "delete", "hpa", f"{name}-hpa", "-n", NAMESPACE, "--ignore-not-found"],
        check=False
    )


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
                print(f" TTL: Successfully purged {env_name}")

        except Exception as e:
            print(f" TTL Error: {e}")
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
    """Innovation: Trigger CPU load to demonstrate HPA scaling"""
    try:
        data = request.get_json()
        env_name = data["env_name"]
        
        # Get actual pod name (kubectl exec requires a pod, not a deployment)
        pod_cmd = ["kubectl", "get", "pod", "-l", f"app={env_name}", "-o", "name", "-n", NAMESPACE]
        pod_output = subprocess.check_output(pod_cmd, text=True).strip()
        
        if not pod_output:
            return jsonify({"error": "No running pod found for this environment"}), 404

        # Pick the first pod if multiple are returned (e.g. during scaling or restarts)
        pod_name = pod_output.split('\n')[0]

        # Run in a background thread so the HTTP response is instant, 
        # but the load is sustained for 60s
        def run_load():
            try:
                # Increased to 120s to ensure HPA has reliable metrics window
                stress_cmd = ["kubectl", "exec", "-n", NAMESPACE, pod_name, "--", "sh", "-c", "timeout 120s cat /dev/urandom | gzip -9 > /dev/null"]
                subprocess.run(stress_cmd, check=True)
            except Exception as e:
                logging.error(f"Stress execution failed: {e}")

        threading.Thread(target=run_load, daemon=True).start()
        
        logging.info(f"STRESS TEST TRIGGERED: {env_name} on {pod_name}")
        log_to_es_async(index_name="app-logs", doc={
            "event": "stress_test",
            "env": env_name,
            "pod": pod_name
        })
        
        return jsonify({"status": "stressing", "message": f"CPU load triggered for 60s on {pod_name}"})
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

                pvc_file = f"/tmp/pvc-{env_id}.yaml"
                dep_file = f"/tmp/deploy-{env_id}.yaml"
                svc_file = f"/tmp/service-{env_id}.yaml"
                hpa_file = f"/tmp/hpa-{env_id}.yaml"

                open(pvc_file, "w").write(pvc_yaml)
                open(dep_file, "w").write(deployment_yaml)
                open(svc_file, "w").write(service_yaml)
                open(hpa_file, "w").write(hpa_yaml)

                def run_kubectl(args):
                    res = subprocess.run(args, capture_output=True, text=True, timeout=30)
                    if res.returncode != 0:
                        raise Exception(f"kubectl error: {res.stderr or res.stdout}")
                    return res.stdout

                run_kubectl(["kubectl", "apply", "-f", pvc_file])
                run_kubectl(["kubectl", "apply", "-f", dep_file])
                run_kubectl(["kubectl", "apply", "-f", svc_file])
                run_kubectl(["kubectl", "apply", "-f", hpa_file])

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
            start_time = time.time()
            while time.time() - start_time < 300:
                try:
                    out = subprocess.check_output(
                        ["kubectl", "get", "deployment", name, "-n", NAMESPACE, "-o", "json"],
                        text=True
                    )
                    data = json.loads(out)
                    ready_replicas = data.get("status", {}).get("readyReplicas", 0)
                    if ready_replicas >= 1:
                        envs_col.update_one({"env_name": name}, {"$set": {"status": "running"}})
                        return
                    
                    # Check for image pull errors
                    pod_out = subprocess.check_output(
                        ["kubectl", "get", "pods", "-n", NAMESPACE, "-l", f"app={name}", "-o", "json"],
                        text=True
                    )
                    pod_data = json.loads(pod_out)
                    if pod_data.get("items"):
                        container_statuses = pod_data["items"][0].get("status", {}).get("containerStatuses", [])
                        for cs in container_statuses:
                            waiting = cs.get("state", {}).get("waiting", {})
                            if waiting.get("reason") in ["ImagePullBackOff", "ErrImagePull"]:
                                envs_col.update_one({"env_name": name}, {"$set": {"status": "error", "error": f"Image Error: {waiting.get('message')}"}})
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
