"""Amazon Connect infrastructure construct."""

import os
import json
import csv
import logging
from aws_cdk import (
    aws_lambda as _lambda,
    aws_connect as connect,
    aws_iam as iam,
    custom_resources as cr,
)
from constructs import Construct
import constants

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Connect(Construct):
    """Connect construct for integrating Lambda functions with Amazon Connect."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        email_processing_function: _lambda.Function,
        query_function: _lambda.Function,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Store function references for Connect integration
        self.email_processing_function = email_processing_function
        self.query_function = query_function
        
        # Generate ARNs from environment variables
        instance_id = os.getenv("AMAZON_CONNECT_INSTANCE_ID", "")
        queue_id = os.getenv("AMAZON_CONNECT_QUEUE_ID", "")
        
        if instance_id:
            instance_arn = f"arn:aws:connect:{scope.region}:{scope.account}:instance/{instance_id}"
            queue_arn = f"arn:aws:connect:{scope.region}:{scope.account}:instance/{instance_id}/queue/{queue_id}"
            
            # Create Amazon Connect Contact Flows
            self._create_contact_flows(instance_arn, queue_arn)
            
            # Grant Amazon Connect permission to invoke Lambda functions
            self._grant_connect_permissions(instance_arn)
            
            # Create Lambda integration associations
            self._create_lambda_integrations(instance_arn)
        
        # Create customer profiles from CSV
        self._create_customer_profiles()

    def _create_contact_flows(self, instance_arn: str, queue_arn: str):
        """Create Amazon Connect Contact Flows."""
        # Create the first Amazon Connect Contact Flow (Step-by-Step Guide)
        with open('contact-flows/Email-SBS.json', 'r', encoding='utf-8') as f:
            contact_flow_content = f.read()
        
        # Replace region placeholder with actual region
        contact_flow_content = contact_flow_content.replace('eu-west-2', self.node.scope.region)
        
        self.email_sbs_contact_flow = connect.CfnContactFlow(
            self, "EmailSBSContactFlow",
            instance_arn=instance_arn,
            name=f"{constants.APP_NAME}-Email-SBS",
            description=f"{constants.APP_NAME} - Step-by-step guidance contact flow for email processing",
            type="CONTACT_FLOW",
            content=contact_flow_content
        )
        
        # Create the second Amazon Connect Contact Flow (main flow)
        try:
            with open('contact-flows/EmailSuggestedResponseConfidenceScore.json', 'r', encoding='utf-8') as file:
                content = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Error reading contact flow file: {str(e)}")
            raise
        
        # Update Queue ARN in the content
        for action in content['Actions']:
            if action['Type'] == 'UpdateContactTargetQueue':
                action['Parameters']['QueueId'] = queue_arn
        
        # Update Lambda ARN in the content
        for action in content['Actions']:
            if action['Type'] == 'InvokeLambdaFunction':
                if 'QueryTempoStorage4AsyncMode' in action['Parameters']['LambdaFunctionARN']:
                    action['Parameters']['LambdaFunctionARN'] = self.query_function.function_arn
                elif 'EmailAIResponseRouting' in action['Parameters']['LambdaFunctionARN']:
                    action['Parameters']['LambdaFunctionARN'] = self.email_processing_function.function_arn
        
        # Update DefaultAgentUI with Email-SBS contact flow ARN
        for action in content['Actions']:
            if action['Type'] == 'UpdateContactEventHooks':
                if 'DefaultAgentUI' in action['Parameters']['EventHooks']:
                    action['Parameters']['EventHooks']['DefaultAgentUI'] = self.email_sbs_contact_flow.attr_contact_flow_arn
        
        # Replace email address placeholder with environment variable
        email_address = os.getenv("AMAZON_CONNECT_EMAIL_ADDRESS", "anycompany@email.connect.aws")
        content_str = json.dumps(content)
        content_str = content_str.replace("anycompany@email.connect.aws", email_address)
        content = json.loads(content_str)
        
        # Update CreateCase action with case template ID from environment variable
        case_template_id = os.getenv("AMAZON_CONNECT_CASE_TEMPLATE_ID", "")
        content_str = json.dumps(content)
        content_str = content_str.replace("case-template-id", case_template_id)
        content = json.loads(content_str)
        
        self.email_confidence_contact_flow = connect.CfnContactFlow(
            self, "EmailSuggestedResponseConfidenceScoreContactFlow",
            instance_arn=instance_arn,
            name=f"{constants.APP_NAME}-EmailSuggestedResponseConfidenceScore",
            description=f"{constants.APP_NAME} - Main email processing contact flow with AI response generation and confidence scoring",
            type="CONTACT_FLOW",
            content=json.dumps(content)
        )

    def _grant_connect_permissions(self, instance_arn: str):
        """Grant Amazon Connect permission to invoke Lambda functions."""
        self.email_processing_function.add_permission(
            "ConnectInvokePermission",
            principal=iam.ServicePrincipal("connect.amazonaws.com"),
            source_arn=instance_arn
        )
        
        self.query_function.add_permission(
            "ConnectInvokePermission",
            principal=iam.ServicePrincipal("connect.amazonaws.com"),
            source_arn=instance_arn
        )

    def _create_lambda_integrations(self, instance_arn: str):
        """Create Lambda integration associations."""
        self.email_lambda_integration = connect.CfnIntegrationAssociation(
            self, "EmailAIResponseRoutingIntegration",
            instance_id=instance_arn,
            integration_type="LAMBDA_FUNCTION",
            integration_arn=self.email_processing_function.function_arn
        )
        
        self.query_lambda_integration = connect.CfnIntegrationAssociation(
            self, "QueryTempoStorage4AsyncModeIntegration",
            instance_id=instance_arn,
            integration_type="LAMBDA_FUNCTION",
            integration_arn=self.query_function.function_arn
        )

    def _create_customer_profiles(self):
        """Create customer profiles from CSV."""
        customer_profiles_domain = os.getenv("AMAZON_CONNECT_CUSTOMER_PROFILES_DOMAIN", "")
        
        if customer_profiles_domain:
            try:
                with open('customerprofiles.csv', 'r', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for i, row in enumerate(reader):
                        profile_data = {
                            "AccountNumber": row.get('AccountNumber', ''),
                            "FirstName": row.get('FirstName', ''),
                            "LastName": row.get('LastName', ''),
                            "EmailAddress": row.get('EmailAddress', ''),
                            "PhoneNumber": row.get('PhoneNumber', ''),
                            "MobilePhoneNumber": row.get('MobilePhoneNumber', ''),
                            "HomePhoneNumber": row.get('HomePhoneNumber', ''),
                            "BusinessPhoneNumber": row.get('BusinessPhoneNumber', ''),
                            "AdditionalInformation": row.get('AdditionalInformation', ''),
                            "PartyType": row.get('PartyType', ''),
                            "BirthDate": row.get('BirthDate', ''),
                            "Gender": row.get('Gender', ''),
                            "Address": {
                                "Address1": row.get('Address.Address', ''),
                                "City": row.get('Address.City', ''),
                                "Country": row.get('Address.Country', ''),
                                "PostalCode": row.get('Address.PostalCode', '')
                            },
                            "Attributes": {
                                "CreditScore": row.get('CreditScore', ''),
                                "SpendingProfile": row.get('SpendingProfile', ''),
                                "ServiceLevel": row.get('ServiceLevel', ''),
                                "LoanApproved": row.get('LoanApproved', '')
                            }
                        }
                        
                        # Remove empty fields
                        profile_data = {k: v for k, v in profile_data.items() if v}
                        if profile_data.get('Address'):
                            profile_data['Address'] = {k: v for k, v in profile_data['Address'].items() if v}
                        if profile_data.get('Attributes'):
                            profile_data['Attributes'] = {k: v for k, v in profile_data['Attributes'].items() if v}
                        
                        cr.AwsCustomResource(
                            self, f"CreateCustomerProfile{i}",
                            on_create=cr.AwsSdkCall(
                                service="customerprofiles",
                                action="createProfile",
                                parameters={
                                    "DomainName": customer_profiles_domain,
                                    **profile_data
                                },
                                physical_resource_id=cr.PhysicalResourceId.of(f"profile-{row.get('AccountNumber', i)}")
                            ),
                            policy=cr.AwsCustomResourcePolicy.from_statements([
                                iam.PolicyStatement(
                                    effect=iam.Effect.ALLOW,
                                    actions=["profile:CreateProfile"],
                                    resources=["*"]
                                )
                            ]),
                            resource_type=f"Custom::{constants.APP_NAME}CustomerProfile"
                        )
            except FileNotFoundError:
                logger.warning("customerprofiles.csv not found, skipping customer profile creation")