#!/bin/bash

# Combined cleanup script for ACEmailAI deployment
echo "Starting ACEmailAI cleanup process..."

# Read AWS region from .env file
if [ -f ".env" ]; then
    AWS_REGION=$(grep "^AWS_REGION=" .env | cut -d'=' -f2)
    AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN=$(grep "^AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN=" .env | cut -d'=' -f2)
    
    if [ -z "$AWS_REGION" ]; then
        echo "Warning: AWS_REGION not found in .env file, using default region"
        AWS_REGION="us-east-1"
    fi
    
    if [ -z "$AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN" ]; then
        echo "Warning: AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN not found in .env file"
    fi
else
    echo "Warning: .env file not found, using default region us-east-1"
    AWS_REGION="us-east-1"
fi

echo "Using AWS region: $AWS_REGION"

# 1. Delete log groups that are causing conflicts
echo ""
echo "=== Cleaning up conflicting log groups ==="
aws logs delete-log-group --log-group-name "/aws/lambda/ACEmailAI-QueryTempoStorage4AsyncMode" --region "$AWS_REGION" 2>/dev/null || echo "Log group QueryTempoStorage4AsyncMode not found or already deleted"
aws logs delete-log-group --log-group-name "/aws/lambda/ACEmailAI-EmailAIResponseRouting" --region "$AWS_REGION" 2>/dev/null || echo "Log group EmailAIResponseRouting not found or already deleted"
echo "Log group cleanup complete!"

# 2. Clean up customer profiles
if [ -n "$AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN" ]; then
    echo ""
    echo "=== Cleaning up customer profiles ==="
    
    # Account numbers from customerprofiles.csv
    ACCOUNT_NUMBERS=("9715398723" "1273421047")
    
    for account_number in "${ACCOUNT_NUMBERS[@]}"; do
        echo "Processing account: $account_number"
        
        # Search for profile
        search_result=$(aws customer-profiles search-profiles --domain-name "$AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN" --key-name "_account" --values "$account_number" --region "$AWS_REGION" --query 'Items[0].ProfileId' --output text 2>/dev/null)
        
        if [ "$search_result" != "None" ] && [ -n "$search_result" ]; then
            echo "Found profile ID: $search_result"
            
            # Delete profile
            if aws customer-profiles delete-profile --domain-name "$AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN" --profile-id "$search_result" --region "$AWS_REGION" 2>/dev/null; then
                echo "Successfully deleted profile for account: $account_number"
            else
                echo "Failed to delete profile for account: $account_number"
            fi
        else
            echo "No profile found for account: $account_number"
        fi
        
        echo ""
    done
    
    echo "Customer profile cleanup completed!"
else
    echo ""
    echo "=== Skipping customer profile cleanup ==="
    echo "AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN not configured in .env file"
fi

echo ""
echo "=== Cleanup process completed ==="