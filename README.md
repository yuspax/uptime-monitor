# Uptime Monitor

A containerized Python application that monitors website availability.
The project represents a complete **pipeline** following IaC principles.

**Tech Stack:** Python, Docker, AWS EC2, Terraform, Ansible, GitHub Actions.

---

## 💻 Option 1: Run Application Locally

If you just want to run the monitoring script on your machine.

### Prerequisites
* Docker installed.

### Steps
1. **Clone the repository:**
   ```bash
   git clone [https://github.com/yuspax/uptime-monitor.git](https://github.com/yuspax/uptime-monitor.git)
   cd uptime-monitor



2. **Start the container:**
```bash
docker compose up -d

```


3. **View logs (Real-time):**
```bash
docker compose logs -f

```



---

## ☁️ Option 2: Deploy Infrastructure

This section explains how to provision the AWS infrastructure and deploy the app manually using Terraform and Ansible.

### Step 1: Provision Infrastructure (Terraform)

Creates the EC2 instance, Security Groups, and SSH Key.

1. Navigate to the terraform directory:
```bash
cd terraform

```


2. Initialize and apply configuration:
```bash
terraform init
terraform apply -auto-approve

```


3. **Result:** Terraform will output the **Public IP** of your new server. Copy it.

### Step 2: Configure Server (Ansible)

Installs Docker and deploys the application container on the EC2 instance.

1. Navigate to the ansible directory:
```bash
cd ../ansible

```


2. Update `inventory.yml` with your new Server IP:
```ini
ansible_host: ...
```


3. Run the playbook:
```bash
ansible-playbook -i inventory.yml playbook.yml

```



---

## 🤖 CI/CD Pipeline (Automation)

Once the infrastructure is up (Step 1: Provision Infrastructure (Terraform)), you don't need to touch the server manually. The repository uses **GitHub Actions** to automate the entire lifecycle.

### 1. Configure Secrets (One-time setup)
To allow GitHub to communicate with your AWS server, add these secrets in **Settings -> Secrets and variables -> Actions**:

* `SERVER_IP`: The Public IP of your EC2 instance (from Terraform output).
* `SSH_PRIVATE_KEY`: The content of `terraform/ssh-keys/uptime_key` (copy the whole file).

### 2. How the Pipeline Works
The workflow (`.github/workflows/deploy.yml`) handles two stages:

* **(CI):**
  On every push to any branch, the system runs `flake8` (linting) and `pytest` (unit tests) to ensure code quality.

* **(CD):**
  When code is merged into the `master` branch, the pipeline:
  1. Connects to the AWS server via SSH.
  2. Pulls the latest code.
  3. Rebuilds and restarts the Docker container via Ansible.

---

## ⚙️ App Configuration

To change the monitored websites, edit `app.py`:

```python
sites = ["google.com", "facebook.com", "your-site.com"]

```

Then restart:

```bash
docker compose restart

```

## 📂 Project Structure

```text
uptime-monitor/
├── .github/            # CI/CD Workflows
├── ansible/            # Configuration Management (Playbooks)
├── terraform/          # Infrastructure as Code (AWS)
├── tests/              # Unit Tests
├── app.py              # Application Source Code
├── Dockerfile          # Docker Image Config
└── docker-compose.yml  # Local Orchestration

```
