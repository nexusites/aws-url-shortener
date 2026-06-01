import json
import boto3
import hashlib
import os
import time
from datetime import datetime, timezone

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])


def _base_url(event):
    ctx = event.get("requestContext", {}) or {}
    headers = event.get("headers", {}) or {}
    domain = ctx.get("domainName") or headers.get("Host") or headers.get("host", "")
    stage = ctx.get("stage", "Prod")
    if domain:
        return f"https://{domain}/{stage}"
    return os.environ.get("BASE_URL", "")


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }


def _short_code(url):
    raw = f"{url}{time.time()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:7]


def landing_page(event, _context):
    base = _base_url(event)
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Serverless URL Shortener</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0d1117; color: #e6edf3; line-height: 1.6; padding: 2rem 1rem; }
  .wrap { max-width: 760px; margin: 0 auto; }
  .badge { display: inline-block; background: #1f6feb22; color: #58a6ff;
    font-size: 13px; padding: 4px 12px; border-radius: 20px; margin-bottom: 16px; }
  h1 { font-size: 2rem; font-weight: 600; margin-bottom: 8px; }
  .sub { color: #8b949e; font-size: 1.05rem; margin-bottom: 32px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px;
    padding: 20px 24px; margin-bottom: 16px; }
  .method { display: inline-block; font-family: monospace; font-size: 13px; font-weight: 600;
    padding: 2px 10px; border-radius: 6px; margin-right: 8px; }
  .post { background: #238636; color: #fff; }
  .get { background: #1f6feb; color: #fff; }
  .path { font-family: monospace; font-size: 15px; color: #e6edf3; }
  .desc { color: #8b949e; font-size: 14px; margin-top: 8px; }
  pre { background: #0d1117; border: 1px solid #30363d; border-radius: 8px;
    padding: 12px 16px; overflow-x: auto; font-size: 13px; margin-top: 12px; color: #79c0ff; }
  .stack { display: flex; flex-wrap: wrap; gap: 8px; margin: 24px 0; }
  .chip { background: #21262d; border: 1px solid #30363d; color: #c9d1d9;
    font-size: 13px; font-family: monospace; padding: 4px 12px; border-radius: 6px; }
  footer { color: #8b949e; font-size: 14px; margin-top: 32px; text-align: center; }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
</style>
</head>
<body>
<div class="wrap">
  <span class="badge">Live on AWS &middot; Serverless</span>
  <h1>URL Shortener API</h1>
  <p class="sub">A production-ready URL shortener built entirely on AWS serverless services. Runs 100% within the AWS Free Tier.</p>
  <div class="stack">
    <span class="chip">API Gateway</span>
    <span class="chip">Lambda</span>
    <span class="chip">DynamoDB</span>
    <span class="chip">CloudWatch</span>
    <span class="chip">Python 3.12</span>
  </div>
  <div class="card">
    <span class="method post">POST</span><span class="path">/shorten</span>
    <p class="desc">Create a short link from a long URL.</p>
    <pre>curl -X POST __BASE__/shorten \\
  -H "Content-Type: application/json" \\
  -d '{"url": "https://example.com"}'</pre>
  </div>
  <div class="card">
    <span class="method get">GET</span><span class="path">/r/{code}</span>
    <p class="desc">Redirects (301) to the original URL and counts the click.</p>
  </div>
  <div class="card">
    <span class="method get">GET</span><span class="path">/stats/{code}</span>
    <p class="desc">Returns click statistics for a short link.</p>
    <pre>curl __BASE__/stats/abc1234</pre>
  </div>
  <footer>
    Built by Riccardo Lotronto &middot;
    <a href="https://github.com/nexusites/aws-url-shortener">View source on GitHub</a>
  </footer>
</div>
</body>
</html>"""
    html = html.replace("__BASE__", base)
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": html,
    }


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
    base = _base_url(event)
    return _response(201, {
        "short_url": f"{base}/r/{code}",
        "short_code": code,
        "original_url": original_url,
        "expires_in_days": ttl_days,
    })


def redirect(event, _context):
    code = (event.get("pathParameters") or {}).get("code", "")
    if not code:
        return _response(400, {"error": "Missing short code"})
    result = table.get_item(Key={"short_code": code})
    item = result.get("Item")
    if not item:
        return _response(404, {"error": "Short URL not found or expired"})
    table.update_item(
        Key={"short_code": code},
        UpdateExpression="SET click_count = click_count + :inc",
        ExpressionAttributeValues={":inc": 1},
    )
    return {
        "statusCode": 301,
        "headers": {"Location": item["original_url"], "Cache-Control": "no-cache"},
        "body": "",
    }


def get_stats(event, _context):
    code = (event.get("pathParameters") or {}).get("code", "")
    if not code:
        return _response(400, {"error": "Missing short code"})
    result = table.get_item(Key={"short_code": code})
    item = result.get("Item")
    if not item:
        return _response(404, {"error": "Short URL not found"})
    base = _base_url(event)
    return _response(200, {
        "short_code": code,
        "original_url": item["original_url"],
        "short_url": f"{base}/r/{code}",
        "click_count": int(item.get("click_count", 0)),
        "created_at": item["created_at"],
    })


def lambda_handler(event, context):
    http_method = event.get("httpMethod", "")
    path = event.get("path", "")
    if http_method == "GET" and path == "/":
        return landing_page(event, context)
    elif http_method == "POST" and path == "/shorten":
        return create_short_url(event, context)
    elif http_method == "GET" and path.startswith("/r/"):
        return redirect(event, context)
    elif http_method == "GET" and path.startswith("/stats/"):
        return get_stats(event, context)
    else:
        return _response(404, {"error": "Route not found"})