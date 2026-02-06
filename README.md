# inboXray

## Overview

inboXray is a serverless email proxy built on AWS that intercepts emails, removes tracking pixels, sanitizes malicious content, and forwards clean versions to your private inbox. Create unlimited disposable email aliases while maintaining your privacy.

## Architecture

```
Email → AWS SES → S3 → Lambda → Sanitize → Forward to Clean Inbox
                        ↓
                   DynamoDB (aliases, blocklist)
```
