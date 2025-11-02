import json
import boto3
import os
import re
import time
from urllib.parse import urlparse
from functools import lru_cache
from typing import Dict, Any, Optional, Union
from botocore.exceptions import ClientError

def validate_aws_url(url: str) -> bool:
    """
    Validate URL to ensure it's a safe AWS pre-signed URL.
    Only allows HTTPS URLs from AWS S3 domains.
    """
    try:
        parsed = urlparse(url)
        
        # Only allow HTTPS scheme
        if parsed.scheme != 'https':
            return False
            
        hostname = parsed.hostname
        if not hostname:
            return False
            
        # Check for various AWS S3 URL patterns
        s3_patterns = [
            # Virtual-hosted-style URLs
            '.s3.amazonaws.com',           # bucket.s3.amazonaws.com
            '.s3-',                        # bucket.s3-region.amazonaws.com
            '.s3.',                        # bucket.s3.region.amazonaws.com
            # Path-style URLs
            's3.amazonaws.com',            # s3.amazonaws.com/bucket
            's3-',                         # s3-region.amazonaws.com/bucket
        ]
        
        # Check if hostname matches S3 patterns and ends with amazonaws.com
        is_s3_pattern = any(pattern in hostname for pattern in s3_patterns)
        is_aws_domain = hostname.endswith('.amazonaws.com') or hostname == 'amazonaws.com'
        
        return is_s3_pattern and is_aws_domain
        
    except Exception:
        return False

def safe_download_s3_json(url: str) -> Optional[dict]:
    """
    Safely download JSON content from AWS S3 using boto3.
    Extracts bucket and key from pre-signed URL and uses S3 client directly.
    """
    # Add debug logging
    ENABLE_LOGGING = os.getenv("ENABLE_LOGGING", "true").lower() == "true"
    
    if ENABLE_LOGGING:
        print(f"Validating URL: {url}")
    
    if not validate_aws_url(url):
        if ENABLE_LOGGING:
            parsed = urlparse(url)
            print(f"URL validation failed - scheme: {parsed.scheme}, hostname: {parsed.hostname}")
        raise ValueError(f"Invalid or unsafe URL - not an AWS S3 URL: {url}")
    
    if ENABLE_LOGGING:
        print("URL validation passed, proceeding with download")
    
    try:
        # Parse the S3 URL to extract bucket and key
        parsed = urlparse(url)
        
        # Handle different S3 URL formats
        hostname = parsed.hostname
        
        if '.s3.' in hostname and hostname.endswith('.amazonaws.com'):
            # Virtual-hosted-style URL: https://bucket-name.s3.region.amazonaws.com/key
            # or https://amazon-connect-xxxxx.s3.eu-west-2.amazonaws.com/key
            bucket_name = hostname.split('.s3.')[0]
            object_key = parsed.path.lstrip('/')
        elif hostname.startswith('s3.') or hostname.startswith('s3-'):
            # Path-style URL: https://s3.region.amazonaws.com/bucket-name/key
            path_parts = parsed.path.lstrip('/').split('/', 1)
            if len(path_parts) < 2:
                raise ValueError("Invalid S3 URL format")
            bucket_name = path_parts[0]
            object_key = path_parts[1]
        else:
            raise ValueError(f"Unrecognized S3 URL format: {hostname}")
        
        # Remove query parameters from object key (they're for pre-signed URL auth)
        object_key = object_key.split('?')[0]
        
        # Use boto3 S3 client to download the object
        s3_client = boto3.client('s3')
        
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
            content = response['Body'].read().decode('utf-8')
            return json.loads(content)
        except ClientError as e:
            # If direct S3 access fails, the URL might be pre-signed for a reason
            # Fall back to using the pre-signed URL with boto3's built-in HTTP client
            import urllib3
            http = urllib3.PoolManager()
            
            # Validate URL scheme again for safety
            if not url.startswith('https://'):
                raise ValueError("URL must use HTTPS")
                
            response = http.request('GET', url)
            if response.status != 200:
                raise ValueError(f"HTTP {response.status}: Failed to download content")
            
            return json.loads(response.data.decode('utf-8'))
            
    except (json.JSONDecodeError, ClientError, Exception) as e:
        raise ValueError(f"Failed to download or parse JSON content: {e}")

