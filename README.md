# Serverless URL Shortener

**Live demo:** https://73si4d4qbc.execute-api.eu-west-1.amazonaws.com/Prod

[![CI/CD](https://github.com/nexusites/aws-url-shortener/actions/workflows/ci.yml/badge.svg)](https://github.com/nexusites/aws-url-shortener/actions/workflows/ci.yml)
![AWS Free Tier](https://img.shields.io/badge/AWS-Free%20Tier-orange?logo=amazon-aws)
![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)

A production-ready URL shortener built entirely on AWS serverless services. Zero fixed infrastructure cost, runs 100% within the AWS Free Tier.

## Architecture

​```mermaid
graph LR
    Client -->|POST /shorten| APIGW[API Gateway]
    Client -->|GET /r/code| APIGW
    Client -->|GET /stats/code| APIGW
    APIGW --> Lambda[Lambda Python 3.12]
    Lambda -->|Read / Write| DDB[(DynamoDB On-Demand)]
    Lambda -->|Metrics and Logs| CW[CloudWatch]
​```

| Component     | Service              | Free Tier limit                 |
|---------------|----------------------|---------------------------------|
| API           | API Gateway          | 1M calls/month                  |
| Compute       | Lambda               | 1M invocations/month            |
| Database      | DynamoDB On-Demand   | 25 WCU, 25 RCU, 25 GB storage   |
| Observability | CloudWatch           | 10 custom metrics, 5 GB logs    |

## API Reference

### POST /shorten
Shorten a URL.

Request body:
​```json
{ "url": "https://example.com/long/path", "ttl_days": 30 }
​```

Response 201:
​```json
{
  "short_url": "https://73si4d4qbc.execute-api.eu-west-1.amazonaws.com/Prod/r/a3f9c12",
  "short_code": "a3f9c12",
  "original_url": "https://example.com/long/path",
  "expires_in_days": 30
}
​```

### GET /r/{code}
Redirects to the original URL (301).

### GET /stats/{code}
Returns click statistics.

## Deploy

​```bash
git clone https://github.com/nexusites/aws-url-shortener.git
cd aws-url-shortener
sam build --template infrastructure/template.yaml
sam deploy --guided
​```

## Key Design Decisions

- Single Lambda function with internal routing keeps cold starts minimal.
- DynamoDB TTL automatically expires old links at zero cost.
- On-Demand billing means no capacity planning and stays within free tier.
- Runtime base URL is built from the request context, so the same code works across stages.

## AWS Services Used

API Gateway, Lambda, DynamoDB, CloudWatch, IAM, SAM

## Author

Riccardo Lotronto - https://github.com/nexusites