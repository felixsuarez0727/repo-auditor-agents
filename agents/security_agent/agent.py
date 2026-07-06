import os
import re
import httpx
from dotenv import load_dotenv
from google.adk import Agent

# Load environment variables
load_dotenv()

# Tool 1: Scan python code for secrets using regex patterns
def scan_code_for_secrets(code: str) -> list:
    """
    Scans Python code for hardcoded secrets like API keys, tokens, and passwords using regex patterns.
    
    Args:
        code: The Python code content to analyze.
        
    Returns:
        A list of dictionaries representing found secrets, their approximate line, and severity.
    """
    patterns = {
        "AWS API Key": r"(?:AKIA|ASCA|AAAA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}",
        "GitHub Token": r"(?:ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9]{82})",
        "Generic Secret/Password Assignment": r"(?:api_key|apikey|secret|password|passwd|token|credential|private_key)\s*=\s*['\"]([a-zA-Z0-9_\-\.\+=/]{10,})['\"]",
        "Google API Key": r"AIza[yA-Z0-9_\-]{35}",
    }
    
    results = []
    lines = code.splitlines()
    
    for i, line in enumerate(lines, 1):
        # Exclude inline comments
        clean_line = line.split('#')[0].strip()
        for name, pattern in patterns.items():
            matches = re.finditer(pattern, clean_line, re.IGNORECASE if "Assignment" in name else 0)
            for match in matches:
                # If it's a generic assignment, ignore if it looks like a variable load
                val = match.group(1) if len(match.groups()) > 0 else match.group(0)
                val_lower = val.lower()
                if "Assignment" in name:
                    if any(p in val_lower for p in ["getenv", "environ", "os.get", "config", "your_", "placeholder", "xxx", "env("]):
                        continue
                
                results.append({
                    "type": name,
                    "line": i,
                    "content_preview": line.strip()[:100],
                    "severity": "HIGH" if name in ["AWS API Key", "GitHub Token", "Google API Key"] else "MEDIUM"
                })
                
    return results

# Tool 2: Check latest version of a python package on PyPI
async def get_latest_pypi_version(package_name: str) -> dict:
    """
    Queries the public PyPI API to get the latest available version of a Python package.
    
    Args:
        package_name: The name of the Python package to check.
        
    Returns:
        A dictionary with the latest package version, or an error if not found.
    """
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                return {
                    "package": package_name,
                    "latest_version": data.get("info", {}).get("version"),
                    "status": "success"
                }
            else:
                return {
                    "package": package_name,
                    "status": "error",
                    "message": f"Package not found on PyPI (status {response.status_code})"
                }
    except Exception as e:
        return {
            "package": package_name,
            "status": "error",
            "message": str(e)
        }

# System instructions for the security agent
INSTRUCTION = """
You are the security agent (security_agent) of the Repo Auditor project.
Your primary goal is to audit Python code snippets and requirements.txt files for security issues and outdated dependencies.

When the user provides a Python code snippet or the content of a requirements.txt file in plain text, you must:
1. Analyze the Python code:
   - Use the 'scan_code_for_secrets' tool to search for secrets, tokens, API keys, or exposed passwords using regular expressions.
   - Logically analyze the code for common vulnerabilities (such as the use of eval(), exec(), command injection via os.system(), insecure deserialization with pickle, etc.).
2. Analyze the requirements.txt:
   - For each dependency listed (e.g., fastapi==0.90.0 or requests>=2.20.0), extract the package name and specified version.
   - Use the 'get_latest_pypi_version' tool to find the latest version available on PyPI.
   - Compare the versions. If the specified version is significantly older than the latest available version, register it as an outdated dependency.
3. Generate a structured audit report in Markdown format in English with the following sections:
   - **Executive Summary**: A high-level summary of the issues found.
   - **Exposed Secrets and Credentials**: Detailed table of found secrets, approximate line number, secret type, and severity (HIGH for real tokens/API keys, MEDIUM for generic suspicious assignments).
   - **Code Vulnerabilities**: Detailed table of code vulnerabilities (like eval(), os.system()), approximate line, explanation, and severity (HIGH, MEDIUM, or LOW).
   - **Outdated Dependencies**: Detailed table comparing specified version with the latest PyPI version, and severity (LOW for minor updates, MEDIUM for major updates).
   - **Recommendations**: Clear mitigation steps for each of the issues found.

Be professional and comprehensive in your report.
"""

# Define the root_agent following ADK name conventions
root_agent = Agent(
    name="security_agent",
    model="gemini-2.5-pro",
    instruction=INSTRUCTION,
    tools=[scan_code_for_secrets, get_latest_pypi_version]
)
