import base64
import json
import os
from decimal import Decimal
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from mangum import Mangum

app = FastAPI(title="inboXray API")

API_KEY = os.environ.get("API_KEY", "")


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    # /health is exempt so monitoring can probe without credentials
    if request.url.path != "/health" and API_KEY:
        if request.headers.get("x-api-key") != API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)

dynamodb = boto3.resource(
    "dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1")
)

ANALYSIS_TABLE = os.environ["ANALYSIS_RESULTS_TABLE"]
BLOCKLIST_TABLE = os.environ["BLOCKLIST_TABLE"]

analysis_table = dynamodb.Table(ANALYSIS_TABLE)
blocklist_table = dynamodb.Table(BLOCKLIST_TABLE)


def _to_json(item):
    # DynamoDB returns Decimal — convert to float for JSON serialization
    if isinstance(item, dict):
        return {k: _to_json(v) for k, v in item.items()}
    if isinstance(item, list):
        return [_to_json(v) for v in item]
    if isinstance(item, Decimal):
        return float(item)
    return item


def _encode_cursor(key: dict) -> str:
    # LastEvaluatedKey may contain Decimal (DynamoDB numeric type) — convert first
    return (
        base64.urlsafe_b64encode(json.dumps(_to_json(key)).encode())
        .rstrip(b"=")
        .decode()
    )


def _from_json(item):
    # JSON numbers become float — DynamoDB requires Decimal for numeric types
    if isinstance(item, dict):
        return {k: _from_json(v) for k, v in item.items()}
    if isinstance(item, list):
        return [_from_json(v) for v in item]
    if isinstance(item, float):
        return Decimal(str(item))
    return item


def _decode_cursor(cursor: str) -> dict:
    # re-add stripped padding — (4 - n%4)%4 gives 0 when already aligned
    padding = (4 - len(cursor) % 4) % 4
    return _from_json(json.loads(base64.urlsafe_b64decode(cursor + "=" * padding)))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/analysis")
def list_analysis(
    threat_level: Optional[str] = Query(None, description="HIGH | MEDIUM | LOW"),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(
        None, description="pagination cursor from previous response"
    ),
):
    kwargs = {"Limit": limit}
    if cursor:
        kwargs["ExclusiveStartKey"] = _decode_cursor(cursor)

    if threat_level:
        # query ThreatLevelIndex — O(n) for matching threat level, no full scan needed
        resp = analysis_table.query(
            IndexName="ThreatLevelIndex",
            KeyConditionExpression=Key("threat_level").eq(threat_level.upper()),
            ScanIndexForward=False,  # newest first
            **kwargs,
        )
    else:
        resp = analysis_table.scan(**kwargs)

    items = _to_json(resp.get("Items", []))
    result = {"items": items, "count": len(items)}
    if "LastEvaluatedKey" in resp:
        result["next_cursor"] = _encode_cursor(resp["LastEvaluatedKey"])
    return result


@app.get("/analysis/{message_id}")
def get_analysis(message_id: str):
    resp = analysis_table.query(
        KeyConditionExpression=Key("message_id").eq(message_id),
        Limit=1,
    )
    items = resp.get("Items", [])
    if not items:
        raise HTTPException(status_code=404, detail="not found")
    return _to_json(items[0])


@app.get("/stats")
def stats():
    counts = {}
    for level in ("HIGH", "MEDIUM", "LOW"):
        resp = analysis_table.query(
            IndexName="ThreatLevelIndex",
            KeyConditionExpression=Key("threat_level").eq(level),
            Select="COUNT",
        )
        counts[level] = resp["Count"]
    return {"threat_counts": counts, "total": sum(counts.values())}


@app.post("/blocklist", status_code=201)
def add_to_blocklist(body: dict):
    sender = body.get("sender", "").strip()
    if not sender:
        raise HTTPException(status_code=400, detail="sender is required")
    blocklist_table.put_item(Item={"sender": sender})
    return {"sender": sender}


@app.delete("/blocklist/{sender}", status_code=204)
def remove_from_blocklist(sender: str):
    blocklist_table.delete_item(Key={"sender": sender})
    return Response(status_code=204)


handler = Mangum(app, lifespan="off")