# Constants - Model ID with fallback mechanism
def get_model_id():
    """Get appropriate model ID with fallback mechanism"""
    region = os.environ.get('AWS_REGION', 'us-east-1')
    
    # Region prefix mapping
    region_map = {
        'us-': 'us',
        'eu-': 'eu', 
        'ap-': 'us',  # Most AP regions use US inference profiles
        'ca-': 'us',  # Canada uses US inference profiles
        'sa-': 'us'   # South America uses US inference profiles
    }
    
    region_prefix = next((v for k, v in region_map.items() if region.startswith(k)), 'us')
    
    # Try Claude 3.5 Haiku first, fallback to Claude 3 Haiku
    models_to_try = [
        f"{region_prefix}.anthropic.claude-3-5-haiku-20241022-v1:0",
        "anthropic.claude-3-5-haiku-20241022-v1:0",
        f"{region_prefix}.anthropic.claude-3-haiku-20240307-v1:0", 
        "anthropic.claude-3-haiku-20240307-v1:0"
    ]
    
    return models_to_try

MODEL_IDS = get_model_id()
KNOWLEDGE_BASE_ID = os.environ.get('KNOWLEDGE_BASE_ID')
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')
ENABLE_LOGGING = os.environ.get('ENABLE_LOGGING', 'true').lower() == 'true'

# Initialize clients once (outside handler for reuse)
connect_client = boto3.client('connect')
bedrock_client = boto3.client('bedrock-runtime')
bedrock_agent_client = boto3.client('bedrock-agent-runtime')
dynamodb = boto3.resource('dynamodb')

# Confidence score deductions mapping - Updated to match README.md Scoring Framework
CONFIDENCE_DEDUCTIONS = {
    'no_knowledge': -100,        # Critical: No relevant KB information available
    'unclear_info': -85,         # High: Incomplete or ambiguous information  
    'premium_complaints': -50,   # Medium: Premium service level issues
    'angry_frustrated_tone': -30, # Medium: Negative sentiment detected
    'urgency': -15,              # Low: Time-sensitive requests requiring quick response
    'multiple_topics': -10       # Low: Additional topics beyond primary (-10 per topic)
}

def clean_string(text: Union[str, Any]) -> str:
    """Clean and normalize text content"""
    if not isinstance(text, str):
        text = str(text)
    
    # Single pass cleaning
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\ufeff', '')
    return ''.join(char for char in text if char in '\n\t' or (char.isprintable() and ord(char) < 127))

def format_text(text: Union[str, Any], html_breaks: bool = False) -> str:
    """Unified text formatting function"""
    if not isinstance(text, str):
        text = str(text)
    
    # Replace line breaks
    break_char = '<br/>' if html_breaks else ' '
    text = text.replace('\n', break_char).replace('\r', ' ').replace('\t', ' ')
    text = text.replace('•', '-').replace('\\n', break_char).replace('\\r', ' ')
    
    # Normalize whitespace
    return re.sub(r'\s+', ' ', text).strip()

def extract_attribute(event: Dict[str, Any], attribute_name: str, convert_to_int: bool = False) -> Optional[Union[str, int]]:
    """Extract attribute from Connect event with improved error handling"""
    try:
        # Check Attributes first
        if value := event.get('Attributes', {}).get(attribute_name):
            if str(value).strip():
                return int(value) if convert_to_int else str(value).strip()
        
        # Check SegmentAttributes
        if segment_attr := event.get('SegmentAttributes', {}).get(attribute_name):
            if isinstance(segment_attr, dict) and (value := segment_attr.get('ValueString')):
                if str(value).strip():
                    return int(value) if convert_to_int else str(value).strip()
        
        if ENABLE_LOGGING:
            print(f"{attribute_name} not found in event")
        return None
        
    except (ValueError, TypeError) as e:
        if ENABLE_LOGGING:
            print(f"Error extracting {attribute_name}: {e}")
        return None

