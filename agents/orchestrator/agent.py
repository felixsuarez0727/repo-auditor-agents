import os
import re
import ast
import httpx
from dotenv import load_dotenv
from google.adk import Agent

# Load environment variables
load_dotenv()

# Force use of Application Default Credentials (ADC) in production (Vertex AI / Agent Runtime)
# by deleting GOOGLE_API_KEY if running in a GCP managed environment.
if os.getenv("AIP_PREDICTION_URI") or os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_JOB"):
    if "GOOGLE_API_KEY" in os.environ:
        del os.environ["GOOGLE_API_KEY"]

GITHUB_API_URL = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

def get_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "GitHub-MCP-Server-Python",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers

# In-memory cache to store file contents and avoid redundant network requests
_file_cache = {}

async def _fetch_file_content(owner: str, repo: str, path: str) -> str:
    key = f"{owner}/{repo}/{path}"
    if key in _file_cache:
        return _file_cache[key]
    
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}"
    headers = get_headers()
    headers["Accept"] = "application/vnd.github.raw"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Error reading file {path} ({response.status_code}): {response.text}")
        content = response.text
        _file_cache[key] = content
        return content

# --- Core Repository Tools ---

async def get_repo_metadata(owner: str, repo: str) -> dict:
    """
    Retrieves basic repository metadata (name, description, main language, stars, forks).
    
    Args:
        owner: The owner of the repository.
        repo: The name of the repository.
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_headers())
        if response.status_code != 200:
            return {"error": f"Error fetching metadata ({response.status_code}): {response.text}"}
        
        data = response.json()
        return {
            "name": data.get("name"),
            "description": data.get("description"),
            "language": data.get("language"),
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "default_branch": data.get("default_branch")
        }

async def list_repo_files(owner: str, repo: str, path: str = "") -> list:
    """
    Lists files and directories in the repository at the specified path.
    
    Args:
        owner: The owner of the repository.
        repo: The name of the repository.
        path: The path within the repository (leave empty for root).
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_headers())
        if response.status_code != 200:
            raise Exception(f"Error listing files ({response.status_code}): {response.text}")
        
        data = response.json()
        if not isinstance(data, list):
            return [{"name": data.get("name"), "path": data.get("path"), "type": "file"}]
        
        result = []
        for item in data:
            result.append({
                "name": item.get("name"),
                "path": item.get("path"),
                "type": item.get("type"),
                "size": item.get("size")
            })
        return result

async def read_file_content(owner: str, repo: str, path: str) -> str:
    """
    Reads and returns the content of a specific file in the repository (and caches it).
    
    Args:
        owner: The owner of the repository.
        repo: The name of the repository.
        path: The path to the file.
    """
    return await _fetch_file_content(owner, repo, path)

# --- Analysis Tools (Refactored to accept owner, repo, path parameters to avoid giant payloads) ---

async def scan_code_for_secrets(owner: str, repo: str, path: str) -> list:
    """
    Scans a Python or requirements.txt file in the repository for secrets (AWS keys, GitHub tokens, passwords).
    
    Args:
        owner: The owner of the repository.
        repo: The name of the repository.
        path: The path to the file to scan.
    """
    code = await _fetch_file_content(owner, repo, path)
    
    patterns = {
        "AWS API Key": r"(?:AKIA|ASCA|AAAA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}",
        "GitHub Token": r"(?:ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9]{82})",
        "Generic Secret/Password Assignment": r"(?:api_key|apikey|secret|password|passwd|token|credential|private_key)\s*=\s*['\"]([a-zA-Z0-9_\-\.\+=/]{10,})['\"]",
        "Google API Key": r"AIza[yA-Z0-9_\-]{35}",
    }
    
    results = []
    lines = code.splitlines()
    
    for i, line in enumerate(lines, 1):
        clean_line = line.split('#')[0].strip()
        for name, pattern in patterns.items():
            matches = re.finditer(pattern, clean_line, re.IGNORECASE if "Assignment" in name else 0)
            for match in matches:
                val = match.group(1) if len(match.groups()) > 0 else match.group(0)
                val_lower = val.lower()
                if "Assignment" in name:
                    if any(p in val_lower for p in ["getenv", "environ", "os.get", "config", "your_", "placeholder", "xxx", "env("]):
                        continue
                
                results.append({
                    "file": path,
                    "type": name,
                    "line": i,
                    "content_preview": line.strip()[:100],
                    "severity": "HIGH" if name in ["AWS API Key", "GitHub Token", "Google API Key"] else "MEDIUM"
                })
                
    return results

