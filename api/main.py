import os
import re
import secrets
import uuid
import time
import traceback
from collections import defaultdict
from datetime import datetime
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables (contains GITHUB_TOKEN and GOOGLE_API_KEY)
load_dotenv()

# Import the orchestrator agent and InMemoryRunner from google.adk
from google.adk.runners import InMemoryRunner
from agents.orchestrator import root_agent as orchestrator_agent
from google.genai import types

# Initialize FastAPI app
app = FastAPI(title="Repo Auditor API", version="1.0.0")

# Initialize the ADK Runner as a long-lived object
runner = InMemoryRunner(agent=orchestrator_agent, app_name="orchestrator")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
AUDIT_API_KEY = os.getenv("AUDIT_API_KEY")

# --- Security Measure 2: Basic In-Memory Rate Limiting ---
# Store request timestamps per IP address to prevent abuse and API exhaustion.
# We limit to a maximum of 5 requests per minute per client IP.
_rate_limit_records = defaultdict(list)

def is_rate_limited(ip: str) -> bool:
    current_time = time.time()
    # Retain only timestamps from the last 60 seconds
    _rate_limit_records[ip] = [t for t in _rate_limit_records[ip] if current_time - t < 60]
    
    if len(_rate_limit_records[ip]) >= 5:
        return True
    
    _rate_limit_records[ip].append(current_time)
    return False


# --- Security Measure 3: Sensitive Information Sanitization (DLP) ---
# Inspects and sanitizes the final generated report before sending it to the client.
# This prevents accidental leakage of system secrets, such as API keys or GitHub tokens.
def sanitize_report(report_text: str) -> str:
    if not report_text:
        return report_text
        
    # Redact GitHub Token if it appears in the report
    if GITHUB_TOKEN and GITHUB_TOKEN in report_text:
        report_text = report_text.replace(GITHUB_TOKEN, "[REDACTED_GITHUB_TOKEN]")
        
    # Redact Google API Key if it appears in the report
    if GOOGLE_API_KEY and GOOGLE_API_KEY in report_text:
        report_text = report_text.replace(GOOGLE_API_KEY, "[REDACTED_GOOGLE_API_KEY]")
        
    return report_text


class AuditRequest(BaseModel):
    repo_url: str

class AuditResponse(BaseModel):
    repo_url: str
    report: str
    generated_at: str

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/audit", response_model=AuditResponse)
async def audit_repository(request: AuditRequest, fastapi_req: Request, x_api_key: str | None = Header(default=None)):
    # --- Security Measure 2: Check Rate Limit ---
    # Retrieve client IP to enforce rate limiting
    client_ip = fastapi_req.client.host if fastapi_req.client else "unknown"
    if is_rate_limited(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 5 requests per minute per IP are allowed."
        )

    # --- Security Measure 0: API key authentication ---
    if not AUDIT_API_KEY:
        raise HTTPException(status_code=503, detail="Server API key is not configured.")
    if not x_api_key or not secrets.compare_digest(x_api_key, AUDIT_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")

    repo_url = request.repo_url.strip()
    if not repo_url:
        raise HTTPException(status_code=400, detail="repo_url field cannot be empty.")
    
    # --- Security Measure 1: Input URL Validation ---
    # Restrict input to GitHub repository URLs (https://github.com/<owner>/<repo>).
    # This prevents SSRF (Server-Side Request Forgery) and invalid tool invocations.
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?(?:[/?#].*)?", repo_url)
    if not match:
        raise HTTPException(
            status_code=400,
            detail="Invalid repository URL. Use 'https://github.com/<owner>/<repo>'."
        )
    repo_url = f"https://github.com/{match[1]}/{match[2]}"
    
    # Generate unique session ID for isolation on concurrent requests
    session_id = str(uuid.uuid4())
    user_id = "api_client"
    app_name = "orchestrator"
    
    # Explicitly register the session in ADK's session service before executing the agent loop
    try:
        await runner.session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create ADK session: {str(e)}")
    
    # Construct types.Content object to avoid AttributeError: 'str' object has no attribute 'role'
    new_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=f"Analyze this repository: {repo_url}")]
    )
    
    report_content = ""
    try:
        # Run orchestrator agent programmatically using the ADK runner
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        report_content += part.text
                        
    except Exception as e:
        # Log the complete Python traceback to the server console/logs
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error auditing repository: {str(e)}")
    
    if not report_content:
        raise HTTPException(
            status_code=500,
            detail="The auditor agent failed to generate a report. Check logs for details."
        )
        
    # --- Security Measure 3: Sanitize the output before returning to client ---
    sanitized_report = sanitize_report(report_content)
        
    return AuditResponse(
        repo_url=repo_url,
        report=sanitized_report,
        generated_at=datetime.utcnow().isoformat() + "Z"
    )
