import boto3
import json
from botocore.exceptions import ClientError
import sys
from pathlib import Path
parent_dir = str(Path(__file__).parent.parent)
sys.path.append(parent_dir)

from confluence_ai.load import load_page

# Initialize the Amazon Bedrock client
bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')

# Function to call the Bedrock model
def call_bedrock_model(prompt):
    #modelId='anthropic.claude-3-7-sonnet-20250219-v1:0' 

    #modelId='us.anthropic.claude-3-5-sonnet-20241022-v2:0'
    modelId='us.anthropic.claude-3-7-sonnet-20250219-v1:0'
    native_request = {
                    "max_tokens": 2560,
                    "messages": [{"role": "user", "content": prompt}],
                    "anthropic_version": "bedrock-2023-05-31"
                    }
    # Convert the native request to JSON.
    request = json.dumps(native_request)
    print("-" * 20)
    print(request)
    response = bedrock_client.invoke_model (
        modelId=modelId,      
        body=request
        #endpointUrl='https://bedrock-runtime.us-east-1.amazonaws.com'
    )
    # Decode the response body.
    model_response = json.loads(response["body"].read())
    return model_response.get("content")

# Combine the context from the retrieved documents
docs = load_page()
context = "\n\n".join([doc.page_content for doc in docs])

# Create a new prompt with the context
contextual_prompt = f"""\
Human: 
Here is a Use case text:

{context}

provide a concise summary for the use case, do not skip anything important, include Title, Description, Key Features and Requirements only.
Go as long as necessary to list all requirements, do not copy text from the context.
Assistant:"""

# Call the Bedrock model and print the response
response = call_bedrock_model(contextual_prompt)
print(response)

print("\n\nDone answering.")  # Indicate that processing is done