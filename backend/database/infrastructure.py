"""Database infrastructure construct for DynamoDB."""

from aws_cdk import (
    RemovalPolicy,
    aws_dynamodb as dynamodb,
)
from constructs import Construct
from cdk_nag import NagSuppressions
import constants


class Database(Construct):
    """Database construct containing DynamoDB table for temporary storage."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        dynamodb_billing_mode: dynamodb.BillingMode = dynamodb.BillingMode.PAY_PER_REQUEST,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create DynamoDB table for temporary storage
        self.dynamodb_table = dynamodb.Table(
            self, "TempoStorageEmailAnalyseResult",
            partition_key=dynamodb.Attribute(
                name="contactId",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb_billing_mode,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",
            table_name=f"{constants.APP_NAME}-TempoStorageEmailAnalyseResult",
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            )
        )
        
