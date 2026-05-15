# 🏗️ Project Architecture & Flow Deep-Dive

This document provides a comprehensive technical breakdown of the **Intelligent Ephemeral Multi-Stack Development Platform**, detailing what each component does, how they interact, and when specific processes are triggered.

---

## 🛰️ 1. Orchestration Engine (The "Brain")
### File: `backend/app.py`
This is the core Python service that manages the lifecycle of all development environments.

*   **WHAT it does**: Orchestrates Kubernetes API calls, monitors pod health, manages TTL (Time-To-Live) cleanup, and serves metadata to the UI.
*   **WHEN it triggers**:
    *   **Startup**: Connects to the Kubernetes cluster and starts a background thread for TTL monitoring.
    *   **User Action (Launch)**: Triggered by the `/provision` endpoint. It reads the K8s templates, injects environment-specific variables (CPU, Memory, Ports), and applies the YAML.
    *   **Async Polling**: The `/status` endpoint is polled by the frontend every 5 seconds to provide real-time updates on provisioning progress.
*   **HOW it works**: It uses the `subprocess` module to execute `kubectl` commands directly, ensuring compatibility with Minikube environments.

---

## 🎨 2. Unified Access Portal (The "Body")
### Directory: `frontend/` (index.html, style.css)
A high-performance "Glassmorphism" dashboard for managing the cloud stacks.

*   **WHAT it does**: Provides a visual interface to launch, delete, and monitor environments. Includes a **Stress Test** feature to demonstrate HPA.
*   **TRIGGER**: When a user clicks **"Deploy X Stack"**, a JavaScript fetch call triggers the backend's provisioning pipeline.
*   **HOW it works**: Uses a state-driven approach where buttons transform based on the environment's current status (PROVISIONING, RUNNING, or ERROR).

---

## 📦 3. Interactive Ephemeral Stacks (The "Environments")
### Directory: `templates/` (Flask, Java, MERN, ML)
Each stack is a fully isolated, containerized web-IDE based on Monaco Editor.

*   **WHAT they do**: Provide a real-time coding environment where users can write and execute code within the browser.
*   **STABILITY GUARDRAILS** (Triggered on every "RUN" click):
    *   **Execution Timeout (30s)**: Automatically kills any process (like infinite loops) that exceeds the limit.
    *   **Output Truncation (10KB)**: Limits the stdout/stderr buffer to prevent memory exhaustion and pod crashes.
*   **HOW it works**: A hidden Flask/Node.js backend inside the pod receives the code via POST, writes it to a temporary file, executes it via a subprocess, and returns the output to the Monaco console.

---

## 🛡️ 4. Infrastructure & DevSecOps (The "Foundation")
### Directory: `ansible/` & `jenkins/`
The system is pre-configured and audited automatically.

*   **Ansible (`setup.yml`)**:
    *   **WHEN**: Triggered manually during initial setup.
    *   **WHAT**: Configures Docker, sets up Minikube, and ensures Trivy (Security Scanner) is installed.
*   **Jenkins (`Jenkinsfile`)**:
    *   **WHEN**: Triggered on every code push (CI/CD).
    *   **WHAT**: Automatically builds Docker images for all 4 stacks AND runs a **Trivy Vulnerability Scan** on each image.
    *   **TRIGGER**: If a High/Critical vulnerability is found, the pipeline fails, preventing insecure code from entering the cluster.

---

## 📈 5. Auto-Scaling & Resiliency (The "Intelligence")
### Files: `k8s/hpa.yaml` & `k8s/deployment.yaml`
The platform proactively manages resources.

*   **HPA (Horizontal Pod Autoscaler)**:
    *   **TRIGGER**: When a user runs a calculation-heavy or infinite script in a stack, CPU usage spikes.
    *   **REACTION**: K8s detects usage > 50% and automatically spawns up to 3 replicas of that specific environment.
*   **TTL Cleanup**:
    *   **TRIGGER**: The backend background thread runs every 10 seconds.
    *   **REACTION**: If an environment has been running longer than its set expiry (e.g., 30 mins), it is automatically deleted to save cluster resources.

---

## 🔄 Trigger Flow Example
1. **User** clicks "Run Java" with a complex loop.
2. **Frontend** POSTs code to **Pod IP**.
3. **Internal Backend (templates/java/app.py)** executes code with a **30s Timeout**.
4. **HPA Controller** monitors the CPU spike.
5. **Ansible/Trivy** ensures that the pod being scaled was previously audited for security.
