import os
from dotenv import load_dotenv
from google.adk import Agent

# Load environment variables (such as GOOGLE_API_KEY)
load_dotenv()

root_agent = Agent(
    name="root_agent",
    model="gemini-2.5-pro",
    instruction=(
        "You are a test agent from Google's Agent Development Kit (ADK). "
        "Your only task is to greet the user friendly and briefly explain "
        "that you are a test agent created to verify that the development environment "
        "and project setup are working correctly."
    )
)
