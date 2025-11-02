"""Main backend component that composes all logical units."""

import os
from typing import Any
from aws_cdk import (
    Stack,
    CfnOutput,
    aws_dynamodb as dynamodb,
)
from constructs import Construct

import constants
from backend.api.infrastructure import API
from backend.database.infrastructure import Database
from backend.storage.infrastructure import Storage
from backend.knowledge.infrastructure import KnowledgeBase
from backend.connect.infrastructure import Connect
from cdk_nag import NagSuppressions


class Backend(Stack):
    """Main backend stack that composes all logical units."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        opensearch_collection_arn: str,
        opensearch_index_name: str = "bedrock-knowledge-base-default-index",
        database_dynamodb_billing_mode: dynamodb.BillingMode = dynamodb.BillingMode.PAY_PER_REQUEST,
        api_lambda_reserved_concurrency: int = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create storage for knowledge articles
        storage = Storage(self, "Storage")

        # Create database for temporary storage
        database = Database(
            self,
            "Database",
            dynamodb_billing_mode=database_dynamodb_billing_mode
        )

        # Create knowledge base
        knowledge_base = KnowledgeBase(
            self,
            "KnowledgeBase",
            s3_bucket_arn=storage.s3_bucket.bucket_arn,
            opensearch_collection_arn=opensearch_collection_arn,
            opensearch_index_name=opensearch_index_name
        )

        # Create API with Lambda functions
        api = API(
            self,
            "API",
            dynamodb_table_name=database.dynamodb_table.table_name,
            knowledge_base_id=knowledge_base.knowledge_base.attr_knowledge_base_id,
            lambda_reserved_concurrency=api_lambda_reserved_concurrency
        )

        # Create Connect integration
        connect_integration = Connect(
            self,
            "Connect",
            email_processing_function=api.email_processing_function,
            query_function=api.query_function
        )

        # Grant permissions between logical units
        database.dynamodb_table.grant_read_write_data(api.email_processing_function)
        database.dynamodb_table.grant_read_data(api.query_function)
        storage.s3_bucket.grant_read(knowledge_base.bedrock_kb_role)

        # Stack outputs
        self.knowledge_base_id = CfnOutput(
            self,
            "KnowledgeBaseId",
            value=knowledge_base.knowledge_base.attr_knowledge_base_id,
            description=f"{constants.APP_NAME} - Bedrock Knowledge Base ID"
        )

        self.email_processing_function_name = CfnOutput(
            self,
            "EmailProcessingFunctionName",
            value=api.email_processing_function.function_name,
            description=f"{constants.APP_NAME} - Email Processing Lambda Function Name"
        )

        self.query_function_name = CfnOutput(
            self,
            "QueryFunctionName",
            value=api.query_function.function_name,
            description=f"{constants.APP_NAME} - Query Lambda Function Name"
        )

        self.s3_bucket_name = CfnOutput(
            self,
            "S3BucketName",
            value=storage.s3_bucket.bucket_name,
            description=f"{constants.APP_NAME} - S3 Bucket for Knowledge Articles"
        )

        self.dynamodb_table_name = CfnOutput(
            self,
            "DynamoDBTableName",
            value=database.dynamodb_table.table_name,
            description=f"{constants.APP_NAME} - DynamoDB Table for Temporary Storage"
        )
        
        # Additional stack outputs to match original functionality
        self.email_lambda_url = CfnOutput(
            self,
            "EmailAIResponseRoutingLambdaUrl",
            value=f"https://console.aws.amazon.com/lambda/home?region={self.region}#/functions/{api.email_processing_function.function_name}",
            description=f"{constants.APP_NAME} - AWS Console URL for EmailAIResponseRouting Lambda function"
        )
        
        self.query_lambda_url = CfnOutput(
            self,
            "QueryTempoStorage4AsyncModeLambdaUrl",
            value=f"https://console.aws.amazon.com/lambda/home?region={self.region}#/functions/{api.query_function.function_name}",
            description=f"{constants.APP_NAME} - AWS Console URL for QueryTempoStorage4AsyncMode Lambda function"
        )
        
        self.knowledge_base_url = CfnOutput(
            self,
            "KnowledgeBaseUrl",
            value=f"https://console.aws.amazon.com/bedrock/home?region={self.region}#/knowledge-bases/{knowledge_base.knowledge_base.attr_knowledge_base_id}",
            description=f"{constants.APP_NAME} - AWS Console URL for the Bedrock Knowledge Base"
        )
        
        self.s3_bucket_url = CfnOutput(
            self,
            "S3BucketUrl",
            value=f"https://s3.console.aws.amazon.com/s3/buckets/{storage.s3_bucket.bucket_name}?region={self.region}",
            description=f"{constants.APP_NAME} - AWS Console URL for the S3 bucket"
        )
        
        self.dynamodb_table_url = CfnOutput(
            self,
            "DynamoDBTableUrl",
            value=f"https://console.aws.amazon.com/dynamodbv2/home?region={self.region}#table?name={database.dynamodb_table.table_name}",
            description=f"{constants.APP_NAME} - AWS Console URL for the DynamoDB table"
        )
        
        # Contact Flow outputs (only if Connect instance is configured)
        instance_id = os.getenv("AMAZON_CONNECT_INSTANCE_ID", "")
        if instance_id and hasattr(connect_integration, 'email_sbs_contact_flow'):
            self.email_sbs_arn = CfnOutput(
                self,
                "EmailSBSArn",
                value=connect_integration.email_sbs_contact_flow.attr_contact_flow_arn,
                description=f"{constants.APP_NAME} - ARN of the Email-SBS Contact Flow"
            )
            
            self.email_confidence_arn = CfnOutput(
                self,
                "EmailSuggestedResponseConfidenceScoreArn",
                value=connect_integration.email_confidence_contact_flow.attr_contact_flow_arn,
                description=f"{constants.APP_NAME} - ARN of the EmailSuggestedResponseConfidenceScore Contact Flow"
            )
        
        # Add stack-level CDK-nag suppressions for critical security issues only
        NagSuppressions.add_stack_suppressions(
            self,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Bedrock foundation models and services require wildcard permissions by design for cross-region model access",
                    "appliesTo": [
                        "Resource::arn:aws:bedrock:*::foundation-model/*anthropic.claude-3-5-haiku-20241022-v1:0",
                        "Resource::arn:aws:bedrock:*::foundation-model/*anthropic.claude-3-haiku-20240307-v1:0",
                        "Resource::arn:aws:bedrock:*:*:inference-profile/*anthropic.claude-3-5-haiku-20241022-v1:0",
                        "Resource::arn:aws:bedrock:*:*:inference-profile/*anthropic.claude-3-haiku-20240307-v1:0",
                        "Resource::arn:aws:bedrock:*:*:knowledge-base/*"
                    ]
                },
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Connect service requires wildcard access for GetAttachedFile operations across all instances",
                    "appliesTo": ["Resource::*"]
                },
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "S3 GetObject permission needed for Connect attachments from unknown bucket names",
                    "appliesTo": ["Resource::arn:aws:s3:::*"]
                }
            ]
        )