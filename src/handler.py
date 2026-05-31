import json
import boto3
import hashlib
import os
import time
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])
BASE_URL = os.environ.get("BASE_URL", "https://your-api-id.execute-api.eu-west-1.amazonaws.com/prod")


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _short_code(url: str) -> str:
    """Generate a 7-char alphanumeric code from the URL + current timestamp."""
    raw = f"{url}{time.time()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:7]


# ── POST /shorten ──────────────────────────────────────────────────────────────
def create_short_url(event, _context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON body"})

    original_url = body.get("url", "").strip()
    if not original_url or not original_url.startswith(("http://", "https://")):
        return _response(400, {"error": "Provide a valid URL starting with http:// or https://"})

    ttl_days = int(body.get("ttl_days", 30))
    expiry_ts = int(time.time()) + ttl_days * 86400

    code = _short_code(original_url)
    item = {
        "short_code": code,
        "original_url": original_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "click_count": 0,
        "ttl": expiry_ts,
    }
    table.put_item(Item=item)

    return _response(201, {
        "short_url": f"{BASE_URL}/r/{code}",
        "short_code": code,
        "original_url": original_url,
        "expires_in_days": ttl_days,
    })


# ── GET /r/{code} ─────────────────────────────────────────────────────────────
def redirect(event, _context):
    code = (event.get("pathParameters") or {}).get("code", "")
    if not code:
        return _response(400, {"error": "Missing short code"})

    result = table.get_item(Key={"short_code": code})
    item = result.get("Item")

    if not item:
        return _response(404, {"error": "Short URL not found or expired"})

    # Increment click counter atomically
    table.update_item(
        Key={"short_code": code},
        UpdateExpression="SET click_count = click_count + :inc",
        ExpressionAttributeValues={":inc": 1},
    )

    return {
        "statusCode": 301,
        "headers": {
            "Location": item["original_url"],
            "Cache-Control": "no-cache",
        },
        "body": "",
    }


# ── GET /stats/{code} ─────────────────────────────────────────────────────────
def get_stats(event, _context):
    code = (event.get("pathParameters") or {}).get("code", "")
    if not code:
        return _response(400, {"error": "Missing short code"})

    result = table.get_item(Key={"short_code": code})
    item = result.get("Item")

    if not item:
        return _response(404, {"error": "Short URL not found"})

    return _response(200, {
        "short_code": code,
        "original_url": item["original_url"],
        "short_url": f"{BASE_URL}/r/{code}",
        "click_count": int(item.get("click_count", 0)),
        "created_at": item["created_at"],
    })


# ── Lambda router ─────────────────────────────────────────────────────────────
def lambda_handler(event, context):
    http_method = event.get("httpMethod", "")
    path = event.get("path", "")

    if http_method == "POST" and path == "/shorten":
        return create_short_url(event, context)
    elif http_method == "GET" and path.startswith("/r/"):
        return redirect(event, context)
    elif http_method == "GET" and path.startswith("/stats/"):
        return get_stats(event, context)
    else:
        return _response(404, {"error": "Route not found"})
