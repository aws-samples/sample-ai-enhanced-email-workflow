"""Storage infrastructure construct for S3 bucket and knowledge articles."""

from aws_cdk import (
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_iam as iam,
    Fn,
    RemovalPolicy,
)
from constructs import Construct
from cdk_nag import NagSuppressions
import constants


class Storage(Construct):
    """Storage construct containing S3 bucket for knowledge articles."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket for access logs
        self.access_logs_bucket = s3.Bucket(
            self, "AccessLogsBucket",
            versioned=True,
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            bucket_name=f"{constants.APP_NAME.lower()}-access-logs-{scope.account}-{scope.region}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True
        )

        # Create S3 bucket for knowledge articles
        self.s3_bucket = s3.Bucket(
            self, "EmailAIResponseRoutingBucket",
            versioned=True,
            public_read_access=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            bucket_name=f"{constants.APP_NAME.lower()}-knowledge-articles-{scope.account}-{scope.region}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            server_access_logs_bucket=self.access_logs_bucket,
            server_access_logs_prefix="access-logs/"
        )
        
        # Upload knowledge articles to S3 bucket
        self.knowledge_deployment = s3deploy.BucketDeployment(
            self, "KnowledgeArticles",
            sources=[s3deploy.Source.asset("knowledge-articles")],
            destination_bucket=self.s3_bucket,
            destination_key_prefix=""
        )
        
        # Grant specific S3 permissions to the imported service role from OpenSearch stack
        kb_service_role_arn = Fn.import_value("BedrockServiceRoleArn")
        kb_service_role = iam.Role.from_role_arn(
            self, "ImportedBedrockRoleForS3",
            role_arn=kb_service_role_arn
        )
        
        # Create a specific IAM policy for the knowledge articles bucket only
        kb_s3_policy = iam.Policy(
            self, "BedrockKnowledgeArticlesS3Policy",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:GetObject",
                        "s3:GetObjectVersion"
                    ],
                    resources=[f"{self.s3_bucket.bucket_arn}/*"]
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:ListBucket",
                        "s3:GetBucketLocation"
                    ],
                    resources=[self.s3_bucket.bucket_arn]
                )
            ]
        )
        
        # Attach the specific policy to the Bedrock service role
        kb_s3_policy.attach_to_role(kb_service_role)
        

        
