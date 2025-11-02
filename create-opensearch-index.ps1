# PowerShell script to create OpenSearch index for Amazon Connect Email AI Response Routing
# Run this script after deploying the OpenSearchStack

Write-Host "Creating OpenSearch index for Bedrock Knowledge Base..." -ForegroundColor Green

# Read AWS region from .env file
$AWS_REGION = (Get-Content .env | Where-Object { $_ -match '^AWS_REGION=' }) -replace 'AWS_REGION=', ''

# Get collection ID and dynamic index name from stack outputs
Write-Host "Getting collection ID from CloudFormation stack..." -ForegroundColor Yellow
$COLLECTION_ID = aws cloudformation describe-stacks --stack-name OpenSearchStack --region $AWS_REGION --query "Stacks[0].Outputs[?OutputKey=='VectorCollectionId'].OutputValue" --output text
$INDEX_NAME = "kb-email-ai-acemailaisandbox-index"

if (-not $COLLECTION_ID) {
    Write-Error "Failed to get collection ID. Make sure OpenSearchStack is deployed successfully."
    exit 1
}

Write-Host "Collection ID: $COLLECTION_ID" -ForegroundColor Cyan

# Create schema file
Write-Host "Creating index schema file..." -ForegroundColor Yellow
@'
{
  "id": "",
  "indexName": "kb-email-ai-acemailaisandbox-index",
  "indexSchema": {
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
  }
}
'@ | Out-File -FilePath "index-schema.json" -Encoding utf8

# Update the ID in the file
Write-Host "Updating collection ID in schema file..." -ForegroundColor Yellow
$content = Get-Content "index-schema.json" -Raw
$content = $content -replace '"id": ""', ('"id": "' + $COLLECTION_ID + '"')
$content | Set-Content "index-schema.json"

# Create index
Write-Host "Creating OpenSearch index..." -ForegroundColor Yellow
try {
    aws opensearchserverless create-index --cli-input-json file://index-schema.json --region $AWS_REGION
    Write-Host "Index created successfully!" -ForegroundColor Green
} catch {
    Write-Error "Failed to create index: $_"
    exit 1
}

# Clean up the temporary file 
Write-Host "Cleaning up temporary files..." -ForegroundColor Yellow
Remove-Item "index-schema.json"

Write-Host "OpenSearch index creation completed successfully!" -ForegroundColor Green
Write-Host "You can now proceed with deploying the main stack: cdk deploy ACEmailAISandbox" -ForegroundColor Cyan