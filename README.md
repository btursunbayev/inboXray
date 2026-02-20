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

Lambda processes batches of up to 10 emails concurrently. Each email goes through Bedrock for threat analysis (~1.7s median), then gets forwarded clean, prepended with a `[SUSPICIOUS]` warning, or blocked entirely depending on threat level. Everything goes into DynamoDB for the audit log.

Benchmark (10 emails, batch_size=10):
- Bedrock P50: 1136ms, P95: 2805ms
- End-to-end P50: 1737ms, P95: 3289ms
- Concurrent batch wall-time: ~2.2s vs ~15s sequential


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

## REST API

A read/write API is deployed alongside the pipeline on API Gateway (HTTP API v2) + Lambda.

**Base URL:** `https://4zoeqko6dk.execute-api.us-east-1.amazonaws.com`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/analysis` | List analysis records (paginated) |
| GET | `/analysis/{message_id}` | Get single record |
| GET | `/stats` | Threat level counts |
| POST | `/blocklist` | Add sender to blocklist |
| DELETE | `/blocklist/{sender}` | Remove sender from blocklist |

**Pagination** — all list endpoints support `?limit=N&cursor=<token>`. The response includes `next_cursor` when more pages exist.

```bash
# list HIGH threat emails, 5 at a time
curl "$BASE/analysis?threat_level=HIGH&limit=5"

# next page
curl "$BASE/analysis?threat_level=HIGH&limit=5&cursor=<next_cursor>"

# aggregate stats
curl "$BASE/stats"
# {"threat_counts": {"HIGH": 14, "MEDIUM": 4, "LOW": 6}, "total": 24}

# add to blocklist
curl -X POST "$BASE/blocklist" \
  -H "Content-Type: application/json" \
  -d '{"sender": "spam@evil.com", "reason": "phishing"}'
```

## Benchmark
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python scripts/benchmark.py --count 10
```

---
Maintained by [**Bekmukhamed Tursunbayev**](https://btursunbayev.com)  
