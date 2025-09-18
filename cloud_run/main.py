import os
import re
import requests
import google.auth.transport.requests
from google.auth.exceptions import DefaultCredentialsError
from google.auth import compute_engine
import functions_framework
from cloudevents.http import CloudEvent


TARGET_APP_URL = os.environ.get("TARGET_APP_URL") 
TARGET_APP_NAME = "test_agents" 


def get_auth_token(audience_url):
    try:
        # Create an auth request object
        request = google.auth.transport.requests.Request()
        credentials = compute_engine.IDTokenCredentials(
            request=request,
            target_audience=audience_url,
            use_metadata_identity_endpoint=True  # Use the default application credentials
        )
        credentials.refresh(request)
        return credentials.token
    except DefaultCredentialsError as e:
        print(f"Error: Could not find default credentials. {e}")
        print("Are you running locally? Try 'gcloud auth application-default login'")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during auth: {e}")
        return None
    
@functions_framework.cloud_event   
def handle_event(cloud_event: CloudEvent):
    data = cloud_event.data

    # 1. Check for Target URL configuration
    if not TARGET_APP_URL:
        print("Error: TARGET_APP_URL environment variable is not set.")
        # Return a 500 error to signal a server configuration problem.
        # Eventarc will try to redeliver the message.
        return "Server configuration error", 500

    # 2. Extract GCS file data from the event
    try:
        bucket = data["bucket"]
        name = data["name"]  # 'name' is the full path to the file
        gcs_uri = f"gs://{bucket}/{name}"
        print(f"Received trigger for file: {gcs_uri}")
    except KeyError as e:
        print(f"Error: Event payload is missing expected key: {e}")
        print(f"Received data: {data}")
        # Acknowledge the event with a 400 error so it's not retried.
        return "Bad request: Invalid event payload", 400
    
    # 3. Set Session and User ID
    user_id = 'Cloud Run Service'
    session_id = name

    # 4. Get Auth Token for the target service
    token = get_auth_token(TARGET_APP_URL)
    if not token:
        print("Error: Failed to fetch auth token.")
        # Return 500 to signal an auth problem that might be temporary.
        return "Internal authentication error", 500

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 5. Call the first endpoint (Create/Update Session)
    # This ensures the session exists.
    session_url = TARGET_APP_URL+f'/apps/test_agents/users/{user_id}/sessions/{session_id}'
    session_data = {
    "state": {
        "preferred_language": "English",
        "visit_count": 5
    }
    }   

    try:
        print(f"Calling session update endpoint: {session_url}")
        response = requests.post(session_url, headers=headers, json=session_data)
        response.raise_for_status() # Raise an exception for bad statuses (4xx, 5xx)
        print(f"Session update response: {response.status_code}")
    except requests.exceptions.HTTPError as e:
        print(f"Error updating session: {e.response.status_code} {e.response.text}")
        # This could be a 4xx or 5xx. We'll return 502 (Bad Gateway).
        return f"Failed to update session: {e.response.text}", 502
    except Exception as e:
        print(f"Error calling session API: {e}")
        return "Session call failed", 500
    
    # 6. Call the second endpoint (Run SSE)
    # This sends the GCS URI to the agent
    prompt_url=TARGET_APP_URL+'/run_sse'
    prompt_data ={
        "app_name": "test_agents",
        "user_id": f"{user_id}",
        "session_id":f"{session_id}",
        "new_message": {
            "role": "user",
            "parts": [{
            "text": gcs_uri
            }]
        },
        "streaming": False
    }
    try:
        print(f"Calling run_sse endpoint: {prompt_url}")
        response = requests.post(prompt_url, headers=headers, json=prompt_data)
        response.raise_for_status()
        print(f"Run SSE response: {response.status_code}, Body: {response.text}")
    except requests.exceptions.HTTPError as e:
        print(f"Error running SSE: {e.response.status_code} {e.response.text}")
        return f"Failed to run SSE: {e.response.text}", 502
    except Exception as e:
        print(f"Error calling Run SSE API: {e}")
        return "Run SSE call failed", 500
    
    print(f"Successfully processed file: {gcs_uri}")
    return "OK", 200