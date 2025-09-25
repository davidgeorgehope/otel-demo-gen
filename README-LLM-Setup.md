# LLM Provider Setup Guide

The OTEL Demo Generator now uses **Amazon Bedrock** exclusively for LLM-powered configuration and scenario generation. Follow the steps below to configure the required credentials and verify your setup.

## 1. Prepare Environment Variables

1. Copy the example environment file and update it with your Bedrock credentials:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` (or your deployment manifest) with the following values:
   ```env
   LLM_PROVIDER=bedrock
   AWS_ACCESS_KEY_ID=your-aws-access-key
   AWS_SECRET_ACCESS_KEY=your-aws-secret-key
   AWS_REGION=us-east-1
   BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
   ```

   - `AWS_REGION` must be a region where Amazon Bedrock is available (for example `us-east-1`, `us-west-2`, or `eu-central-1`).
   - `BEDROCK_MODEL_ID` can be any supported Anthropic Claude model. The defaults above target Claude 3.5 Sonnet.

## 2. Grant IAM Permissions

The AWS credentials you supply must have permission to invoke your chosen model:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "*"
    }
  ]
}
```

Attach this policy (or an equivalent, more restrictive version) to the IAM user or role whose keys you are using.

## 3. Start the Backend and Verify

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Check that the backend can read your Bedrock configuration:

```bash
curl http://localhost:8000/llm-config
```

A healthy response looks like:

```json
{
  "provider": "bedrock",
  "configured": true,
  "model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
  "details": {
    "aws_access_key_set": true,
    "aws_secret_key_set": true,
    "aws_region": "us-east-1",
    "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0"
  }
}
```

## 4. Test Config Generation

```bash
curl -X POST http://localhost:8000/generate-config \
  -H "Content-Type: application/json" \
  -d '{"description": "Simple web app with frontend, backend, and database"}'
```

The response should return a job identifier. Poll the job endpoint until status becomes `succeeded`:

```bash
curl http://localhost:8000/generate-config/<job_id>
```

## 5. Operating Without Bedrock

If you do not provide Bedrock credentials, you can still:
- Load the sample configuration via the UI.
- Call `GET /test-config` to retrieve a predefined scenario.
- Manually craft configurations and submit them to `/start`.

## 6. Troubleshooting

- **`Unsupported LLM provider` error** – Ensure `LLM_PROVIDER=bedrock` everywhere (local env, Kubernetes secrets, Helm values, etc.).
- **`AWS credentials not found` error** – Confirm both `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are present.
- **`AccessDeniedException` from Bedrock** – Verify the IAM user/role has the `bedrock:InvokeModel` permission and that Bedrock is enabled in the selected region.
- **Schema validation failures** – The backend now retries with validation feedback, but you can inspect `last_error` fields from `/generate-config/<job_id>` for details.

## 7. Cost Awareness

Amazon Bedrock usage is billed per token. Claude 3.5 Sonnet typically costs about **$0.003** per 1K output tokens (subject to region and current pricing). Monitor your AWS usage to avoid surprises.

With these steps complete, the OTEL Demo Generator will use Amazon Bedrock for reliable JSON generation and scenario creation.
