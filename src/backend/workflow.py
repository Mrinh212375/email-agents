"""All LangGraph workflows, one per assignment part. Each part builds on the previous one.

Part 1:  START -> writer -> END                                       (reply to a pasted email)
Part 2:  START -> fetch_latest_email -> writer -> END                 (reply to the newest inbox email)
Part 3:  START -> read_emails -> categorize_emails -> END             (reader agent)
Part 4:  START -> read_emails -> categorize_emails -> write_replies -> save_drafts -> END
         (reader agent passes its analysis to the writer agent, which replies to every
          email that needs action from me; each reply is saved as a Gmail draft)
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.agents.reader import categorize_emails, read_today_emails
from backend.agents.writer import write_reply
from mcp_server.gmail_client import email_to_text, fetch_emails, save_reply_drafts


# ---------- Shared state (each part uses the fields it needs) ----------
class EmailState(TypedDict, total=False):
    email_body: str       # Part 1-2: the email to reply to
    reply: str            # Part 1-2: the generated reply
    emails: list[dict]    # Part 3-4: today's emails (+ the reader's analysis after categorize)
    replies: list[dict]   # Part 4:   [{"email": {...}, "reply": "...", "draft_id": "..."}] for emails needing action


# ---------- Nodes ----------
def writer_node(state: EmailState) -> dict:
    """Writer agent: reply to one email."""
    return {"reply": write_reply(state["email_body"])}


async def fetch_latest_email_node(state: EmailState) -> dict:
    """Get the newest email in the inbox (Part 2)."""
    emails = await fetch_emails("in:inbox", max_emails=1)
    if not emails:
        raise RuntimeError("No email found in the inbox.")
    return {"email_body": email_to_text(emails[0])}


async def read_emails_node(state: EmailState) -> dict:
    """Reader agent, step 1: read all emails from today."""
    return {"emails": await read_today_emails()}


def categorize_emails_node(state: EmailState) -> dict:
    """Reader agent, step 2: needs action from me / does not need action from me."""
    return {"emails": categorize_emails(state["emails"])}


def write_replies_node(state: EmailState) -> dict:
    """Writer agent: reply to every email that needs action, using the reader's analysis as context."""
    action_emails = [email for email in state["emails"] if email["needs_action"]]

    def reply_with_context(email: dict) -> str:
        reader_context = (
            f"Summary: {email['summary']}\n"
            f"Action needed from me: {email['action_required']}"
        )
        return write_reply(email_to_text(email), reader_context)

    with ThreadPoolExecutor(max_workers=5) as pool:  # write the replies in parallel
        replies = list(pool.map(reply_with_context, action_emails))
    return {"replies": [{"email": e, "reply": r} for e, r in zip(action_emails, replies)]}


async def save_drafts_node(state: EmailState) -> dict:
    """Save every reply as a Gmail draft (in the original email's thread)."""
    draft_ids = await save_reply_drafts(state["replies"])
    return {"replies": [{**item, "draft_id": d} for item, d in zip(state["replies"], draft_ids)]}


# ---------- Graphs ----------
def build_graph(*steps):
    """Build a straight-line graph: START -> step 1 -> step 2 -> ... -> END."""
    graph = StateGraph(EmailState)
    previous = START
    for name, node in steps:
        graph.add_node(name, node)
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    return graph.compile()


part1_graph = build_graph(("writer", writer_node))

part2_graph = build_graph(("fetch_latest_email", fetch_latest_email_node), ("writer", writer_node))

part3_graph = build_graph(("read_emails", read_emails_node), ("categorize_emails", categorize_emails_node))

part4_graph = build_graph(
    ("read_emails", read_emails_node),
    ("categorize_emails", categorize_emails_node),
    ("write_replies", write_replies_node),
    ("save_drafts", save_drafts_node),
)


# ---------- Run helpers (used by the Streamlit app and the tests) ----------
def run_part1(email_body: str) -> dict:
    return part1_graph.invoke({"email_body": email_body})


def run_part2() -> dict:
    return asyncio.run(part2_graph.ainvoke({}))


def run_part3() -> dict:
    return asyncio.run(part3_graph.ainvoke({}))


def run_part4() -> dict:
    return asyncio.run(part4_graph.ainvoke({}))
