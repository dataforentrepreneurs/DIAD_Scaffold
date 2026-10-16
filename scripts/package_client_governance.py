#!/usr/bin/env python3
"""
DIAD Client Governance & Handover Package Generator
Packages institutional security, legal, cost, and onboarding documentation
into a clean ZIP archive ready to deliver to client founders and IT leads.
"""

import os
import json
import zipfile
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

def load_client_config(config_path: str = "config/client_rawdata.json"):
    p = ROOT_DIR / config_path
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def generate_package(client_slug: str = None, output_dir: str = "dist_release"):
    cfg = load_client_config()
    client_info = cfg.get("client", {})
    gcp_info = cfg.get("gcp", {})
    
    raw_biz = client_info.get("business_name")
    if not client_slug:
        if raw_biz and raw_biz != "YOUR_BUSINESS_NAME":
            client_slug = "".join([c if c.isalnum() else "_" for c in raw_biz]).strip("_").lower()
        else:
            client_slug = "client"

    business_name = raw_biz if (raw_biz and raw_biz != "YOUR_BUSINESS_NAME") else client_slug.replace("_", " ").title()
    project_id = client_info.get("project_id")
    if not project_id or project_id == "Not Configured":
        project_id = f"{client_slug}-diad"
    region = gcp_info.get("region", "asia-southeast1")
    store_url = client_info.get("website_url") or client_info.get("store_url", "https://yourstore.com")
    admin_email = client_info.get("business_email", "admin@yourstore.com")
    
    out_path = ROOT_DIR / output_dir
    pkg_dir = out_path / f"diad_governance_package_{client_slug}"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 01_CLIENT_ONBOARDING_SUMMARY.md
    doc1 = f"""# DIAD Deployment & Onboarding Summary
**Client:** {business_name}  
**GCP Project:** `{project_id}`  
**Region:** `{region}`  
**Platform Version:** DIAD v1.0 Production  

---

## 1. What Was Deployed in Your Google Cloud Account
DIAD runs 100% inside your sovereign Google Cloud environment. Zero customer databases or sales transactions are mirrored to Data for Entrepreneurs servers.

- **Google BigQuery Data Warehouse**:
  - Raw Ingestion: `{project_id}.{client_slug}_raw` (Shopify/WooCommerce orders, products, customers)
  - Staging Views: `{project_id}.{client_slug}_staging` (Cleaned & deduplicated records)
  - Gold Marts: `{project_id}.{client_slug}_gold` (Canonical dimensions, `customer_360`, `rfm_segments`)
- **Serverless Software Engine (Google Cloud Run)**:
  - Internal BI Advisor: Private authenticated service for executive Text-to-SQL analytics.
  - Storefront Chatbot: Fast customer assistance service for order tracking and product recommendations.
- **Automated Hourly/Daily Pipelines (Cloud Scheduler)**:
  - Daily incremental document synchronization to Pinecone vector database.
  - Scheduled dbt transformation runs to keep customer segments up to date.

---

## 2. Storefront Chatbot Widget Integration
To display your floating AI assistant on your storefront, paste this single line before the closing `</body>` tag of your Shopify or WooCommerce theme:

```html
<script src="https://diad-chatbot-external-{project_id}.a.run.app/external_chatbot.js"></script>
```

---

## 3. Support & Maintenance
DIAD is provided as a **Free Product** with best-effort founder guidance. In the event DIAD ever introduces paid subscription tiers in the future, you are guaranteed **at least 30 days advance written notice**. Your BigQuery data and dbt models remain 100% yours forever.
"""

    # 2. 02_SECURITY_AND_ZERO_CUSTODY_BRIEF.md
    doc2 = f"""# DIAD Security & Zero-Custody Brief
**Client:** {business_name}  
**Classification:** Enterprise Security Architecture  

---

## 1. The Zero-Custody Guarantee
Data for Entrepreneurs operates on a strict **Zero-Custody Architecture**:
- All raw order data, customer contact info, financial metrics, and dbt models remain **100% inside your private Google Cloud project** (`{project_id}`).
- D4E maintains zero centralized databases and never takes custody of your customer records.
- Service account permissions (`diad-cloud-run-sa`) follow the strict **Principle of Least Privilege** (BigQuery job runner, Secret Manager accessor). DIAD is never granted project owner or administrator rights.

---

## 2. The 10 Enterprise Security Principles
1. **Physical Storage**: 100% inside your Google Cloud project in `{region}`.
2. **Zero Centralized Storage**: D4E never copies or mirrors your transactions.
3. **Infrastructure Ownership**: You own the cloud project, billing, IAM, and KMS keys.
4. **No Backdoor Access**: Keys are generated locally with least-privilege roles, revocable anytime in GCP Console.
5. **No AI Training**: Ephemeral inference connects exclusively to enterprise Zero Data Retention (ZDR) endpoints (OpenAI / Google Gemini). Your data is never used to train foundational AI models.
6. **Automated PII Redaction**: Emails, phone numbers, and street addresses are automatically masked before any prompt context leaves BigQuery.
7. **Transparent Subprocessors**: Vetted enterprise providers only (GCP, OpenAI, Pinecone, Cloudflare).
8. **Cancellation Guarantee**: Transformed tables and models stay with you forever. Zero vendor lock-in.
9. **Singapore PDPA 2012 Compliance**: Enforces Protection and Transfer Limitation obligations.
10. **Signed Container Releases**: Software is distributed as sealed, cryptographically signed Docker images.
"""

    # 3. 03_RECOMMENDED_CLOUD_BUDGET_GUIDE.md
    doc3 = f"""# DIAD Cloud Cost & Recommended Budget Guide
**Client:** {business_name}  
**GCP Project:** `{project_id}`  

---

## 1. Transparent Self-Hosted Cost Structure
Because DIAD runs on serverless Google Cloud primitives with automatic scale-to-zero capabilities, infrastructure costs are minimal:

| Service | Usage Profile | Typical Monthly Cost |
| :--- | :--- | :--- |
| **Google Cloud Run** | Internal BI queries + Storefront customer chat (with min-instances=0) | **S$8 – S$15 / mo** (Free tier: 2M reqs/mo) |
| **Google BigQuery** | Storage of sales records + daily dbt transformations (with 1 GB query cap) | **S$3 – S$8 / mo** (10 GB storage & 1 TB queries free) |
| **Secret Manager & Scheduler** | 6 secrets + 4 daily/hourly automated cron jobs | **< S$1.00 / mo** |
| **AI Inference (OpenAI / Gemini)** | ~5,000 storefront interactions + daily executive BI summaries | **S$10 – S$35 / mo** (Billed directly to your AI account) |
| **Total Estimated Cloud Bill** | Full production deployment | **~S$25 – S$60 / month** |

---

## 2. Recommended Project Budget Brackets by Store Sizing
You can establish a project-scoped budget alert in your Google Cloud Console to ensure complete peace of mind. Project-scoped budgets **only monitor `{project_id}`** and will never restrict or impact other corporate cloud projects in your billing account:

| Store Volume | Monthly Orders | Web Visits | Recommended Budget Cap | Warning Thresholds |
| :--- | :--- | :--- | :--- | :--- |
| **Boutique Tier** | < 1,000 orders/mo | < 30k visits/mo | **S$25 – S$35 / month** | 50% (S$15), 80% (S$25), 100% (S$35) |
| **Growth Retail (Recommended)** | 1,000 – 10,000 orders/mo | 30k – 150k visits/mo | **S$50 – S$80 / month** | 50% (S$30), 80% (S$50), 100% (S$80) |
| **Scaling Omnichannel** | 10,000 – 50,000+ orders/mo | 150k – 500k+ visits/mo | **S$100 – S$150 / month** | 50% (S$60), 80% (S$100), 100% (S$150) |

---

## 3. How to Confirm Your Budget in 3 Clicks (GCP Console)
1. Open this direct link in your browser:  
   `https://console.cloud.google.com/billing/budgets?project={project_id}`
2. Click **Create Budget**:
   - Scope: Projects -> Select only `{project_id}`
   - Amount: Enter your chosen bracket amount (e.g. `50 SGD`)
   - Actions: Check **Email billing admins and users**
3. Click **Finish**.
"""

    # 4. 04_DIAD_FREE_PRODUCT_TERMS.md
    doc4 = f"""# DIAD Free Pilot Terms & 30-Day Notice Guarantee
**Client:** {business_name}  

---

## 1. Free Software License
DIAD is provided as a **Free Product (S$0 Software Fee)**. Client may deploy, execute, and utilize DIAD within its internal business operations without software licensing fees.

## 2. Consideration: Logo Exchange
In consideration for free access to DIAD software, canonical dbt models, and onboarding technical guidance, Client grants Vendor a non-exclusive, worldwide, royalty-free license to display Client’s commercial trade name, trademark, and brand logo on [`d4e.ai`](https://d4e.ai) and marketing materials as an official pilot partner.

## 3. Best-Effort Support (No SLA Liabilities)
Support is provided on a founder **best-effort basis**. Software is provided on an "as-is" self-hosted basis without strict SLA response time penalties or ongoing support obligations.

## 4. The 30-Day Commercial Notice Guarantee
If Vendor ever introduces paid commercial tiers or changes pricing in the future, Vendor explicitly guarantees **at least thirty (30) days advance written email notice** to Client before any commercial change takes effect.

## 5. Permanent Data Retention (Zero Vendor Lock-In)
If Client elects not to subscribe to future paid tiers upon receiving notice, Client permanently retains 100% of all transformed BigQuery datasets, sales records, customer metrics, and dbt models inside Client's Google Cloud account forever.
"""

    # 5. 05_THIRD_PARTY_SUBPROCESSOR_REGISTER.md
    doc5 = f"""# DIAD Third-Party Subprocessor Register
**Client:** {business_name}  
**Classification:** Institutional Data Protection Register  

---

| Subprocessor | Headquarters | Service Description | Nature of Data Transferred | Processing Location | Certifications & Safeguards |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Google Cloud Platform (GCP)** | Mountain View, CA, USA | Cloud Run, BigQuery, Secret Manager, Cloud Storage | Raw e-commerce orders, customer analytics, dbt gold marts | Client Selected Region (Default: `{region}`) | ISO 27001, SOC 2/3, PCI-DSS Level 1, MTCS Level 3 |
| **OpenAI, LLC** | San Francisco, CA, USA | LLM Inference (Text-to-SQL, Storefront AI Assistant) | Ephemeral query prompts with PII masked | United States (Enterprise ZDR Tier) | Zero Data Retention (ZDR), SOC 2 Type II, TLS 1.3 |
| **Google Cloud (Gemini API)** | Mountain View, CA, USA | Vertex AI / Gemini LLM Fallback & Embeddings | Ephemeral context prompts | Global / Singapore (`{region}`) | SOC 2 Type II, ISO 27001, HIPAA Compliant, TLS 1.3 |
| **Pinecone Systems, Inc.** | New York, NY, USA | Managed Vector Database for Knowledge Base RAG | Vector embeddings of indexed documents (chunks) | AWS / GCP Singapore (`{region}`) | SOC 2 Type II, HIPAA, Encryption at rest (AES-256) |
| **Cloudflare, Inc.** | San Francisco, CA, USA | Web Application Firewall (WAF), CDN & Edge Proxy | Ephemeral web traffic metadata | Global Anycast Edge Network | ISO 27001, SOC 2 Type II, DDoS Mitigation |

---

## Subprocessor Change Notification Commitment
Vendor provides at least thirty (30) days advance written email notice to administrative contacts prior to engaging any new subprocessor.
"""

    files = [
        ("01_CLIENT_ONBOARDING_SUMMARY.md", doc1),
        ("02_SECURITY_AND_ZERO_CUSTODY_BRIEF.md", doc2),
        ("03_RECOMMENDED_CLOUD_BUDGET_GUIDE.md", doc3),
        ("04_DIAD_FREE_PRODUCT_TERMS.md", doc4),
        ("05_THIRD_PARTY_SUBPROCESSOR_REGISTER.md", doc5),
    ]

    for fname, content in files:
        fpath = pkg_dir / fname
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Created: {fpath}")

    # Create ZIP
    zip_path = out_path / f"diad_governance_package_{client_slug}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, _ in files:
            zf.write(pkg_dir / fname, arcname=f"diad_governance_{client_slug}/{fname}")
    
    print(f"\n[SUCCESS] Packaged complete governance kit: {zip_path} ({zip_path.stat().st_size} bytes)")
    return zip_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Client Governance Package")
    parser.add_argument("--client", default=None, help="Client slug (e.g. acme, mybrand). Defaults to configured business.")
    parser.add_argument("--output", default="dist_release", help="Output directory")
    args = parser.parse_args()
    generate_package(client_slug=args.client, output_dir=args.output)
