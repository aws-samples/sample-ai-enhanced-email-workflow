from aws_cdk import (
    Duration,
    Stack,
    aws_opensearchserverless as opensearchserverless,
    aws_iam as iam,
    aws_lambda as _lambda,
    custom_resources as cr,
    CfnOutput
)
from constructs import Construct
from cdk_nag import NagSuppressions
import constants

class OpenSearchStack(Stack):
    """OpenSearch Serverless stack for Bedrock Knowledge Base vector storage."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create OpenSearch Serverless security policies
        encryption_policy = opensearchserverless.CfnSecurityPolicy(
            self, "VectorCollectionEncryptionPolicy",
            name="kb-vector-collection-encryption",
            type="encryption",
            policy='{"Rules":[{"ResourceType":"collection","Resource":["collection/kb-vector-collection"]}],"AWSOwnedKey":true}'
        )
        
        network_policy = opensearchserverless.CfnSecurityPolicy(
            self, "VectorCollectionNetworkPolicy",
            name="kb-vector-collection-network",
            type="network",
            policy='[{"Rules":[{"ResourceType":"collection","Resource":["collection/kb-vector-collection"]},{"ResourceType":"dashboard","Resource":["collection/kb-vector-collection"]}],"AllowFromPublic":true}]'
        )
        
        # Create service role for Bedrock Knowledge Base
        kb_service_role = iam.Role(
            self, "BedrockKnowledgeBaseRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            inline_policies={
                "BedrockKnowledgeBasePolicy": iam.PolicyDocument(
                    statements=[
                        # Embedding model permissions
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["bedrock:InvokeModel"],
                            resources=["arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v2:0"]
                        ),
                        # OpenSearch Serverless permissions
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "aoss:APIAccessAll",
                                "aoss:CreateIndex",
                                "aoss:DeleteIndex",
                                "aoss:UpdateIndex",
                                "aoss:DescribeIndex",
                                "aoss:ReadDocument",
                                "aoss:WriteDocument",
                                "aoss:CreateCollection"
                            ],
                            resources=["*"]
                        ),
                        # S3 permissions for knowledge articles
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:GetObject",
                                "s3:ListBucket"
                            ],
                            resources=["*"]
                        )
                    ]
                )
            }
        )
        
        # Add CDK-nag suppressions for necessary wildcard permissions
        NagSuppressions.add_resource_suppressions(
            kb_service_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Bedrock foundation models require wildcard region access as model ARNs contain region wildcards by design",
                    "appliesTo": ["Resource::arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v2:0"]
                },
                {
                    "id": "AwsSolutions-IAM5", 
                    "reason": "OpenSearch Serverless collections are dynamically created and require wildcard access for collection management operations",
                    "appliesTo": ["Resource::*"]
                }
            ]
        )
        
        # Create data access policy after service role
        data_access_policy = opensearchserverless.CfnAccessPolicy(
            self, "VectorCollectionDataAccessPolicy",
            name="kb-vector-collection-access",
            type="data",
            policy=f'[{{"Rules":[{{"ResourceType":"collection","Resource":["collection/kb-vector-collection"],"Permission":["aoss:*"]}},{{"ResourceType":"index","Resource":["index/kb-vector-collection/*"],"Permission":["aoss:*"]}}],"Principal":["arn:aws:iam::{self.account}:root","{kb_service_role.role_arn}"]}}]'
        )
        
        # Create OpenSearch Serverless collection for vector store
        vector_collection = opensearchserverless.CfnCollection(
            self, "KnowledgeBaseVectorCollection",
            name="kb-vector-collection",
            type="VECTORSEARCH"
        )
        
        vector_collection.add_dependency(encryption_policy)
        vector_collection.add_dependency(network_policy)
        vector_collection.add_dependency(data_access_policy)
        
        # Store collection reference for cross-stack access
        self.collection = vector_collection


        # Export collection ARN and ID for cross-stack reference
        CfnOutput(
            self, "VectorCollectionArn",
            value=vector_collection.attr_arn,
            export_name="VectorCollectionArn",
            description=f"{constants.APP_NAME} - OpenSearch Serverless Collection ARN for Bedrock Knowledge Base"
        )
        
        CfnOutput(
            self, "VectorCollectionId",
            value=vector_collection.attr_id,
            export_name="VectorCollectionId",
            description=f"{constants.APP_NAME} - OpenSearch Serverless Collection ID for index creation"
        )
        
        CfnOutput(
            self, "BedrockServiceRoleArn",
            value=kb_service_role.role_arn,
            export_name="BedrockServiceRoleArn",
            description=f"{constants.APP_NAME} - Bedrock Knowledge Base Service Role ARN"
        )
        
        # Export readiness signal
        CfnOutput(
            self, "CollectionReady",
            value="true",
            export_name="CollectionReady",
            description=f"{constants.APP_NAME} - Signal that collection is ready for Knowledge Base"
        )
        
        # AWS Console URL for OpenSearch collection
        CfnOutput(
            self, "VectorCollectionUrl",
            value=f"https://console.aws.amazon.com/aos/home?region={self.region}#opensearch/collections/kb-vector-collection",
            description=f"{constants.APP_NAME} - AWS Console URL for the OpenSearch Serverless Collection"
        )