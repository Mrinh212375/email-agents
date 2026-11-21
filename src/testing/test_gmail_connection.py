"""Check the connection to the Gmail MCP server (real Gmail, no LLM).

1. Start the server in another terminal:  python src/mcp_server/start_server.py
2. Run from the project root:             python src/testing/test_gmail_connection.py

It lists the Gmail tools, then prints the 3 latest inbox emails (sender + subject).
The first time, you get a Google sign-in link: open it, approve, then run this script again.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_server.gmail_client import GMAIL_MCP_URL, fetch_emails, list_tool_names  # noqa: E402


async def main() -> None:
    print(f"Connecting to {GMAIL_MCP_URL} ...")
    tools = await list_tool_names()
    print(f"Connected. {len(tools)} Gmail tools: {', '.join(tools)}\n")

    print("Latest 3 inbox emails:")
    for email in await fetch_emails("in:inbox", max_emails=3):
        print(f"  - {email['subject']}  (from {email['sender']})")


if __name__ == "__main__":
    asyncio.run(main())