def save_to_dynamodb(response_data: Dict[str, Any]) -> None:
    """Save response to DynamoDB with error handling"""
    if not DYNAMODB_TABLE_NAME:
        return
        
    try:
        # Add TTL for 3 days (259200 seconds)
        response_data['ttl'] = int(time.time()) + 259200
        
        table = dynamodb.Table(DYNAMODB_TABLE_NAME)
        table.put_item(Item=response_data)
        if ENABLE_LOGGING:
            print(f"Saved to DynamoDB: {response_data.get('contactId', 'Unknown')}")
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"DynamoDB save error: {e}")

def fix_customer_name_in_response(text: str, customer_name: str) -> str:
    """Fix customer name in response text"""
    if customer_name and customer_name != 'Valued Customer':
        text = text.replace('Dear Valued Customer,', f'Dear {customer_name},')
        text = text.replace('Dear Valued Customer', f'Dear {customer_name}')
    return text

def build_response(**kwargs) -> Dict[str, Any]:
    """Build standardized response with defaults"""
    defaults = {
        'contactId': None,
        'customer_name_text': None,
        'confidence_score': 0,
        'confidence_explanation': '',
        'suggested_response': 'Thank you for contacting us. An agent will assist you.',
        'intent': 'General Inquiry',
        'category': 'General_Inquiry',
        'credit_available': False,
        'credit_value': None,
        'spending_profile': None,
        'service_level': None,
        'add_info': None, 
        'model_used': None
    }
    
    # Merge with provided kwargs
    response = {**defaults, **kwargs}
    
    # Fix customer name in suggested response
    customer_name = response.get('customer_name_text')
    if 'suggested_response' in response:
        response['suggested_response'] = fix_customer_name_in_response(response['suggested_response'], customer_name)
    
    # Apply formatting
    response['confidence_explanation_sbs_formatting'] = format_text(response['confidence_explanation'], html_breaks=True)
    response['suggested_response'] = response['suggested_response'].replace('\\n', '\n')
    response['suggested_response_sbs_formatting'] = format_text(response['suggested_response'], html_breaks=True)
    response['suggested_response_agent'] = response['suggested_response']
    
    return response

def calculate_confidence_score(factors: Dict[str, int]) -> Dict[str, Any]:
    """Calculate confidence score with optimized logic"""
    total_deduction = sum(
        CONFIDENCE_DEDUCTIONS.get(factor, 0) * count 
        for factor, count in factors.items() 
        if factor in CONFIDENCE_DEDUCTIONS
    )
    
    return {
        'total_deduction': total_deduction,
        'final_score': max(0, 100 + total_deduction),
        **{factor: CONFIDENCE_DEDUCTIONS.get(factor, 0) * count for factor, count in factors.items()}
    }

