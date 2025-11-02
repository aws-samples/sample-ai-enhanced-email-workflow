#!/usr/bin/env python3
import os
from dotenv import load_dotenv

import aws_cdk as cdk
from aws_cdk import Aspects

import constants
from backend.component import Backend
from backend.opensearch.component import OpenSearchStack

# Load environment variables from .env file
load_dotenv()

app = cdk.App()

# Create OpenSearch stack first (required for manual index creation step)
opensearch_stack = OpenSearchStack(
    app, "OpenSearchStack",
    env=cdk.Environment(
        account=os.getenv('AWS_ACCOUNT_ID'),
        region=os.getenv('AWS_REGION')
    )
)

# Component sandbox stack
Backend(
    app,
    constants.APP_NAME + "Sandbox",
    env=cdk.Environment(
        account=os.getenv('AWS_ACCOUNT_ID'),
        region=os.getenv('AWS_REGION')
    ),
    opensearch_collection_arn=opensearch_stack.collection.attr_arn,
    opensearch_index_name=f"kb-email-ai-{constants.APP_NAME.lower()}sandbox-index",
    api_lambda_reserved_concurrency=1,
    database_dynamodb_billing_mode=cdk.aws_dynamodb.BillingMode.PAY_PER_REQUEST,
)

app.synth()
