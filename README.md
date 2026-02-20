# inboXray

Serverless email security system. Emails sent to my domain get analyzed by AI for phishing/malware, then forwarded, flagged, or blocked.

```
Sender
   ↓
SES (yourdomain.com) → S3 (raw storage)
                        ↓
                       SNS
                        ↓
                       SQS (batching, retry, DLQ)
                        ↓
                      Lambda (concurrent batch processing)
                        ↓
            ┌───────────┴──────────┐
  Bedrock (Claude 3 Haiku)  DynamoDB (audit log)
                        ↓
                       SES (forward / warn / block)
```

Lambda processes batches of up to 10 emails concurrently. Each email goes through Bedrock for threat analysis (~1.7s median), then gets forwarded clean, prepended with a `[SUSPICIOUS]` warning, or blocked entirely depending on threat level. Everything goes into DynamoDB for the audit log

## Quick Start

Prerequisites: AWS account, domain with SES set up, Terraform >= 1.0, Python 3.11+

Clone the repository
```bash
git clone https://github.com/btursunbayev/inboXray.git
cd inboXray
```

Configure your domain and email
```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
nano terraform/terraform.tfvars  # Edit with your values
```

Deploy to AWS
```bash
make deploy
```

Emails sent to your domain will be analyzed and forwarded to whatever address you configure in `terraform.tfvars`.

## Benchmark
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python scripts/benchmark.py --count 10
```

---
Maintained by [**Bekmukhamed Tursunbayev**](https://btursunbayev.com)  
