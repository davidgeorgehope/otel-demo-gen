# LLM Provider Setup Guide

The OTEL Demo Generator supports multiple LLM providers for generating telemetry configurations. You can choose between OpenAI and Amazon Bedrock.

## Environment Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit the `.env` file with your preferred LLM provider configuration.

## Option 1: OpenAI Configuration

Set the following environment variables in your `.env` file:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_MODEL=gpt-4o-mini
```

**Getting OpenAI API Key:**
1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in
3. Navigate to API Keys section
4. Create a new secret key

**Supported Models:**
- `gpt-4o-mini` (default, cost-effective)
- `gpt-4o`
- `gpt-4-turbo`
- `gpt-3.5-turbo`

## Option 2: Amazon Bedrock Configuration

Set the following environment variables in your `.env` file:

```env
LLM_PROVIDER=bedrock
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

**Getting AWS Credentials:**
1. Log in to [AWS Console](https://console.aws.amazon.com/)
2. Go to IAM → Users
3. Create or select a user
4. Generate access keys with Bedrock permissions

**Required IAM Permissions:**
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

**Supported Claude Models:**
- `anthropic.claude-3-5-sonnet-20241022-v2:0` (default, latest)
- `anthropic.claude-3-5-sonnet-20240620-v1:0`
- `anthropic.claude-3-haiku-20240307-v1:0`

## Testing Configuration

After setting up your `.env` file:

1. Start the backend:
```bash
cd backend
uvicorn main:app --reload --port 8000
```

2. Check LLM configuration status:
```bash
curl http://localhost:8000/llm-config
```

3. Test config generation:
```bash
curl -X POST http://localhost:8000/generate-config \
  -H "Content-Type: application/json" \
  -d '{"description": "Simple web app with frontend, backend, and database"}'
```

## No LLM Provider Mode

If no LLM provider is configured, you can still:
- Use the "Load Test Config" button in the UI
- Access the test config endpoint: `GET /test-config`
- Start telemetry generation with pre-built configurations

## Troubleshooting

### OpenAI Issues
- **401 Unauthorized**: Check your API key
- **429 Too Many Requests**: You've hit rate limits
- **Model not found**: Verify the model name

### Bedrock Issues
- **Access Denied**: Check IAM permissions
- **Region not supported**: Verify Bedrock is available in your region
- **Model not found**: Ensure the model ID is correct

### General Issues
- **Backend won't start**: Check all environment variables are set correctly
- **Config generation fails**: Verify LLM provider status in the UI

## Cost Considerations

### OpenAI Pricing (approximate)
- GPT-4o-mini: ~$0.00015 per generation
- GPT-4o: ~$0.01 per generation

### Bedrock Pricing (approximate)
- Claude 3.5 Sonnet: ~$0.003 per generation
- Claude 3 Haiku: ~$0.00025 per generation

Prices vary by input/output token count and may change. Check official pricing pages for current rates.