@lru_cache(maxsize=128)
def get_instruction_template() -> str:
    """Cached instruction template"""
    return """
        Analyze the email's content and identify risk factors to determine a confidence score for sending a suggested response, then output the information in JSON format:

        Email content: {email_content}
        Knowledge results: {knowledge_results}
        Customer name: {customer_name_text}
        Supplemental information: 
        - Credit score: {credit_score}
        - Spending profile: {spending_profile}
        - Service Level: {service_level}
        - Additional Information: {add_info}

        Identify these factors (return 1 if present, 0 if not):
        - no_knowledge: No relevant knowledge base information available
        - unclear_info: Incomplete or ambiguous information
        - premium_complaints: Premium service level issues, consider if customer's Service Level {service_level} is "Premium" and they have any complaint or concern.
        - angry_frustrated_tone: Negative sentiment detected
        - urgency: Time-sensitive requests requiring quick response
        - multiple_topics: Count additional unrelated topics beyond the first

        Provide reasoning for detected factors only (no math calculations).

        IMPORTANT: In the suggested_response greeting:
        - If the customer name is a specific name, use that exact name.
        - Only use "Dear Valued Customer," if the customer name field shows "Valued Customer" (indicating no customer profile was found)

        Output ONLY valid JSON:
        {{
            "factors": {{
                "no_knowledge": [0 or 1],
                "unclear_info": [0 or 1],
                "premium_complaints": [0 or 1],
                "angry_frustrated_tone": [0 or 1],
                "urgency": [0 or 1],
                "multiple_topics": [number of additional topics]
            }},
            "confidence_explanation": "[Reasoning for detected factors only]",
            "intent": "[Summary of customer intent with key points]",
            "category": "[Credit_Cards|Insurance|Loan_Mortgage|Online_Banking|Investment|Payment|General_Inquiry]",
            "suggested_response": "Dear [USE THE ACTUAL CUSTOMER NAME PROVIDED ABOVE. Only use 'Valued Customer' if the customer name is 'Valued Customer', otherwise use the specific name],\\n\\n[Generate a personalized reply for the email content based on knowledge results and supplemental information (e.g. credit score, spending profile, service level and additional information) if there is any]\\n\\nKind regards,\\nCustomer Service Team\\nAnyCompany Bank"
        }}
        """

def query_knowledge_base(query_text: str, credit_score: Optional[int] = None) -> str:
    """Query knowledge base with enhanced context"""
    try:
        # Enhance query with credit score if available
        enhanced_query = f"{query_text} [Customer Credit Score: {credit_score}]" if credit_score else query_text
        
        # Truncate if too long
        if len(enhanced_query) > 1000:
            enhanced_query = enhanced_query[:1000]
        
        response = bedrock_agent_client.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={'text': enhanced_query},
            retrievalConfiguration={'vectorSearchConfiguration': {'numberOfResults': 5}}
        )
        
        if not response.get('retrievalResults'):
            return "No relevant information found in the knowledge base."
        
        # Build consolidated results
        results = []
        for i, result in enumerate(response['retrievalResults'], 1):
            content = result.get('content', {}).get('text', '')
            score = result.get('score', 0)
            results.append(f"--- Information {i} (Relevance: {score:.2f}) ---\n{content}")
        
        return '\n\n'.join(results)
        
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"Knowledge base query error: {e}")
        return "Error retrieving information from knowledge base."

def extract_email_content(event: Dict[str, Any]) -> str:
    """Extract email content with improved error handling"""
    try:
        # Check direct body attribute first
        if body := event.get('Attributes', {}).get('body'):
            return clean_string(body)

        # Extract instance and contact info
        instance_id = event["InstanceARN"].split('/')[1]
        contact_id = event["ContactId"]
        contact_arn = f"{event['InstanceARN']}/contact/{contact_id}"

        # Process email references
        for ref_key, ref_value in event.get("References", {}).items():
            if not (isinstance(ref_value, dict) and ref_value.get("Type") == "EMAIL_MESSAGE"):
                continue
                
            file_id = (ref_value.get("Value") or ref_value.get("Reference") or 
                      ref_value.get("Id") or ref_key)
            
            if not file_id:
                continue
                
            try:
                file_response = connect_client.get_attached_file(
                    InstanceId=instance_id,
                    FileId=file_id,
                    AssociatedResourceArn=contact_arn
                )
                
                download_url = file_response.get('DownloadUrlMetadata', {}).get('Url')
                if not download_url:
                    continue
                    
                email_json = safe_download_s3_json(download_url)
                    
                # Try multiple content fields
                for field in ['messageContent', 'content', 'body', 'text', 'message']:
                    if content := email_json.get(field):
                        return clean_string(content)
                        
            except Exception as e:
                if ENABLE_LOGGING:
                    print(f"File processing error {file_id}: {e}")
                continue

        # Fallback to email subject
        if subject := event.get('SegmentAttributes', {}).get('connect:EmailSubject', {}).get('ValueString'):
            return f"Email Subject: {subject}"

        return "Customer inquiry"

    except Exception as e:
        if ENABLE_LOGGING:
            print(f"Email content extraction error: {e}")
        return "Customer inquiry"

