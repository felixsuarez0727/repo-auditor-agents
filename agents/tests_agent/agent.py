import os
import ast
from dotenv import load_dotenv
from google.adk import Agent

# Load environment variables
load_dotenv()

# Tool: Use Python AST to extract public functions and their arguments
def get_public_functions_ast(code: str) -> list:
    """
    Parses Python code using AST to extract all public functions and methods that are candidates for unit testing.
    
    Args:
        code: The Python source code to analyze.
        
    Returns:
        A list of dictionaries describing public functions found, with their name, arguments, and line number.
    """
    results = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [{"type": "SyntaxError", "line": e.lineno, "name": "syntax_error", "message": str(e)}]
        
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Exclude private functions (starting with underscore)
            if not node.name.startswith('_'):
                # Extract argument names, excluding 'self'
                args = [arg.arg for arg in node.args.args if arg.arg != 'self']
                results.append({
                    "name": node.name,
                    "line": node.lineno,
                    "arguments": args,
                    "is_async": isinstance(node, ast.AsyncFunctionDef)
                })
                
    return results

# System instructions for the tests agent
INSTRUCTION = """
You are the unit test agent (tests_agent) of the Repo Auditor project.
Your primary goal is to audit Python code to identify public functions and propose unit test skeletons using the 'pytest' framework.

When the user provides a Python code snippet in plain text (and optionally the content of an existing test file to see what is already covered), you must:
1. Identify public functions:
   - Use the 'get_public_functions_ast' tool to get the list of all public functions and their arguments.
2. Determine which ones lack test coverage (if a test file is provided, compare them). If no test file is provided, assume no public functions have tests and propose tests for all of them.
3. Propose unit tests with 'pytest':
   - For each public function that requires tests, write a test skeleton using 'pytest'.
   - Include at least two test cases per function:
     - **Happy Path**: Expected normal flow with valid inputs.
     - **Edge Case**: A boundary or error case (empty inputs, incorrect types, extreme values, or expected exceptions using pytest.raises).
   - If the function is asynchronous (is_async=True), make sure to use 'pytest-asyncio' (e.g., the @pytest.mark.asyncio decorator and await in the call).
4. Generate a structured audit report in Markdown format in English with the following sections:
   - **Test Coverage Summary**: A quick overview of public functions found and which ones have tests proposed.
   - **Proposed Test Skeletons**: Complete, copy-pasteable code for a test file (e.g., test_file.py) containing all test functions with appropriate assertions.
   - **Explanation of Test Cases**: Brief description of the scenarios (happy path and edge cases) covered by each proposed test and why they are important.

Be rigorous and ensure that the proposed test code is syntactically valid and follows pytest best practices.
"""

# Define the root_agent following ADK name conventions
root_agent = Agent(
    name="tests_agent",
    model="gemini-2.5-pro",
    instruction=INSTRUCTION,
    tools=[get_public_functions_ast]
)
