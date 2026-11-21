"""The one shared LLM instance. Every agent imports `llm` from here.

Configure it in the .env file at the project root:
    OPENAI_API_KEY=...
    OPENAI_MODEL=gpt-4o-mini
"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

llm = ChatOpenAI(model=MODEL_NAME, temperature=0.3)  # reads OPENAI_API_KEY from the environment
