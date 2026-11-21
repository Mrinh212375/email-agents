"""Talks to the local Gmail MCP server (streamable HTTP): reads emails and saves reply drafts.

Every email is a dict:  {"id", "thread_id", "sender", "subject", "date", "body"}

The server must be running first:  python src/mcp_server/start_server.py
"""

import asyncio
import os
import re

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

load_dotenv()

GMAIL_MCP_URL = os.getenv("GMAIL_MCP_URL", "http://localhost:8000/mcp")
USER_EMAIL = os.getenv("USER_GOOGLE_EMAIL", "")

mcp_client = MultiServerMCPClient(
    {"gmail": {"url": GMAIL_MCP_URL, "transport": "streamable_http"}}
)


# ---------- Public functions ----------
async def fetch_emails(query: str, max_emails: int) -> list[dict]:
    """Search Gmail (newest first) and return up to `max_emails` full emails."""
    async with mcp_client.session("gmail") as session:  # one connection for all calls
        tools = {tool.name: tool for tool in await load_mcp_tools(session)}
        found = await _search_messages(tools["search_gmail_messages"], query, max_emails)
        reads = [_read_email(tools["get_gmail_message_content"], mid, tid) for mid, tid in found]
        return list(await asyncio.gather(*reads))  # read all emails in parallel (order is kept)


async def save_reply_drafts(replies: list[dict]) -> list[str]:
    """Save each reply as a Gmail draft in the original email's thread. Returns the draft IDs.

    replies: [{"email": {...}, "reply": "..."}]
    """
    if not replies:
        return []
    async with mcp_client.session("gmail") as session:
        tools = {tool.name: tool for tool in await load_mcp_tools(session)}
        draft_ids = []
        for item in replies:
            email = item["email"]
            text = await _call(
                tools["draft_gmail_message"],
                thread_id=email["thread_id"],         # reply inside the original conversation
                to=sender_address(email["sender"]),
                body=item["reply"],
            )
            match = re.search(r"Draft ID:\s*(\S+)", text)
            if not match:
                raise RuntimeError(f"Gmail did not save the draft for '{email['subject']}': {text}")
            draft_ids.append(match.group(1))
        return draft_ids


def sender_address(sender: str) -> str:
    """'"Jane Doe" <jane@x.com>'  ->  'jane@x.com'"""
    match = re.search(r"<([^>]+)>", sender)
    return match.group(1) if match else sender.strip()


async def list_tool_names() -> list[str]:
    """Names of the Gmail tools the server offers (used by the connection test)."""
    return [tool.name for tool in await mcp_client.get_tools()]


def email_to_text(email: dict, max_body_chars: int = 3000) -> str:
    """Format an email as plain text for the LLM (long bodies are shortened)."""
    body = email["body"]
    if len(body) > max_body_chars:
        body = body[:max_body_chars] + "\n[...email shortened...]"
    return f"From: {email['sender']}\nSubject: {email['subject']}\nDate: {email['date']}\n\n{body}"


# ---------- Helpers ----------
async def _call(tool, **args) -> str:
    """Call an MCP tool and return its text. Raises if Google sign-in is needed."""
    if "user_google_email" in tool.args:
        args["user_google_email"] = USER_EMAIL
    result = await tool.ainvoke(args)
    if isinstance(result, list):  # list of content blocks -> plain text
        result = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in result)
    text = str(result)
    if "ACTION REQUIRED" in text or text.startswith("Error calling tool"):
        raise RuntimeError(text)  # e.g. Google sign-in needed: the message contains the link
    return text


async def _search_messages(search_tool, query: str, max_emails: int) -> list[tuple[str, str]]:
    """Collect (message ID, thread ID) pairs page by page until `max_emails` or no more results."""
    found, page_token = [], None
    while len(found) < max_emails:
        args = {"query": query, "page_size": min(25, max_emails - len(found))}
        if page_token:
            args["page_token"] = page_token
        text = await _call(search_tool, **args)

        new = re.findall(r"Message ID:\s*(\S+)[\s\S]*?Thread ID:\s*(\S+)", text)
        found += new
        next_page = re.search(r"page_token='([^']+)'", text)
        if not new or not next_page:
            break
        page_token = next_page.group(1)
    return found[:max_emails]


async def _read_email(content_tool, message_id: str, thread_id: str) -> dict:
    """Read one email and split it into sender / subject / date / body."""
    text = await _call(content_tool, message_id=message_id)
    body = text.split("--- BODY ---", 1)[-1].split("--- ATTACHMENTS ---", 1)[0].strip()
    return {
        "id": message_id,
        "thread_id": thread_id,
        "sender": _header(text, "From"),
        "subject": _header(text, "Subject"),
        "date": _header(text, "Date"),
        "body": body,
    }


def _header(text: str, name: str) -> str:
    match = re.search(rf"^{name}:\s*(.*)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""
