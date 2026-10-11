# DIAD — AI-Powered Data Intelligence for Entrepreneurs

> **Turn your store's raw data into an AI chatbot that knows everything about your business — deployed in under 30 minutes, running entirely inside your own Google Cloud account.**

DIAD (Data Intelligence & Analytics Dashboard) is an end-to-end data warehouse and AI chatbot platform built specifically for e-commerce entrepreneurs. It connects to your Google Drive documents, Notion pages, Firestore orders, and Google Analytics — then deploys a private AI assistant that can answer questions about your customers, orders, policies, and operations.

---

## 🚀 Get Started in 60 Seconds

### Prerequisites
- **Windows 10/11** (the setup script handles everything else automatically)
- **A Google Cloud account** (free tier is sufficient — [sign up here](https://console.cloud.google.com/))

### One-Line Setup (PowerShell)

```powershell
irm https://raw.githubusercontent.com/dataforentrepreneurs/DIAD_Scaffold/main/setup.ps1 | iex
```

Or clone and run directly:
```powershell
git clone https://github.com/dataforentrepreneurs/DIAD_Scaffold.git
cd DIAD_Scaffold
.\setup.ps1
```
**That's it.** The script will automatically:
- ✅ Download the encrypted DIAD release package
- ✅ Install Python 3.11 (if not already installed)
- ✅ Install Google Cloud SDK (for deployment)
- ✅ Create virtual environment & dependencies
- ✅ Open the onboarding dashboard in your browser (`http://localhost:8000`)


---

## 🖥️ What Happens Next

Once the dashboard opens at `http://localhost:8000`, you'll follow a guided wizard:

| Step | What You Do | What DIAD Does |
|------|------------|----------------|
| **1. GCP Setup** | Create a Google Cloud project & upload your service account key | Auto-configures your deployment credentials |
| **2. Link Sources** | Share your Google Drive folders & connect Notion | Sets up document access for the AI |
| **3. API Keys** | Enter your OpenAI & Pinecone keys | Securely vaults them in your GCP Secret Manager |
| **4-8. Pipeline** | Click "Run" on each step | Builds your data warehouse & deploys your chatbot |

An interactive **Onboarding Mentor** guides you through every step with plain-English instructions.

---

## 🔒 Data Architecture & Privacy Boundary

DIAD follows a hybrid architecture designed for enterprise control: all operational warehouse tables and deployment scaffolding reside inside your personal Google Cloud tenant, while AI synthesis queries your configured providers.

### What Stays Inside Your Google Cloud Project & Local Machine
| Component | Location | Details |
|-----------|----------|---------|
| **Data Warehouse & Marts** | Google BigQuery | All raw e-commerce orders, customer identities, daily inventory, and analytical marts reside entirely in your private BigQuery datasets (`ecommerce_canonical`, `ecommerce_mart`). |
| **Object Landing Storage** | Google Cloud Storage | Ingested source files and export archives are stored in your private `gs://[client]-storage/` bucket. |
| **API Keys & Vaults** | GCP Secret Manager | External provider tokens are vaulted in your project's Secret Manager and mounted directly into container memory at runtime. |
| **Chatbot Compute Engines** | Google Cloud Run | Both internal and external API services execute inside container instances in your chosen GCP region. |
| **Onboarding Wizard** | Local Machine | The setup wizard runs locally at `http://localhost:8000` to orchestrate cloud resource creation. |

### What Data Leaves Your Cloud (External Network Calls)
To provide natural-language reasoning and vector search, DIAD transmits specific runtime data over encrypted HTTPS directly to your configured third-party accounts:
- **LLM Providers (OpenAI & Google AI Studio/Gemini):** When an end-user or employee submits a question, the user's question, sanitized order context (with strict PII masking), and matching document excerpts are sent to your configured OpenAI (`api.openai.com`) or Gemini endpoint to formulate responses.
- **Vector Database (Pinecone):** Knowledge base policy documents (Google Drive, Notion, Confluence) are chunked and converted into vector embeddings stored in your Pinecone index (`api.pinecone.io`) for fast semantic retrieval.
- **Document Integrations:** Read-only document sync connects via official APIs to Google Drive, Notion, and Confluence spaces shared by your team.

---

## ⚙️ Operations, Upgrades & Rollbacks

### 🚀 Deploying Versioned Release Images
To deploy the pre-built, version-pinned DIAD container image into Cloud Run:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/phase9/9_2_deploy_cloud_run.ps1 `
  -SkipBuild `
  -ImageRef "asia-southeast1-docker.pkg.dev/<PROJECT_ID>/diad/diad-engine:v1.0.0"
```

### 🔄 Upgrading to a New Version
When a new version is released, zero changes are required to your BigQuery data or configuration. Simply point Cloud Run to the new immutable image tag:
```bash
# Upgrade External Chatbot
gcloud run services update diad-external-chat \
  --image=asia-southeast1-docker.pkg.dev/<PROJECT_ID>/diad/diad-engine:v1.1.0 \
  --region=asia-southeast1

# Upgrade Internal Analytics Chatbot
gcloud run services update diad-internal-chat \
  --image=asia-southeast1-docker.pkg.dev/<PROJECT_ID>/diad/diad-engine:v1.1.0 \
  --region=asia-southeast1
```

### ⏪ Instant Rollback
If an upgrade needs to be reverted, roll back immediately to the previous pinned image tag:
```bash
gcloud run services update diad-external-chat \
  --image=asia-southeast1-docker.pkg.dev/<PROJECT_ID>/diad/diad-engine:v1.0.0 \
  --region=asia-southeast1
```
Or revert to the previous Cloud Run revision directly:
```bash
gcloud run services rollback diad-external-chat --region=asia-southeast1
```

### 🩺 Health Checks & Diagnostics
Both services provide standard health check endpoints:
- `GET /` — Basic service status
- `GET /health` — Service readiness check
- `GET /healthz` — Kubernetes / Cloud Run health check

To view real-time runtime logs:
```bash
gcloud run services logs read diad-external-chat --limit=50 --region=asia-southeast1
gcloud run services logs read diad-internal-chat --limit=50 --region=asia-southeast1
```

---

## 🧹 Resetting & Re-running Sandbox Demos (The Diamante Collections)

If you are using **The Diamante Collections** (`diamante-diad`) sandbox to pitch prospective clients or record demo videos, you can instantly wipe remote GCP resources and reset local configs with a single command:

```powershell
.\scripts\reset_diamante_sandbox.ps1 -Force
```

### What the Reset Script Automatically Wipes:
- 🗑️ **Cloud Run Services & Jobs**: Deletes `diad-external-chat`, `diad-internal-chat`, and doc sync jobs.
- 🗑️ **Cloud Scheduler**: Removes `diad-phase8-sync-quarterly` cron triggers.
- 🗑️ **Secret Manager**: Clears vaulted API keys (`OPENAI_API_KEY`, `PINECONE_API_KEY`, etc.).
- 🗑️ **BigQuery Datasets**: Force-deletes `ecommerce_raw`, `ecommerce_canonical`, and `ecommerce_mart`.
- 🗑️ **GCS Storage Objects**: Clears raw landing files in `gs://diamante-diad-storage/`.
- 🔄 **Local Configuration & Keys**: Resets `config/client_rawdata.json` back to default template, removes local Service Account `.json` keys in `keys/`, and deletes `config/.secrets_synced` flag.

After running the script, launch `python scripts/onboarding_dashboard.py` (or `.\setup.ps1`) to run a 100% clean onboarding pitch from Step 1!

---

## 📦 What's Inside

```
DIAD/
├── setup.ps1                    ← One-click setup script
├── scripts/
│   ├── onboarding_dashboard.py  ← The onboarding wizard server
│   ├── 1_*.py                   ← GCP bootstrap scripts
│   ├── phase3/                  ← Data ingestion pipeline
│   ├── phase7/                  ← Chatbot data preparation
│   ├── phase8/                  ← Vector database sync
│   └── phase9/                  ← Cloud Run deployment
├── chatbot/
│   ├── external_api.py          ← Customer-facing chatbot API
│   └── internal_api.py          ← Admin chatbot API
├── dbt/                         ← Data transformation models
├── config/                      ← Project configuration
├── keys/                        ← Service account keys (gitignored)
└── documentation/               ← Detailed technical guides
```

---

## 💼 Licensing

DIAD is a commercial product by [DataForEntrepreneurs](https://github.com/dataforentrepreneurs). The source code is provided for transparency and self-hosted deployment. Usage is subject to the license terms included in this repository.

For enterprise licensing, custom integrations, or managed deployment, contact: **dataforentrepreneurs@gmail.com**

---

## 🛠️ For Developers

<details>
<summary>Manual Setup (without the setup script)</summary>

```powershell
# 1. Clone
git clone https://github.com/dataforentrepreneurs/DIAD_Agent.git
cd DIAD_Agent

# 2. Virtual environment
python -m venv venv_dbt
.\venv_dbt\Scripts\activate

# 3. Install dependencies (lightweight for dashboard only)
pip install -r requirements_onboarding.txt

# 4. Launch
python scripts/onboarding_dashboard.py
# → Open http://localhost:8000
```

For the full ML pipeline (torch, sentence-transformers), install the complete requirements:
```powershell
pip install -r requirements.txt
```

</details>

<details>
<summary>Architecture Documentation</summary>

See the `documentation/` folder for detailed guides:
- [Architecture Overview](documentation/0_diad_architecture.md)
- [GCP Onboarding](documentation/1_client_gcp_onboarding.md)
- [Self-Serve Architecture](documentation/12_self_serve_architecture.md)
- [Automated Onboarding Guide](documentation/13_automated_onboarding_guide.md)

</details>