def parse_bedrock_response(response_text: str) -> Dict[str, Any]:
    """Parse Bedrock response with robust JSON handling"""
    # Clean response
    response_text = response_text.strip()
    if response_text.startswith('```json'):
        response_text = response_text[7:]
    if response_text.endswith('```'):
        response_text = response_text[:-3]
    response_text = response_text.strip()
    
    # Fix JSON newlines
    def fix_newlines(text):
        result, in_string, i = "", False, 0
        while i < len(text):
            char = text[i]
            if char == '"' and (i == 0 or text[i-1] != '\\'):
                in_string = not in_string
            elif in_string and char == '\n':
                char = '\\n'
            elif in_string and char == '\r':
                char = '\\r'
            result += char
            i += 1
        return result
    
    response_text = fix_newlines(response_text)
    
    try:
        result = json.loads(response_text)
        # Clean up newlines in specific fields
        for key in ['suggested_response', 'confidence_explanation']:
            if key in result:
                result[key] = result[key].replace('\\n', '\n')
        return result
    except json.JSONDecodeError:
        if ENABLE_LOGGING:
            print("JSON parsing failed, using regex extraction")
        
        # Regex fallback extraction
        factors = {}
        for factor in ['no_knowledge', 'unclear_info', 'premium_complaints', 
                      'angry_frustrated_tone', 'urgency']:
            factors[factor] = 1 if re.search(f'"{factor}"\\s*:\\s*1', response_text) else 0
        
        # Extract multiple_topics
        if match := re.search(r'"multiple_topics"\s*:\s*(\d+)', response_text):
            factors['multiple_topics'] = int(match.group(1))
        else:
            factors['multiple_topics'] = 0
        
        # Extract other fields with defaults
        intent = re.search(r'"intent"\s*:\s*"([^"]+)"', response_text)
        category = re.search(r'"category"\s*:\s*"([^"]+)"', response_text)
        confidence = re.search(r'"confidence_explanation"\s*:\s*"(.*?)"(?=\s*,\s*")', response_text, re.DOTALL)
        
        # Extract suggested_response
        suggested_match = re.search(r'"suggested_response"\s*:\s*"(.*?)"\s*\n*"?\s*}', response_text, re.DOTALL)
        if not suggested_match:
            suggested_match = re.search(r'"suggested_response"\s*:\s*"(.*)', response_text, re.DOTALL)
            suggested_response = re.sub(r'["\s}]*$', '', suggested_match.group(1)) if suggested_match else "Thank you for contacting us. An agent will assist you."
        else:
            suggested_response = suggested_match.group(1)
        
        return {
            "factors": factors,
            "confidence_explanation": confidence.group(1) if confidence else "Analysis unavailable",
            "intent": intent.group(1) if intent else "General Inquiry",
            "category": category.group(1) if category else "General_Inquiry",
            "suggested_response": suggested_response
        }

def call_bedrock(instruction: str, email_content: str) -> Dict[str, Any]:
    """Call Bedrock with optimized request handling and model fallback"""
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1500,
        "system": instruction,
        "messages": [{"role": "user", "content": email_content}],
        "temperature": 0
    }
    
    # Try models in order with fallback
    for model_id in MODEL_IDS:
        try:
            if ENABLE_LOGGING:
                print(f"Trying model: {model_id}")
                
            response = bedrock_client.invoke_model(
                body=json.dumps(request_body),
                modelId=model_id,
                accept='application/json',
                contentType='application/json'
            )
            
            response_body = json.loads(response['body'].read())
            response_text = response_body["content"][0]["text"]
            
            if ENABLE_LOGGING:
                print(f"Successfully used model: {model_id}")
                print(f"Raw Bedrock response: {response_text[:200]}...")
            
            result = parse_bedrock_response(response_text)
            return {'success': True, 'data': result, 'model_used': model_id}
            
        except Exception as e:
            if ENABLE_LOGGING:
                print(f"Model {model_id} failed: {e}")
            continue
    
    # All models failed
    return {'success': False, 'error': 'All model attempts failed'}

