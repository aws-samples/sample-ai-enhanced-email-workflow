"""API infrastructure construct for Lambda functions."""

import os
from aws_cdk import (
    Duration,
    aws_lambda as _lambda,
    aws_iam as iam,
)
from constructs import Construct
from cdk_nag import NagSuppressions
import constants


class API(Construct):
    """API construct containing Lambda functions for email processing."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        dynamodb_table_name: str,
        knowledge_base_id: str,
        lambda_reserved_concurrency: int = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Define specific Lambda function name
        email_function_name = f"{constants.APP_NAME}-EmailAIResponseRouting"
        
        # Create custom IAM role for EmailAIResponseRouting Lambda
        email_processing_role = iam.Role(
            self, "EmailAIResponseRoutingRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Custom role for EmailAIResponseRouting Lambda function",
            inline_policies={
                "CloudWatchLogsPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents"
                            ],
                            resources=[
                                f"arn:aws:logs:{scope.region}:{scope.account}:log-group:/aws/lambda/{email_function_name}*"
                            ]
                        )
                    ]
                )
            }
        )

        # Create EmailAIResponseRouting Lambda function with custom role and specific name
        self.email_processing_function = _lambda.Function(
            self, "EmailAIResponseRouting",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("backend/api/runtime"),
            timeout=Duration.seconds(60),
            memory_size=1024,
            reserved_concurrent_executions=lambda_reserved_concurrency,
            description=f"{constants.APP_NAME} - Email processing function with AI response generation",
            role=email_processing_role,
            function_name=email_function_name,
            environment={
                "KNOWLEDGE_BASE_ID": knowledge_base_id,
                "DYNAMODB_TABLE_NAME": dynamodb_table_name,
                "ENABLE_LOGGING": os.getenv("ENABLE_LOGGING", "true")
            }
        )

        # Add additional permissions to the email processing role
        email_processing_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:PutItem",
                    "dynamodb:GetItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem"
                ],
                resources=[
                    f"arn:aws:dynamodb:{scope.region}:{scope.account}:table/{dynamodb_table_name}"
                ]
            )
        )

        email_processing_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=[
                    "arn:aws:bedrock:*::foundation-model/*anthropic.claude-3-5-haiku-20241022-v1:0",
                    "arn:aws:bedrock:*::foundation-model/*anthropic.claude-3-haiku-20240307-v1:0",
                    "arn:aws:bedrock:*:*:inference-profile/*anthropic.claude-3-5-haiku-20241022-v1:0",
                    "arn:aws:bedrock:*:*:inference-profile/*anthropic.claude-3-haiku-20240307-v1:0"
                ]
            )
        )
        
        email_processing_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:Retrieve"],
                resources=["arn:aws:bedrock:*:*:knowledge-base/*"]
            )
        )
        
        email_processing_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["connect:GetAttachedFile"],
                resources=["*"]
            )
        )
        
        email_processing_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject"],
                resources=["arn:aws:s3:::*"]
            )
        )
        

        

        
        # Define specific Lambda function name
        query_function_name = f"{constants.APP_NAME}-QueryTempoStorage4AsyncMode"
        
        # Create custom IAM role for QueryTempoStorage4AsyncMode Lambda
        query_function_role = iam.Role(
            self, "QueryTempoStorage4AsyncModeRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Custom role for QueryTempoStorage4AsyncMode Lambda function",
            inline_policies={
                "CloudWatchLogsPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents"
                            ],
                            resources=[
                                f"arn:aws:logs:{scope.region}:{scope.account}:log-group:/aws/lambda/{query_function_name}*"
                            ]
                        )
                    ]
                )
            }
        )

        # Create QueryTempoStorage4AsyncMode Lambda function with custom role and specific name
        self.query_function = _lambda.Function(
            self, "QueryTempoStorage4AsyncMode",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="query_tempo_storage.lambda_handler",
            code=_lambda.Code.from_asset("backend/api/runtime"),
            timeout=Duration.seconds(30),
            memory_size=516,
            description=f"{constants.APP_NAME} - Query function for async result polling",
            role=query_function_role,
            function_name=query_function_name,
            environment={
                "DYNAMODB_TABLE_NAME": dynamodb_table_name
            }
        )

        # Add DynamoDB permissions to the query function role
        query_function_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:Query",
                    "dynamodb:Scan"
                ],
                resources=[
                    f"arn:aws:dynamodb:{scope.region}:{scope.account}:table/{dynamodb_table_name}"
                ]
            )
        )
        
