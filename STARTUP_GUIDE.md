# 🚀 SPE Dev Platform: Step-by-Step Startup Guide

This guide provides a professional, linear workflow to boot, secure, and test the Intelligent Ephemeral Platform on your local machine.

## 📋 Prerequisites
Before you begin, ensure you have the following installed:
- **Docker & Docker Compose** (Container runtime)
- **Minikube** (Local Kubernetes cluster)
- **Ansible** (Infrastructure automation)
- **Trivy** (Security scanner)
- **Python 3.10+** (Backend server)
- **Jenkins** (CI/CD - optional if testing manually)

---

## Phase 1: Infrastructure Setup

### Step 1: Automated Environment Prep
Run the modular Ansible roles to configure Docker, Kubectl, Minikube, and **Trivy** (Security Scanner) automatically.
```bash
cd ansible
ansible-playbook setup.yml
```
**Verification**: Run `docker ps`, `kubectl version`, and `trivy --version` to ensure all tools are responding.

### Step 2: Boot Core Services
Start the Kubernetes cluster and the Observability stack (ELK).
```bash
# 1. Start Minikube with resources for multi-pod scaling
minikube start --driver=docker --memory=4096 --cpus=4
minikube addons enable metrics-server

# 2. Launch Elastic Stack & Vault
docker-compose up -d
```
**Verification**: Check `http://localhost:5601` for Kibana (Wait ~2 mins for initialization).

---

## Phase 2: Platform Deployment

### Step 3: Deploy Application Infrastructure
Deploy MongoDB and the Backend API to Kubernetes.
```bash
# Apply K8s manifests
kubectl apply -f k8s/config.yml
kubectl apply -f k8s/secrets.yml
kubectl apply -f k8s/mongo.yaml
kubectl apply -f k8s/backend.yaml
```

### Step 4: Expose the Backend
Since the backend runs securely inside the cluster, you must expose it locally for the frontend to connect. Open a **new terminal** and run:
```bash
kubectl port-forward svc/backend-svc 5002:5002 -n dev-platform
```
*(Keep this terminal open!)*

### Step 5: Launch the Frontend
Open another terminal and serve the UI.
```bash
cd frontend
python -m http.server 8080
```
Access the platform at: `http://localhost:8080`

---

## Phase 3: Security & Scaling Tests

### Step 6: Manual Security Audit (Trivy)
To verify image integrity before deployment, run a scan:
```bash
trivy image --severity HIGH,CRITICAL p1yush123/flask-env:latest
```

### Step 7: Local HPA Stress Test
1. Log in to the dashboard (`testuser`/`123`).
2. Provision a **Java** or **Flask** environment.
3. Click the yellow **"Stress Test"** button.
4. Run this monitoring command:
```bash
kubectl get hpa -n dev-platform -w
```
Watch the `REPLICAS` count increase from **1 → 3** as your code hits the CPU threshold!

---

## 🛠 Troubleshooting
- **Port 5001 Busy**: Run `sudo fuser -k 5001/tcp`.
- **ImagePullBackOff**: Ensure you are logged into Docker (`docker login`) or build images locally using `docker build -t p1yush123/flask-env:latest templates/flask`.
- **Mongo Connection Refused**: Ensure the Port-Forward in Step 3 is actively running.