def lambda_handler(event, context):
    if ENABLE_LOGGING:
        print(f"Event: {json.dumps(event, default=str)}")
    
    try:
        contact_data = event["Details"]["ContactData"]
        
        # Extract all attributes in one pass
        email_content = extract_email_content(contact_data)
        credit_score = extract_attribute(contact_data, 'CreditScore', convert_to_int=True)
        customer_name = extract_attribute(contact_data, 'CustomerName') or 'Valued Customer'
        spending_profile = extract_attribute(contact_data, 'SpendingProfile')
        service_level = extract_attribute(contact_data, 'ServiceLevel')
        add_info = extract_attribute(contact_data, 'AddInfo')
        
        # Build instruction and call Bedrock
        knowledge_results = query_knowledge_base(email_content, credit_score)
        instruction = get_instruction_template().format(
            email_content=email_content,
            knowledge_results=knowledge_results,
            customer_name_text=customer_name,
            credit_score=credit_score,
            spending_profile=spending_profile,
            service_level=service_level,
            add_info=add_info
        )
        
        # Debug: Log the instruction being sent to AI
        if ENABLE_LOGGING:
            print(f"Customer name being sent to AI: {customer_name}")
            print(f"Instruction contains customer name: {'Customer name: ' + customer_name in instruction}")
        
        bedrock_result = call_bedrock(instruction, email_content)
        
        if bedrock_result['success']:
            data = bedrock_result['data']
            factors = data.get('factors', {})
            
            if ENABLE_LOGGING:
                print(f"Factors: {factors}")
            
            confidence_calculation = calculate_confidence_score(factors)
            confidence_score = confidence_calculation["final_score"]
            
            if ENABLE_LOGGING:
                print(f"Confidence calculation: {confidence_calculation}")
            
            response = build_response(
                contactId=contact_data['ContactId'],
                customer_name_text=customer_name,
                confidence_score=confidence_score,
                confidence_explanation=f"{data.get('confidence_explanation', 'Score analysis unavailable')} {str(confidence_calculation).replace('{', '(').replace('}', ')')}",
                suggested_response=data.get('suggested_response', ''),
                intent=data.get('intent', ''),
                category=data.get('category', 'General_Inquiry'),
                credit_available=credit_score is not None,
                credit_value=credit_score,
                spending_profile=spending_profile,
                service_level=service_level,
                add_info=add_info,
                model_used=bedrock_result.get('model_used', 'Unknown')
            )
        else:
            # Error response
            response = build_response(
                contactId=contact_data['ContactId'],
                customer_name_text=customer_name,
                confidence_score=0,
                confidence_explanation='Processing error detected - unable to analyze email content.\nRoute to agent for manual review.',
                intent='General Inquiry',
                category='General_Inquiry', 
                credit_available=credit_score is not None,
                credit_value=credit_score,
                spending_profile=spending_profile,
                service_level=service_level,
                add_info=add_info, 
                model_used='No'
            )
        
        # Save to DynamoDB
        save_to_dynamodb(response)
        
        if ENABLE_LOGGING:
            print(f"Response: {response}")
        
        return response
        
    except Exception as e:
        if ENABLE_LOGGING:
            print(f"Lambda handler error: {e}")
        
        error_response = build_response(
            confidence_explanation=f'System error encountered: {str(e)[:100]}...\nImmediate agent review required for technical issue resolution.',
            intent='General Inquiry',
            category='General_Inquiry'
        )
        
        if ENABLE_LOGGING:
            print(f"Error response: {error_response}")
        
        return error_response