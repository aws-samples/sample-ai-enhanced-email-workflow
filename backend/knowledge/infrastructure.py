"""Knowledge base infrastructure construct for Amazon Bedrock."""

import os
from aws_cdk import (
    aws_bedrock as bedrock,
    aws_iam as iam,
    aws_opensearchserverless as opensearchserverless,
    Fn,
)
from constructs import Construct
from cdk_nag import NagSuppressions
import constants


class KnowledgeBase(Construct):
    """Knowledge base construct containing Bedrock Knowledge Base and OpenSearch Serverless."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        s3_bucket_arn: str,
        opensearch_collection_arn: str,
        opensearch_index_name: str = "bedrock-knowledge-base-default-index",
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Import service role from OpenSearch stack
        kb_service_role_arn = Fn.import_value("BedrockServiceRoleArn")
        
        # Import the service role
        self.bedrock_kb_role = iam.Role.from_role_arn(
            self, "ImportedBedrockRole",
            role_arn=kb_service_role_arn
        )
        
        # Add CDK-nag suppressions for necessary wildcard permissions
        NagSuppressions.add_resource_suppressions(
            self.bedrock_kb_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Bedrock foundation models require wildcard region access as model ARNs contain region wildcards by design",
                    "appliesTo": [
                        "Resource::arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v1",
                        "Resource::arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v2:0"
                    ]
                },
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "S3 bucket access requires wildcard permissions for object-level operations on knowledge base content",
                    "appliesTo": [
                        "Action::s3:GetBucket*",
                        "Action::s3:GetObject*",
                        "Action::s3:List*"
                    ]
                }
            ]
        )

        # Create Bedrock Knowledge Base
        self.knowledge_base = bedrock.CfnKnowledgeBase(
            self, "EmailAIKnowledgeBase",
            name=f"{constants.APP_NAME}KnowledgeBase",
            description=f"{constants.APP_NAME} - Knowledge base for email AI response generation",
            role_arn=kb_service_role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn="arn:aws:bedrock:" + os.getenv("AWS_REGION", "us-east-1") + "::foundation-model/amazon.titan-embed-text-v2:0"
                )
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="OPENSEARCH_SERVERLESS",
                opensearch_serverless_configuration=bedrock.CfnKnowledgeBase.OpenSearchServerlessConfigurationProperty(
                    collection_arn=Fn.import_value("VectorCollectionArn"),
                    vector_index_name=opensearch_index_name,
                    field_mapping=bedrock.CfnKnowledgeBase.OpenSearchServerlessFieldMappingProperty(
                        vector_field="bedrock-knowledge-base-default-vector",
                        text_field="AMAZON_BEDROCK_TEXT_CHUNK",
                        metadata_field="AMAZON_BEDROCK_METADATA"
                    )
                )
            )
        )

        # Create Data Source for the Knowledge Base
        self.data_source = bedrock.CfnDataSource(
            self, "KnowledgeBaseDataSource",
            knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
            name=f"{constants.APP_NAME}S3DataSource",
            description=f"{constants.APP_NAME} - S3 data source for knowledge articles",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=s3_bucket_arn
                )
            )
        )