async def get_latest_pypi_version(package_name: str) -> dict:
    """
    Queries the public PyPI API to get the latest available version of a Python package.
    
    Args:
        package_name: The name of the Python package.
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

async def analyze_missing_docstrings(owner: str, repo: str, path: str) -> list:
    """
    Parses a Python file in the repository to locate public classes and functions lacking docstrings.
    
    Args:
        owner: The owner of the repository.
        repo: The name of the repository.
        path: The path to the Python file.
    """
    code = await _fetch_file_content(owner, repo, path)
    results = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [{"type": "SyntaxError", "line": e.lineno, "name": "syntax_error", "message": str(e)}]
        
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith('_'):
                docstring = ast.get_docstring(node)
                if not docstring:
                    results.append({
                        "file": path,
                        "type": "Function",
                        "name": node.name,
                        "line": node.lineno
                    })
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith('_'):
                docstring = ast.get_docstring(node)
                if not docstring:
                    results.append({
                        "file": path,
                        "type": "Class",
                        "name": node.name,
                        "line": node.lineno
                    })
                    
    return results

async def get_public_functions_ast(owner: str, repo: str, path: str) -> list:
    """
    Extracts public functions and methods from a Python file to locate candidates for unit testing.
    
    Args:
        owner: The owner of the repository.
        repo: The name of the repository.
        path: The path to the Python file.
    """
    code = await _fetch_file_content(owner, repo, path)
    results = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [{"type": "SyntaxError", "line": e.lineno, "name": "syntax_error", "message": str(e)}]
        
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith('_'):
                args = [arg.arg for arg in node.args.args if arg.arg != 'self']
                results.append({
                    "file": path,
                    "name": node.name,
                    "line": node.lineno,
                    "arguments": args,
                    "is_async": isinstance(node, ast.AsyncFunctionDef)
                })
                
    return results

# System instructions for the orchestrator agent
INSTRUCTION = """
You are the orchestrator agent (orchestrator_agent) of the Repo Auditor project.
Your primary goal is to audit GitHub repositories. To do this, you have access to various repository extraction tools and Python analysis tools:
- Repository Tools: 'get_repo_metadata', 'list_repo_files', 'read_file_content'.
- Security Tools: 'scan_code_for_secrets' and 'get_latest_pypi_version'.
- Documentation Tools: 'analyze_missing_docstrings'.
- Test Tools: 'get_public_functions_ast'.

When the user provides a GitHub URL (in the format https://github.com/owner/repo), you must execute the following workflow:
1. Extract the 'owner' and 'repo' from the URL. If the URL is invalid, ask the user friendly for a valid URL.
2. Retrieve the repository's metadata using 'get_repo_metadata'.
3. List the repository files using 'list_repo_files' (starting at the root with an empty path).
4. Identify the relevant files to audit applying the following STRICT CONTEXT LIMIT RULES:
   - RULE 1: Only analyze Python files (.py) located in the main/root directory or the primary source directory (e.g., inside 'src/').
   - RULE 2: DO NOT enter recursively into test, example, or documentation directories such as 'tests/', 'examples/', 'docs/', 'testing/', etc. Ignore them entirely.
   - RULE 3: Read a STRICT MAXIMUM of 5 Python files (.py) in total. Prioritize the most important files based on size or core function names (e.g., entry points like __init__.py, core.py, main.py).
   - RULE 4: If you find a 'requirements.txt' file in the root directory, read it too (this does not count towards the 5 Python files limit).
5. For the selected files, retrieve their content using 'read_file_content' (this stores them in cache).
6. Run the code analysis tools directly on the selected files:
   - For all Python files (.py) and requirements.txt (if present): Run 'scan_code_for_secrets' by passing the 'owner', 'repo', and 'path' of the file.
   - For requirements.txt: For each package dependency detected in it, run 'get_latest_pypi_version' to check if there is a newer version.
   - For all Python files (.py): Run 'analyze_missing_docstrings' by passing the 'owner', 'repo', and 'path' of the file.
   - For all Python files (.py): Run 'get_public_functions_ast' by passing the 'owner', 'repo', and 'path' of the file.
7. Combine and synthesize all the analysis results along with the repository metadata into a single, unified, and highly professional audit report in Markdown format in English.

The unified report must include:
- **Repository Metadata**: Name, description, primary language, stars, forks, etc.
- **Project Structure**: Summary of files found and selected under the strict context rules.
- **Security Audit**: Details of found secrets, potential logical vulnerabilities, and outdated dependencies (comparing specified vs latest PyPI version).
- **Documentation Audit**: Summary of missing docstrings and comments, with code block suggestions of the proposed docstrings (Google or Sphinx style) ready to use.
- **Unit Test Coverage Audit**: List of public functions without tests, proposing pytest skeletons (with both Happy Path and Edge Cases) for each.
- **Overall Recommendations**: Actionable mitigation steps for all found issues.

Be rigorous, precise, and maintain a highly structured Markdown document in English.
"""

# Define the root orchestrator agent
root_agent = Agent(
    name="orchestrator_agent",
    model="gemini-2.5-pro",
    instruction=INSTRUCTION,
    tools=[
        get_repo_metadata,
        list_repo_files,
        read_file_content,
        scan_code_for_secrets,
        get_latest_pypi_version,
        analyze_missing_docstrings,
        get_public_functions_ast
    ]
)
