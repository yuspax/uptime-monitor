# Uptime Monitor

A small monitoring project that checks websites, saves the results in PostgreSQL, and displays them in Grafana. It demonstrates how to package an application, provision AWS infrastructure, and deploy changes through GitOps.

The project is intended for learning and portfolio use. The AWS setup has one worker node and one PostgreSQL instance. It incurs AWS charges while running and does not provide high availability.

## Contents

- [What the project does](#what-the-project-does)
- [How the components fit together](#how-the-components-fit-together)
- [Files and folders](#files-and-folders)
- [Run locally](#run-locally)
- [Run on AWS](#run-on-aws)
- [Open Grafana and Argo CD](#open-grafana-and-argo-cd)
- [CI/CD and everyday changes](#cicd-and-everyday-changes)
- [Secrets](#secrets)
- [Tests](#tests)
- [Cleanup](#cleanup)
- [Troubleshooting](#troubleshooting)

## What the project does

The Python agent sends an HTTP request to each configured website. A response below HTTP 400 is recorded as `UP`; an HTTP error or failed request is recorded as `DOWN`. It stores the timestamp, website URL, status, HTTP code, and response time in the `http_logs` table, then waits 60 seconds before the next batch.

The agent is a background process. Its output is logs and database records. Grafana provides the browser interface.

There are two ways to run the project:

| Mode | What runs | What you need |
| --- | --- | --- |
| Local development | Python agent and PostgreSQL | Python 3.12, Docker, Git |
| AWS lab | Agent, PostgreSQL, Prometheus, Grafana, and Argo CD on EKS | AWS account, GitHub repository, and the tools listed below |

The local instructions verify the application's main behavior. The AWS instructions add Kubernetes monitoring, persistent EBS volumes, and automatic deployment from Git.

## How the components fit together

```text
Website requests -> Python agent -> PostgreSQL -> Grafana
Kubernetes and node metrics -> Prometheus -> Grafana

Terraform -> AWS networking, EKS, ECR, IAM, and EKS add-ons
lab.sh -> Local credentials, initial image, and Argo CD bootstrap
GitHub Actions -> Tests -> ECR image -> Image tag committed to Git
Argo CD -> Read Git -> Apply application and monitoring resources
```

| Component | Why it is here |
| --- | --- |
| Python agent | Check websites and write results to the database |
| PostgreSQL | Keep website history across application restarts |
| Docker | Package the agent and run PostgreSQL locally |
| Terraform | Define AWS infrastructure in one file |
| EKS | Run the Kubernetes workloads on AWS |
| ECR | Store the agent's container images |
| EBS CSI | Connect persistent EBS disks to Kubernetes pods |
| Prometheus | Collect Kubernetes and node metrics |
| Grafana | Display website history and infrastructure dashboards |
| Argo CD | Keep running workloads consistent with the configuration in Git |
| GitHub Actions | Test code, publish images, and record the desired image tag |

Website metrics come from PostgreSQL. Infrastructure metrics come from Prometheus. Grafana has both data sources configured automatically.

Some Kubernetes terms used in the files:

| Term | Meaning here |
| --- | --- |
| Pod | A running instance of a containerized workload |
| Namespace | A group of resources; this project uses `uptime` and `argocd` |
| Deployment | Manage the agent's pod and replace it during updates |
| StatefulSet | Give the PostgreSQL pod a stable identity |
| ConfigMap | Store settings such as URLs and database names |
| Secret | Store credentials referenced by pods |
| PVC | Request a persistent disk that survives pod replacement |
| StorageClass | Tell Kubernetes how to create that disk |
| Helm chart | A packaged set of Kubernetes templates, configured through values |

## Files and folders

| File | What it does |
| --- | --- |
| `app.py` | HTTP checks, database connections, table creation, inserts, logging, and shutdown handling |
| `Dockerfile` | Build the agent image using Python 3.12 and run it as a non-root user |
| `requirements.txt` | Pinned application dependencies: Requests and psycopg2 |
| `requirements-dev.txt` | Application dependencies plus pytest and Flake8 |
| `pytest.ini` | Configure pytest imports and test discovery |
| `tests/test_app.py` | Four tests covering configured sites, HTTP success, HTTP error, and timeout |
| `.env.example` | Names of the passwords required by the AWS lab |
| `.gitignore` | Keep passwords, state, kubeconfigs, caches, and local files out of Git |
| `.dockerignore` | Include only `app.py` and `requirements.txt` in the image build context |
| `scripts/lab.sh` | Commands to create, inspect, access, and remove the AWS lab |
| `terraform/main.tf` | All Terraform variables, AWS resources, pinned add-on versions, CI IAM role, and outputs |
| `terraform/.terraform.lock.hcl` | Lock the AWS provider version and checksums; commit this file |
| `k8s/app/namespace.yaml` | Create the `uptime` namespace |
| `k8s/app/storageclass.yaml` | Define encrypted gp3 EBS storage |
| `k8s/app/configmap.yaml` | Website URLs, database hostname, database name, and role names |
| `k8s/app/postgres-init.yaml` | Create the agent and Grafana database roles on an empty database |
| `k8s/app/postgres.yaml` | PostgreSQL StatefulSet, services, and a 5 GiB PVC |
| `k8s/app/agent.yaml` | Agent Deployment, resource limits, and configuration references |
| `k8s/app/kustomization.yaml` | Combine application manifests and select the ECR image and tag |
| `helm/argocd-values.yaml` | Configure a small Argo CD installation with an internal service |
| `helm/prometheus-values.yaml` | Configure metric collection, resources, retention, and storage |
| `helm/grafana-values.yaml` | Configure data sources, login Secret, dashboard loading, and storage |
| `dashboards/uptime-dashboard.json` | Website availability, response times, latest results, and freshness |
| `dashboards/prometheus-dashboard.json` | Node and Kubernetes resource metrics |
| `dashboards/kustomization.yaml` | Package dashboard JSON into a labeled ConfigMap |
| `gitops/project.yaml` | Restrict the Git repositories and destination used by the Applications |
| `gitops/applications.yaml` | Define four Applications: app, dashboards, Prometheus, and Grafana |
| `.github/workflows/ci.yml` | Tests, image publishing through OIDC, and the image-tag update |

These files are created locally and stay outside Git:

| File or folder | Purpose |
| --- | --- |
| `.env` | Real database and Grafana passwords |
| `.venv/` | Local Python dependencies |
| `.local/kubeconfig` | Access configuration for this EKS cluster |
| `.local/` | Local Helm cache, saved plans, and earlier configuration archives |
| `terraform/terraform.tfvars` | Your AWS administrator and repository settings |
| `terraform/terraform.tfstate` | Terraform's record of the AWS resources it manages |

## Run locally

Run commands from the repository root in Bash or Zsh. Start Docker Desktop first, or start the Docker daemon on Linux. Git Bash or WSL is needed for the shell commands on Windows.

### 1. Get the code and install Python dependencies

```bash
git clone https://github.com/yuspax/uptime-monitor.git
cd uptime-monitor
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

If you already cloned the project, use that checkout instead. Local development does not require AWS credentials, Terraform, kubectl, or the cloud `.env` file.

### 2. Start PostgreSQL

The following passwords are local development examples. Use different passwords for the AWS lab.

```bash
docker network create uptime-local
docker run -d --name uptime-local-db \
  --network uptime-local \
  -e POSTGRES_DB=uptime \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=local-admin-password \
  -p 127.0.0.1:5432:5432 \
  -v uptime-local-db-data:/var/lib/postgresql/data \
  postgres:15.19-alpine3.23
```

Check readiness. If PostgreSQL is still starting, wait a few seconds and repeat:

```bash
docker exec uptime-local-db pg_isready -U postgres -d uptime
```

When it reports `accepting connections`, create the application's database role:

```bash
docker exec -i uptime-local-db psql -U postgres -d uptime -v ON_ERROR_STOP=1 <<'SQL'
CREATE ROLE uptime_agent LOGIN PASSWORD 'local-agent-password';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE uptime TO uptime_agent;
GRANT USAGE, CREATE ON SCHEMA public TO uptime_agent;
SQL
```

Create the network, container, and role once for a new local setup. On later sessions, use `docker start uptime-local-db`. The named volume keeps the database and role; changing container password variables does not reset an existing database.

### 3. Run the agent

In the terminal with the Python virtual environment activated:

```bash
export DB_HOST=localhost
export DB_NAME=uptime
export DB_USER=uptime_agent
export DB_PASS=local-agent-password
export MONITOR_SITES=https://google.com,https://github.com
python app.py
```

You should see `Database initialized successfully` followed by website results. Leave the process running. In another terminal, inspect the records:

```bash
docker exec uptime-local-db psql -U postgres -d uptime \
  -c 'SELECT timestamp, site, status, status_code, latency_ms FROM http_logs ORDER BY id DESC LIMIT 10;'
```

Press `Ctrl+C` in the agent terminal to stop it.

### Optional: run the agent image locally

Stop the Python process first so you have one poller. With the same PostgreSQL container running:

```bash
docker build --tag uptime-agent:local .
docker run --rm --name uptime-local-agent \
  --network uptime-local \
  -e DB_HOST=uptime-local-db \
  -e DB_NAME=uptime \
  -e DB_USER=uptime_agent \
  -e DB_PASS=local-agent-password \
  -e MONITOR_SITES=https://google.com,https://github.com \
  uptime-agent:local
```

The database hostname is the container name when both containers use the same Docker network. Stop the foreground agent with `Ctrl+C`.

## Run on AWS

The default environment uses `eu-central-1`, EKS `1.36`, and one `m7i-flex.large` worker. It has two public subnets, an Internet Gateway, and no NAT Gateway. Application services stay inside the cluster; you access the UIs through local tunnels. The EKS public API is restricted to your configured public IP.

The Helm chart versions are pinned:

| Chart | Version | Namespace |
| --- | --- | --- |
| Argo CD | `10.10.5` | `argocd` |
| Prometheus | `29.37.2` | `uptime` |
| Grafana | `14.0.1` | `uptime` |

### 1. Prepare tools and accounts

Install AWS CLI v2, Terraform `>= 1.10, < 2.0`, kubectl compatible with the cluster, Helm, Docker, Git, and GitHub CLI (`gh`). This setup has been used with Helm 4. Start Docker and authenticate GitHub CLI:

```bash
gh auth login
aws sts get-caller-identity
```

AWS CLI must already be authenticated through your chosen profile or SSO session. The AWS identity needs permission to create EKS, EC2 networking, ECR, IAM roles and policies, CloudWatch logs, and EKS access entries. GitHub CLI needs access to the repository you will deploy from.

### 2. Point the project at your GitHub repository

Use a repository you can push to. When using a fork, keep a `master` branch and update:

- The `repoURL` values in `gitops/applications.yaml`.
- The GitHub entry in `sourceRepos` in `gitops/project.yaml`.
- `github_repository` in your Terraform inputs below.
- The Git origin and `--repo` arguments in the GitHub CLI commands in this guide.

The supplied addresses refer to `yuspax/uptime-monitor`. Replace them with your repository when using a fork. Argo CD can read a public repository directly; a private fork also requires read-only repository credentials in Argo CD.

### 3. Create local configuration

On a new checkout, copy the template:

```bash
cp .env.example .env
chmod 600 .env
```

Skip the copy if `.env` already exists. Fill all four password fields with different values and keep `GRAFANA_ADMIN_USER=admin`. Use unquoted `KEY=value` lines. You can generate each password with `openssl rand -hex 24`.

Create `terraform/terraform.tfvars`, replacing these example values:

```hcl
admin_cidr          = "203.0.113.10/32"
admin_principal_arn = "arn:aws:iam::123456789012:user/your-admin-user"
github_repository  = "yuspax/uptime-monitor"
```

`admin_cidr` is your current public IPv4 address followed by `/32`. Find that address with:

```bash
curl -fsS https://checkip.amazonaws.com
```

`admin_principal_arn` is the IAM user or role that will administer Kubernetes. For an assumed-role session, use its underlying IAM role ARN, not the `arn:aws:sts::...` session ARN. That administrator also needs `eks:DescribeCluster` permission in AWS.

Other Terraform inputs have defaults:

| Input | Default |
| --- | --- |
| `aws_region` | `eu-central-1` |
| `cluster_name` | `uptime-lab-cluster` |
| `kubernetes_version` | `1.36` |
| `node_instance_type` | `m7i-flex.large` |

The add-on versions are pinned in `local.eks_addon_versions`. Review their compatibility if you change the Kubernetes version.

### 4. Check GitHub OIDC in AWS

OIDC lets GitHub Actions obtain temporary AWS credentials. Terraform expects the account's shared GitHub provider to exist:

```bash
aws iam list-open-id-connect-providers
```

Look for a provider ARN ending in `oidc-provider/token.actions.githubusercontent.com`. If it is absent, register it once:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com
```

For an existing provider, confirm its client ID list includes `sts.amazonaws.com`. Terraform reuses this provider and leaves it in place when the lab is destroyed.

The supplied CI trust condition is `repo:yuspax/uptime-monitor:ref:refs/heads/master`. For your repository, inspect its subject prefix:

```bash
gh api repos/yuspax/uptime-monitor/actions/oidc/customization/sub \
  --jq '.sub_claim_prefix'
```

The original repository returns `repo:yuspax/uptime-monitor`. A newer fork may return owner and repository IDs with `@` characters. In that case, update the `token.actions.githubusercontent.com:sub` condition in `terraform/main.tf` to the returned prefix followed by `:ref:refs/heads/master`. See [GitHub's OIDC subject examples](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws) for the formats.

### 5. Provision infrastructure for the first time

This first manual apply creates the ECR repository and CI role so you can configure GitHub before its first pipeline run:

```bash
mkdir -p .local
terraform -chdir=terraform init
terraform -chdir=terraform fmt -check
terraform -chdir=terraform validate
terraform -chdir=terraform plan -out=../.local/bootstrap.tfplan
```

Review the plan, then create the resources:

```bash
terraform -chdir=terraform apply ../.local/bootstrap.tfplan
terraform -chdir=terraform output
```

Terraform provisions AWS infrastructure. The application and monitoring are deployed during bootstrap below.

Use the `ecr_repository_url` output as `newName` in `k8s/app/kustomization.yaml`. Keep the initial bootstrap tag, or select an existing image tag from that ECR repository.

### 6. Configure CI and publish your configuration

Set three repository variables using Terraform outputs:

```bash
gh variable set AWS_REGION --repo yuspax/uptime-monitor \
  --body "$(terraform -chdir=terraform output -raw aws_region)"
gh variable set AWS_ROLE_ARN --repo yuspax/uptime-monitor \
  --body "$(terraform -chdir=terraform output -raw github_actions_role_arn)"
gh variable set ECR_REPOSITORY --repo yuspax/uptime-monitor \
  --body "$(terraform -chdir=terraform output -raw ecr_repository_url)"
```

These values are not secrets. The workflow uses AWS OIDC for image publishing and the built-in `GITHUB_TOKEN` for the image-tag commit. It does not need AWS access keys, database passwords, or an EKS kubeconfig.

Review your changes before publishing. `.env`, `terraform.tfvars`, state, and `.local/` must not appear as files to commit:

```bash
git status --short
git add -A
git commit -m "Configure the EKS GitOps lab"
git push origin master
```

Wait for the first pipeline to finish. It publishes the image and makes a bot commit with its tag:

```bash
gh run list --workflow ci.yml --branch master
gh run watch --exit-status
git pull --ff-only
```

Use the Actions tab if you prefer the browser. Pulling the bot commit keeps your checkout aligned with the configuration Argo CD will read.

### 7. Bootstrap the workloads

```bash
scripts/lab.sh up
scripts/lab.sh status
```

`up` performs these steps:

1. Check required tools, `.env`, Terraform inputs, and that local files match published `master`.
2. Plan and apply Terraform automatically. After the initial setup, this normally reuses existing infrastructure.
3. Write `.local/kubeconfig` and wait for a Ready node.
4. Create the namespace, StorageClass, and a missing `uptime-secrets` Secret.
5. Build and push the selected initial image if that tag is absent from ECR.
6. Install Argo CD and register the four Applications.
7. Wait for all four Applications to become `Synced` and `Healthy`.

The script refuses unpublished changes because Argo CD reads GitHub. Existing Secrets, image tags, and PVCs are reused.

Expected results are one Ready node, healthy pods in `uptime` and `argocd`, three Bound PVCs, and four healthy Argo CD Applications. The cloud setup keeps Terraform state locally; GitHub Actions does not apply Terraform.

## Open Grafana and Argo CD

Open Grafana in one terminal:

```bash
scripts/lab.sh grafana
```

Visit `http://localhost:3000`, log in as `admin`, and use `GRAFANA_ADMIN_PASSWORD` from `.env`. The `Uptime Monitor` folder contains:

- `Website Uptime`: website results, availability, successful response times, and time since the latest check.
- `Kubernetes Overview`: node CPU, memory, disk usage, pods, restarts, workload usage, and network traffic.

Availability is the percentage of recorded checks marked `UP` in the selected time range. The freshness panel helps identify a stopped agent. Prometheus retains one day of metrics on a 5 GiB PVC; Grafana keeps its own state on a separate 1 GiB PVC. Website history stays in PostgreSQL's 5 GiB PVC.

Open Argo CD in another terminal:

```bash
scripts/lab.sh argocd
```

Visit `https://localhost:8443` and accept the lab's self-signed certificate. Log in as `admin`. Read the initial password from a third terminal:

```bash
export KUBECONFIG="$PWD/.local/kubeconfig"
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
printf '\n'
```

Keep each tunnel running while using its UI. If a tunnel is already listening on the port, use that existing tunnel. Changing the Argo CD password makes the initial value obsolete.

## CI/CD and everyday changes

The workflow has three jobs: `test`, `publish`, and `update-manifest`. Pull requests and other branches run checks only. A successful `master` run publishes a `linux/amd64` image tagged with the source commit SHA, then commits that tag to the application manifest. Argo CD detects the Git change and deploys it.

The publishing role trusts the configured repository's `master` branch and has access to this project's ECR repository. The manifest job has repository write permission and uses a direct bot push to `master`. This lab assumes that branch permits direct pushes; repositories requiring pull requests need a promotion flow that opens a PR instead.

| Change | File to edit | How to apply it |
| --- | --- | --- |
| Agent behavior | `app.py` | Commit and push; CI tests and publishes the new image |
| Website list | `k8s/app/configmap.yaml` | Commit and push; restart the agent after the ConfigMap syncs |
| Dashboard panels | `dashboards/*.json` | Commit and push; Grafana's sidecar reloads the ConfigMap |
| Monitoring resources or data sources | `helm/*-values.yaml` | Commit and push; Argo CD applies the rendered chart |
| Chart versions or Application settings | `gitops/applications.yaml` | Commit, push, then reapply this bootstrap file with kubectl |
| AWS infrastructure | `terraform/main.tf` | Review a Terraform plan and apply it locally |

For manual Kubernetes commands, set the local kubeconfig first:

```bash
export KUBECONFIG="$PWD/.local/kubeconfig"
kubectl -n argocd get applications
kubectl -n uptime get pods,pvc
kubectl -n uptime logs deployment/uptime-agent --tail=20
```

ConfigMaps passed as environment variables are read when a pod starts. After a website-list change has synced, restart the agent to load it:

```bash
kubectl -n uptime rollout restart deployment/uptime-agent
```

When editing Application definitions themselves:

```bash
kubectl apply -f gitops/project.yaml
kubectl apply -f gitops/applications.yaml
```

Argo CD uses `selfHeal` to restore managed fields changed manually and `prune` to remove managed resources deleted from Git. The namespace, StorageClass, and data PVCs have protection against Argo CD pruning. The Secret is created separately during bootstrap. Once monitoring is managed by Argo CD, update its values through Git rather than running Helm upgrades for those releases.

ECR tags are immutable, so reruns reuse an image already published for that SHA. Runs on `master` are serialized. A run skips its tag update if `master` has moved; a conflicting push fails without force-pushing.

For a rollback, change only `k8s/app/kustomization.yaml` to a previously published tag, commit, and push. Tag-only pushes skip CI so your selected version is preserved. Bot pushes made with `GITHUB_TOKEN` also do not start another push-triggered workflow. Argo CD still sees both kinds of commits through Git polling.

## Secrets

The AWS lab uses one Kubernetes Secret named `uptime-secrets`, created from `.env` before workloads start. `lab.sh` reads the file with kubectl's `--from-env-file`; it does not execute it as shell code.

| Key | Used for |
| --- | --- |
| `DB_ADMIN_PASSWORD` | PostgreSQL administration and initial role setup |
| `DB_PASS` | The `uptime_agent` role, which creates tables and writes checks |
| `GRAFANA_DB_PASS` | The `grafana_reader` role, which reads application tables |
| `GRAFANA_ADMIN_USER` | Grafana login username, normally `admin` |
| `GRAFANA_ADMIN_PASSWORD` | Grafana administrator login password |

Existing Secrets are preserved on repeated `up` runs. Changing `.env` does not rotate live database passwords or an existing Grafana administrator password. Keep the original credentials when reusing their disks.

If the PostgreSQL PVC exists but its Secret is missing, restore the original values in `.env`, then recreate the Secret:

```bash
export KUBECONFIG="$PWD/.local/kubeconfig"
kubectl -n uptime create secret generic uptime-secrets --from-env-file=.env
```

The database initialization script runs only on an empty volume. Password rotation requires updating PostgreSQL or Grafana first and then their dependent configuration. Kubernetes Secret values are base64 encoded; never publish a Secret manifest as though it were encrypted. `.env`, kubeconfigs, private keys, and Terraform state stay outside Git.

## Tests

From the Python virtual environment, run:

```bash
python -m flake8 app.py tests --count --select=E9,F63,F7,F82 --show-source --statistics
python -m pytest
bash -n scripts/lab.sh
docker build --tag uptime-agent:local .
```

The four unit tests mock HTTP responses. They need no AWS access, database, or external HTTP requests. The local startup walkthrough above checks the real database path. GitHub Actions runs these checks before publishing an image.

## Cleanup

### Local development

Stop the foreground agent with `Ctrl+C`. To keep the database for later, stop its container:

```bash
docker stop uptime-local-db
```

To permanently remove the local database and its history, stop the agent first, then run:

```bash
docker rm -f uptime-local-db
docker volume rm uptime-local-db-data
docker network rm uptime-local
```

### AWS lab

```bash
scripts/lab.sh down
```

Type the cluster name when prompted. The script detaches Argo CD Applications, deletes the `uptime` namespace and its PVCs, waits for EBS volume deletion, then destroys Terraform resources. Database history, monitoring history, and images in the lab's ECR repository are deleted. The shared GitHub OIDC provider remains.

Keep `terraform/terraform.tfstate` until cleanup finishes. If deletion fails, inspect the reported resource and retry after resolving the cause. Deleting Argo CD Application objects alone leaves their workloads running because these Applications have no cascading deletion finalizer.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Docker cannot connect | Start Docker Desktop or the Linux Docker daemon |
| Local database port is occupied | Stop the other listener on port 5432 before starting this database |
| Local role already exists | Reuse its original password; the role-creation step is for a new volume |
| Agent cannot connect to PostgreSQL | Wait for readiness and check the hostname and password; container mode uses `uptime-local-db` |
| `up` refuses unpublished changes | Commit and push the files, wait for CI, then pull the bot's tag commit |
| Terraform cannot find the GitHub OIDC provider | Register the provider once in the same AWS account |
| CI cannot assume the AWS role | Check `AWS_ROLE_ARN`, the exact repository OIDC subject, the `master` branch, and the STS audience |
| CI cannot push the manifest commit | Check `contents: write`, branch protection, and whether `master` moved during the run |
| kubectl times out after changing networks | Update `admin_cidr` to your new public IP and apply Terraform |
| PVC is Pending | Check node readiness, EBS CSI, the StorageClass, and pod events |
| Grafana has no new website data | Check agent logs and the latest database timestamp; confirm the selected dashboard time range |
| UI tunnel reports address already in use | Use the existing tunnel or stop its process before opening another |

Inspect cloud database records with:

```bash
export KUBECONFIG="$PWD/.local/kubeconfig"
kubectl -n uptime exec statefulset/postgres-db -- \
  psql -U postgres -d uptime -c 'SELECT timestamp, site, status, latency_ms FROM http_logs ORDER BY id DESC LIMIT 10;'
```

If AWS rejects the instance type for account eligibility, choose a supported x86_64 type in the region and review its capacity and charges. EKS and the other lab resources are billed independently of EC2 eligibility.

Earlier K3s and Sealed Secrets files are archived under ignored `.local/` on the original setup machine. Those archives are not needed for a fresh setup. The old K3s security group and SSH key pair belong to separate legacy infrastructure and are outside this lab's Terraform state.

Useful references: [GitHub OIDC with AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws), [AWS OIDC provider creation](https://docs.aws.amazon.com/cli/latest/reference/iam/create-open-id-connect-provider.html), and [Kubernetes Secret creation](https://kubernetes.io/docs/tasks/configmap-secret/managing-secret-using-kubectl/).
