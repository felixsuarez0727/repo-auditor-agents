import os
import ast
from dotenv import load_dotenv
from google.adk import Agent

# Load environment variables
load_dotenv()

# Tool: Use Python's AST module to identify public classes/functions lacking docstrings
def analyze_missing_docstrings(code: str) -> list:
    """
    Parses Python code using the Abstract Syntax Tree (AST) to find public classes and functions lacking docstrings.
    
    Args:
        code: The Python source code to analyze.
        
    Returns:
        A list of dictionaries describing public elements without a docstring, including their name, type (function/class), and line number.
    """
    results = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [{"type": "SyntaxError", "line": e.lineno, "name": "syntax_error", "message": str(e)}]
        
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Check if it is a public function (doesn't start with underscore)
            if not node.name.startswith('_'):
                docstring = ast.get_docstring(node)
                if not docstring:
                    results.append({
                        "type": "Function",
                        "name": node.name,
                        "line": node.lineno
                    })
        elif isinstance(node, ast.ClassDef):
            # Check if it is a public class
            if not node.name.startswith('_'):
                docstring = ast.get_docstring(node)
                if not docstring:
                    results.append({
                        "type": "Class",
                        "name": node.name,
                        "line": node.lineno
                    })
                    
    return results

# System instructions for the documentation agent
INSTRUCTION = """
You are the documentation agent (docs_agent) of the Repo Auditor project.
Your primary goal is to audit Python code and suggest improvements to the documentation (docstrings and comments).

When the user provides a Python code snippet or README file in plain text, you must:
1. Analyze the Python code:
   - Use the 'analyze_missing_docstrings' tool to get the exact list of public functions and classes without docstrings.
   - Analyze if the file lacks an overall explanatory module docstring at the top.
   - Analyze if there are complex blocks of code inside functions that require inline explanatory comments.
2. Propose improvements:
   - For each public class or function identified without a docstring, draft a clear and concise docstring proposal (following Google or Sphinx style, in English) explaining what it does, its arguments, and its return values.
   - If the module docstring is missing, write an appropriate one.
3. Analyze README:
   - If a README file is provided, evaluate if it is missing or very sparse. Propose improvements or a complete README structure including: Introduction, Prerequisites, Installation, Usage, and License.
4. Generate a structured audit report in Markdown format in English with the following sections:
   - **Documentation Coverage Summary**: Overall analysis of the documentation status.
   - **Suggested Documentation Improvements**: Detailed table of public elements without a docstring, their line number, and the drafted docstring proposal ready to be copied and pasted.
   - **Module / File Docstring**: If applicable, the module docstring proposal for the top of the file.
   - **README Improvements**: If applicable, suggestions to improve the README.

Be precise, technical, and clear in your suggestions.
"""

# Define the root_agent following ADK name conventions
root_agent = Agent(
    name="docs_agent",
    model="gemini-2.5-pro",
    instruction=INSTRUCTION,
    tools=[analyze_missing_docstrings]
)
