#!/bin/bash
# Bash script to create OpenSearch index for Amazon Connect Email AI Response Routing
# Run this script after deploying the OpenSearchStack

echo "Creating OpenSearch index for Bedrock Knowledge Base..."

# Read AWS region from .env file
AWS_REGION=$(grep '^AWS_REGION=' .env | cut -d'=' -f2)

# Set dynamic index name
INDEX_NAME="kb-email-ai-acemailaisandbox-index"

# Get collection ID from stack outputs
echo "Getting collection ID from CloudFormation stack..."
COLLECTION_ID=$(aws cloudformation describe-stacks --stack-name OpenSearchStack --region $AWS_REGION --query "Stacks[0].Outputs[?OutputKey=='VectorCollectionId'].OutputValue" --output text)

if [ -z "$COLLECTION_ID" ]; then
    echo "Error: Failed to get collection ID. Make sure OpenSearchStack is deployed successfully."
    exit 1
fi

echo "Collection ID: $COLLECTION_ID"

# Create index using CreateIndex API
echo "Creating OpenSearch index..."
aws opensearchserverless create-index \
  --id "$COLLECTION_ID" \
  --index-name "$INDEX_NAME" \
  --region $AWS_REGION \
  --index-schema '{
    "settings": {
      "index.knn": true
    },
    "mappings": {
      "properties": {
        "bedrock-knowledge-base-default-vector": {
          "type": "knn_vector",
          "dimension": 1024,
          "method": {
            "name": "hnsw",
            "engine": "faiss"
          }
        },
        "AMAZON_BEDROCK_TEXT_CHUNK": {"type": "text"},
        "AMAZON_BEDROCK_METADATA": {"type": "text"}
      }
    }
  }'

if [ $? -eq 0 ]; then
    echo "Index created successfully!"
    echo "You can now proceed with deploying the main stack: cdk deploy ACEmailAISandbox"
else
    echo "Error: Failed to create index"
    exit 1
fi