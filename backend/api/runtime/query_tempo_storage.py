import json
import boto3
import os
from decimal import Decimal

def convert_decimals(obj):
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(v) for v in obj]
    elif isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj

def search_dynamodb(table_name, contact_id):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    response = table.get_item(Key={'contactId': contact_id})
    return response.get('Item')

def delete_dynamodb_item(table_name, contact_id):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    table.delete_item(Key={'contactId': contact_id})

def lambda_handler(event, context):
    print(str(event))
    contact_id = event["Details"]["ContactData"]["ContactId"]
    table_name = os.environ.get('DYNAMODB_TABLE_NAME', 'TempoStorageEmailAnalyseResult')
    
    if not contact_id:
        return {
            'statusCode': 400,
            'error': 'contactId is required'
        }
    
    item = search_dynamodb(table_name, contact_id)
    if item:
        item = convert_decimals(item)
        print(str(item))
        # disable the delete item from DynamoDB table
        # delete_dynamodb_item(table_name, contact_id)
        return {
            'statusCode': 200,
            **(item)
        }
    else:
        return {
            'statusCode': 404,
            'error': 'Item not found'
        }