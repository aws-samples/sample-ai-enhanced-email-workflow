# Combined cleanup script for ACEmailAI deployment
Write-Host "Starting ACEmailAI cleanup process..."

# Load environment variables from .env file
$AWS_REGION = $null
$AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN = $null

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^AWS_REGION=(.*)$") {
            $AWS_REGION = $matches[1]
        }
        if ($_ -match "^AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN=(.*)$") {
            $AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN = $matches[1]
        }
    }
    
    if (-not $AWS_REGION) {
        Write-Host "Warning: AWS_REGION not found in .env file, using default region"
        $AWS_REGION = "us-east-1"
    }
    
    if (-not $AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN) {
        Write-Host "Warning: AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN not found in .env file"
    }
} else {
    Write-Host "Warning: .env file not found, using default region us-east-1"
    $AWS_REGION = "us-east-1"
}

Write-Host "Using AWS region: $AWS_REGION"

# 1. Delete log groups that are causing conflicts
Write-Host ""
Write-Host "=== Cleaning up conflicting log groups ==="
try {
    aws logs delete-log-group --log-group-name "/aws/lambda/ACEmailAI-QueryTempoStorage4AsyncMode" --region $AWS_REGION 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Deleted log group: QueryTempoStorage4AsyncMode"
    } else {
        Write-Host "Log group QueryTempoStorage4AsyncMode not found or already deleted"
    }
} catch {
    Write-Host "Log group QueryTempoStorage4AsyncMode not found or already deleted"
}

try {
    aws logs delete-log-group --log-group-name "/aws/lambda/ACEmailAI-EmailAIResponseRouting" --region $AWS_REGION 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Deleted log group: EmailAIResponseRouting"
    } else {
        Write-Host "Log group EmailAIResponseRouting not found or already deleted"
    }
} catch {
    Write-Host "Log group EmailAIResponseRouting not found or already deleted"
}

Write-Host "Log group cleanup complete!"

# 2. Clean up customer profiles
if ($AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN) {
    Write-Host ""
    Write-Host "=== Cleaning up customer profiles ==="
    
    # Account numbers from customerprofiles.csv
    $ACCOUNT_NUMBERS = @("9715398723", "1273421047")
    
    foreach ($account_number in $ACCOUNT_NUMBERS) {
        Write-Host "Processing account: $account_number"
        
        # Search for profile
        try {
            $searchResult = aws customer-profiles search-profiles --domain-name $AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN --key-name "_account" --values $account_number --region $AWS_REGION --query 'Items[0].ProfileId' --output text 2>$null
            
            if ($searchResult -and $searchResult -ne "None") {
                Write-Host "Found profile ID: $searchResult"
                
                # Delete profile
                aws customer-profiles delete-profile --domain-name $AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN --profile-id $searchResult --region $AWS_REGION 2>$null
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Successfully deleted profile for account: $account_number"
                } else {
                    Write-Host "Failed to delete profile for account: $account_number"
                }
            } else {
                Write-Host "No profile found for account: $account_number"
            }
        } catch {
            Write-Host "Error processing account: $account_number"
        }
        
        Write-Host ""
    }
    
    Write-Host "Customer profile cleanup completed!"
} else {
    Write-Host ""
    Write-Host "=== Skipping customer profile cleanup ==="
    Write-Host "AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN not configured in .env file"
}

Write-Host ""
Write-Host "=== Cleanup process completed ==="