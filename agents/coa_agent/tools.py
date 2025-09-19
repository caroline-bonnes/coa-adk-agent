import vertexai
from vertexai.generative_models import GenerativeModel, Part
from google.adk.tools import ToolContext
from google.adk.agents.callback_context import CallbackContext
from google.cloud import storage
from google.adk.tools.base_tool import BaseTool
from typing import Dict, Any
import os 

bucket_uri = os.getenv("BUCKET") 
bucket_name= bucket_uri.removeprefix("gs://")

# Initialize Vertex AI once
vertexai.init()

def update_hold_database_before_tool_callback(tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext):
    """Inspects product hold status to determine whether or not to use the update_hold_database tool"""
    
    hold_status = tool_context.state['product_hold'] 

    if hold_status=='false':
        return {'Status':'Skipping update product hold database tool as no products meet the hold requirements.'}
    else:
        return None


def get_product_number(tool_context: ToolContext, gcs_uri: str) -> str:
    """
    Extracts the product number of a PDF document stored in a Google Cloud Storage bucket.

    This tool leverages the native multimodal capabilities of Gemini to read
    a PDF directly from a GCS URI and extracts the product number.

    Args:
        gcs_uri: The GCS URI of the PDF file.
                 (e.g., "gs://your-bucket-name/your-file.name.pdf")

    Returns:
        A string containing only the product number.
    """
 
    model = GenerativeModel("gemini-2.5-flash")

    # Create a Part object directly from the GCS URI
    pdf_file = Part.from_uri(
        mime_type="application/pdf",
        uri=gcs_uri
    )

    # The prompt for the model
    prompt = "Extract the product number from the document. Retrun only the product number."

    # Construct the full request and generate the content
    response = model.generate_content([pdf_file, prompt])
    tool_context.state['product'] = response.text

    return  {"status": "success", "Product": response.text}

def compare_docs(gcs_uri: str, product:str, tool_context: ToolContext) -> str:
    """
    Compares a COA document stored in a Google Cloud Storage bucket to its relevant spec sheet.

    This tool leverages the native multimodal capabilities of Gemini to read
    a PDF directly from a GCS URI and compare it to another document. 

    Args:
        gcs_uri: The GCS URI of the PDF file to summarize.
                 (e.g., "gs://your-bucket-name/your-file.name.pdf")

        product: The relevant product number (e.g. )

    Returns:
        A string containing the summary of the comparison.
    """
 
    model = GenerativeModel("gemini-2.5-flash")

    # Create a Part object directly from the GCS URI
    coa_file = Part.from_uri(
        mime_type="application/pdf",
        uri=gcs_uri
    )

    spec_uri = f'{bucket_uri}/{product} Spec Sheet.pdf'
    spec_sheet = Part.from_uri(
        mime_type="application/pdf",
        uri=spec_uri
    )

    # The prompt for the model
    prompt = "Analyze the provided COA against the requirements presented in the Spec Sheet. Summarize your findings. "

    # Construct the full request and generate the content
    response = model.generate_content([coa_file,spec_sheet, prompt])

    # write comparison text to state
    tool_context.state['analysis'] = response.text

    # determine hold 

    return  {"status": "success", "summary": response.text}

def determine_hold(tool_context: ToolContext):
    """
    Reviews the analysis of a COA document against it's spec sheet.

    This tool leverages Gemini to review an analysis and determine if a product should go on hold. 

    Args:
        analysis: The analysis to review.

    Returns:
        A string containing a `True` or `False ` response. 
    """
    analysis = tool_context.state['analysis']

    model = GenerativeModel("gemini-2.5-flash")

    prompt = f"Review the provided analysis. If any metrics do not conform, or are out of range, return True. \
    If all metrics conform to specifications, and all required metrics are provided, return False.\
    Analysis: {analysis}"
    
    
    response = model.generate_content([prompt]).text.strip().lower()

    tool_context.state['product_hold'] = response

    if response=='true': 
        return  {"status": "success", "summary": 'The product does not conform and should be put on hold.'}
    else:
        return  {"status": "success", "summary": "The product conforms to all specs."}

    
def update_hold_database(tool_context: ToolContext):
    "Updates the product hold database."
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob('/product_holds.txt')

    product = tool_context.state['product']

    new_line = f'Product #{product} status: Hold'

    existing_content = blob.download_as_text()

    new_content = existing_content + "\n" + new_line

    blob.upload_from_string(new_content, content_type='text/plain')

    return {"status": "success", "message": "The product has been put on hold."}



 