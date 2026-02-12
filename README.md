# inboXray

## Overview

inboXray is a two-phase serverless email security platform built on AWS. 

**Phase 1** intercepts incoming emails, removes tracking pixels and sanitizes links before forwarding clean versions to your inbox in under 500ms.

```
Email
    ↓
AWS SES → S3 → Lambda (sanitize) → Forward clean email
              ↓
         DynamoDB (aliases, blocklist)
```

**Phase 2** optionally performs deep threat analysis using AI agents that visit suspicious URLs in a sandboxed browser, capture evidence, and score threat levels using local LLMs.

```
Lambda detects suspicious email
         ↓
     SQS Queue
         ↓
   Agent Worker (5-Step Analysis)
         ↓
   ┌─────┴─────┬─────────┬──────────┬─────────┐
   1.          2.        3.         4.        5.
Extract     LLM Risk   Browser   LLM Final  Save to
URLs        Check      Visit     Threat    DynamoDB
         (Ollama)  (Playwright)  Score
         
Results: LOW / MEDIUM / HIGH threat level + screenshots
```

The system uses AWS SES to receive emails, stores them temporarily in S3, and triggers Lambda functions for sanitization. For deep analysis, messages flow through SQS to an agent worker that combines LangGraph for orchestration, Ollama for local LLM inference, and Playwright for browser automation. Infrastructure is managed with Terraform. This architecture keeps privacy protection fast (<500ms) while allowing compute-intensive threat analysis to run asynchronously (15-40 seconds).

## Quick Start

### Prerequisites

- AWS account with SES configured
- Domain for receiving emails
- Terraform >= 1.0
- Python 3.11+ (for Phase 2 only)
- Ollama installed (for Phase 2 only)

### Step 1: Deploy Infrastructure

Clone the repository
```bash
git clone https://github.com/yourusername/inboXray.git
cd inboXray
```

Configure your domain and email
```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
nano terraform/terraform.tfvars  # Edit with your values
```

Deploy to AWS
```bash
make terraform-init
make terraform-apply
```

Now emails sent to `anything@inbox.yourdomain.com` will be sanitized and forwarded.

### Step 2: Enable Phase 2

Install Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Download Llama 3.1 model (4.9GB)
```bash
ollama pull llama3.1
```

Start Ollama server (keep running in separate terminal)
```bash
ollama serve
```

Set up Python environment and install worker dependencies
```bash
python -m venv venv
source venv/bin/activate
make worker-install
```

Set environment variables from Terraform outputs
```bash
export AWS_REGION=us-east-1
export ANALYSIS_QUEUE_URL=$(terraform -chdir=terraform output -raw analysis_queue_url)
export ANALYSIS_RESULTS_TABLE=$(terraform -chdir=terraform output -raw analysis_results_table)
export OLLAMA_HOST=http://localhost:11434
```


Enable Phase 2 analysis in Lambda (edit terraform.tfvars: set enable_analysis = true)
```bash
make terraform-apply
```

Start the agent worker
```bash
make worker-run
```

Now suspicious emails will be analyzed automatically.

---
Maintained by [**Bekmukhamed Tursunbayev**](https://btursunbayev.com)  
