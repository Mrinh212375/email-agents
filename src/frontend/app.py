"""Streamlit UI: one tab per assignment part, each building on the previous one.

Part 1: paste an email -> writer agent replies
Part 2: newest Gmail inbox email -> writer agent replies
Part 3: reader agent reads today's emails and categorises them
Part 4: reader agent passes its analysis to the writer agent -> replies to every email that needs action,
        saved as Gmail drafts

Run from the project root:  streamlit run src/frontend/app.py
"""

import html
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `backend` / `mcp_server` importable
load_dotenv()

st.set_page_config(page_title="Email Agents", page_icon="✉️", layout="wide")

# Compact page so the input + result fit on one screen.
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.2rem; padding-bottom: 0.5rem; max-width: 1300px;}
      header[data-testid="stHeader"] {height: 0; background: transparent;}
      [data-testid="stDecoration"] {display: none;}
      h1 {padding-top: 0 !important; margin-bottom: 0 !important;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("✉️ Email Agents")

if not os.getenv("OPENAI_API_KEY"):
    st.warning("`OPENAI_API_KEY` is empty. Add it to the `.env` file, then restart the app.")
    st.stop()

from backend.workflow import run_part1, run_part2, run_part3, run_part4  # noqa: E402


# =====================================================================
# Helpers
# =====================================================================
def describe_error(exc: BaseException) -> str:
    """Turn errors (incl. MCP ExceptionGroups) into a readable message."""
    while getattr(exc, "exceptions", None):  # ExceptionGroup (works on Python 3.10 too)
        exc = exc.exceptions[0]
    if type(exc).__name__ in ("ConnectError", "ConnectionRefusedError"):
        return "Gmail MCP server is not running. Start it with `python src/mcp_server/start_server.py`."
    return str(exc)


def now() -> str:
    return datetime.now().strftime("%d %b %Y, %H:%M:%S")


def show_fetched_at(result: dict) -> None:
    """Show when this result was produced (each button click fetches live data again)."""
    st.caption(f"🕒 Fetched at {result['fetched_at']}. Click the button again to refresh.")


def estimate_lines(text: str, chars_per_line: int = 62) -> int:
    return sum(max(1, math.ceil(len(line) / chars_per_line)) for line in text.splitlines() or [""])


def sender_name(sender: str) -> str:
    """'"Jane Doe" <jane@x.com>'  ->  'Jane Doe'"""
    name = re.sub(r"\s*<[^>]*>", "", sender).strip().strip('"')
    return name or sender


def esc(text: str) -> str:
    return html.escape(text or "")


CARD_CSS = """
  * { box-sizing: border-box; }
  body { margin: 0; font-family: "Segoe UI", system-ui, -apple-system, sans-serif; background: transparent; }
  #card { background: #f4f6fb; border-radius: 16px; padding: 18px; }
  .head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
  .brand { font-size: 18px; font-weight: 700; color: #1f2a44; }
  .tag { font-size: 12px; color: #4a5a85; background: #e2e8f7; border-radius: 999px; padding: 4px 10px; }
  .stats { font-size: 14px; color: #33415c; margin: -4px 0 14px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
  .panel { background: #fff; border-radius: 12px; padding: 14px 16px;
           box-shadow: 0 1px 3px rgba(20, 30, 60, .08); border-top: 4px solid var(--accent); }
  .label { font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
           color: var(--accent); margin-bottom: 8px; }
  .text { white-space: pre-wrap; word-wrap: break-word; font-size: 14.5px; line-height: 1.55; color: #1d1d1f; }
  .email { --accent: #5b6b8c; }
  .reply { --accent: #1f9d6b; }
  .action { --accent: #d9534f; }
  .noaction { --accent: #8a94a6; }
  .item { border-bottom: 1px solid #eef0f5; padding: 9px 0; }
  .item:last-child { border-bottom: 0; }
  .subj { font-size: 14.5px; font-weight: 600; color: #1d1d1f; }
  .from { font-size: 12.5px; color: #6b7280; margin: 1px 0 4px; }
  .sum { font-size: 14px; color: #33415c; line-height: 1.45; }
  .note { font-size: 13.5px; margin-top: 4px; line-height: 1.45; }
  .note.todo { color: #b02a26; }
  .note.why { color: #6b7280; }
  .context { background: #fff4f3; border-left: 3px solid #d9534f; border-radius: 6px; padding: 6px 10px;
             font-size: 13.5px; color: #8a2a26; margin: 6px 0 10px; line-height: 1.45; }
  .empty { font-size: 14px; color: #6b7280; padding: 6px 0; }
  .saved { font-size: 13px; color: #1f7a55; background: #eaf7f1; border-radius: 6px;
           padding: 6px 10px; margin-top: 12px; }
"""


def show_card(inner_html: str, height: int) -> None:
    page = f'<!doctype html><html><head><meta charset="utf-8"><style>{CARD_CSS}</style></head>' \
           f'<body><div id="card">{inner_html}</div></body></html>'
    components.html(page, height=min(max(height, 220), 4000), scrolling=True)


def card_head(brand: str, tag: str) -> str:
    return f'<div class="head"><div class="brand">{brand}</div><div class="tag">{esc(tag)}</div></div>'


# =====================================================================
# Result cards
# =====================================================================
def render_reply_card(email: str, reply: str, email_label: str, tag: str) -> None:
    """Part 1 & 2: received email | generated reply."""
    body = card_head("✉️ Writer Agent", tag) + (
        '<div class="grid">'
        f'<div class="panel email"><div class="label">{esc(email_label)}</div><div class="text">{esc(email)}</div></div>'
        f'<div class="panel reply"><div class="label">✍️ Generated reply</div><div class="text">{esc(reply)}</div></div>'
        '</div>'
    )
    show_card(body, max(estimate_lines(email), estimate_lines(reply)) * 23 + 150)


def email_item(email: dict, note: str, note_class: str, show_summary: bool) -> str:
    summary = f'<div class="sum">{esc(email["summary"])}</div>' if show_summary else ""
    return (
        f'<div class="item"><div class="subj">{esc(email["subject"])}</div>'
        f'<div class="from">{esc(sender_name(email["sender"]))}</div>'
        f'{summary}<div class="note {note_class}">{esc(note)}</div></div>'
    )


def item_height(email: dict, note: str, show_summary: bool) -> int:
    summary_lines = estimate_lines(email["summary"], 55) if show_summary else 0
    return 58 + 21 * (estimate_lines(email["subject"], 55) - 1 + summary_lines + estimate_lines(note, 55))


def render_reader_card(emails: list[dict]) -> None:
    """Part 3: emails split into 'needs action' and 'no action needed'."""
    action = [e for e in emails if e["needs_action"]]
    no_action = [e for e in emails if not e["needs_action"]]

    action_html = "".join(email_item(e, f"➡ {e['action_required']}", "todo", True) for e in action) \
        or '<div class="empty">Nothing needs your action today 🎉</div>'
    no_action_html = "".join(email_item(e, e["reason"], "why", False) for e in no_action) \
        or '<div class="empty">No emails in this category.</div>'

    body = card_head("📖 Reader Agent", "LangGraph · Gmail MCP") + (
        f'<div class="stats">📬 <b>{len(emails)}</b> emails in the last 24 hours &nbsp;·&nbsp; '
        f'🔴 <b>{len(action)}</b> need action &nbsp;·&nbsp; ⚪ <b>{len(no_action)}</b> no action needed</div>'
        '<div class="grid">'
        f'<div class="panel action"><div class="label">🔴 Need action ({len(action)})</div>{action_html}</div>'
        f'<div class="panel noaction"><div class="label">⚪ Does not need action ({len(no_action)})</div>{no_action_html}</div>'
        '</div>'
    )
    left = sum(item_height(e, e["action_required"], True) for e in action)
    right = sum(item_height(e, e["reason"], False) for e in no_action)
    show_card(body, max(left, right, 60) + 190)


DRAFT_SAVED_NOTE = "📝 Reply saved in Drafts. Please check the draft by logging in to your Gmail."


def saved_note(item: dict) -> str:
    """Confirm the draft only when Gmail returned a draft ID."""
    if item.get("draft_id"):
        return f'<div class="saved">{DRAFT_SAVED_NOTE}</div>'
    return '<div class="saved" style="color:#b02a26;background:#fff4f3">⚠️ Draft was not saved in Gmail.</div>'


def render_workflow_card(emails: list[dict], replies: list[dict]) -> None:
    """Part 4: reader analysis -> writer draft (saved in Gmail), for every email that needs action."""
    skipped = [e for e in emails if not e["needs_action"]]
    body = card_head("🔗 Reader → Writer", "LangGraph · Gmail MCP") + (
        f'<div class="stats">📖 Reader: <b>{len(emails)}</b> emails today, <b>{len(replies)}</b> need action '
        f'&nbsp;→&nbsp; ✍️ Writer: <b>{len(replies)}</b> drafts saved in Gmail &nbsp;·&nbsp; '
        f'⚪ {len(skipped)} skipped (no action needed)</div>'
    )
    height = 120
    if not replies:
        body += '<div class="empty">No emails need your action today 🎉</div>'
    for item in replies:
        email, reply = item["email"], item["reply"]
        excerpt = email["body"][:600] + ("…" if len(email["body"]) > 600 else "")
        body += (
            '<div class="grid">'
            f'<div class="panel email"><div class="label">📩 {esc(sender_name(email["sender"]))}</div>'
            f'<div class="subj">{esc(email["subject"])}</div>'
            f'<div class="context">🧠 <b>Reader context:</b> {esc(email["action_required"])}</div>'
            f'<div class="text">{esc(excerpt)}</div></div>'
            f'<div class="panel reply"><div class="label">✍️ Generated draft</div><div class="text">{esc(reply)}</div>'
            f'{saved_note(item)}</div>'
            '</div>'
        )
        left = estimate_lines(excerpt) * 23 + estimate_lines(email["action_required"], 55) * 21 + 70
        height += max(left, estimate_lines(reply) * 23 + 90) + 40
    show_card(body, height)


# =====================================================================
# Tabs: one per assignment part
# =====================================================================
part1, part2, part3, part4 = st.tabs([
    "Part 1 · Paste an email",
    "Part 2 · Reply from Gmail inbox",
    "Part 3 · Reader agent",
    "Part 4 · Reader → Writer",
])

SERVER_HINT = "Start the server first: `python src/mcp_server/start_server.py`"

# ---------- Part 1 ----------
with part1:
    st.caption("Paste an email below and the LangGraph writer agent will draft a reply.")
    email_body = st.text_area("Email body", height=120, placeholder="Paste email here", label_visibility="collapsed")

    if st.button("Generate reply", type="primary"):
        if not email_body.strip():
            st.error("Please paste an email body first.")
        else:
            with st.spinner("Writing reply..."):
                try:
                    st.session_state["part1"] = {**run_part1(email_body), "fetched_at": now()}
                except Exception as exc:
                    st.session_state.pop("part1", None)
                    st.error(f"Could not generate a reply: {describe_error(exc)}")

    if "part1" in st.session_state:
        show_fetched_at(st.session_state["part1"])
        result = st.session_state["part1"]
        render_reply_card(result["email_body"].strip(), result["reply"], "📩 Received email", "LangGraph")

# ---------- Part 2 ----------
with part2:
    st.caption(f"Reads the newest email in your Gmail inbox through the Gmail MCP server and drafts a reply. {SERVER_HINT}")

    if st.button("Fetch first email & reply", type="primary"):
        with st.spinner("Reading your inbox and writing a reply..."):
            try:
                st.session_state["part2"] = {**run_part2(), "fetched_at": now()}
            except Exception as exc:
                st.session_state.pop("part2", None)
                st.error(f"Could not reply to the first email: {describe_error(exc)}")

    if "part2" in st.session_state:
        show_fetched_at(st.session_state["part2"])
        result = st.session_state["part2"]
        render_reply_card(result["email_body"], result["reply"], "📥 First inbox email", "LangGraph · Gmail MCP")

# ---------- Part 3 ----------
with part3:
    st.caption(
        "The reader agent reads all emails from the last 24 hours and sorts them into "
        f"**need action** and **does not need action**. {SERVER_HINT}"
    )

    if st.button("Read today's emails", type="primary"):
        with st.spinner("Reading and categorising today's emails..."):
            try:
                st.session_state["part3"] = {**run_part3(), "fetched_at": now()}
            except Exception as exc:
                st.session_state.pop("part3", None)
                st.error(f"Could not read today's emails: {describe_error(exc)}")

    if "part3" in st.session_state:
        show_fetched_at(st.session_state["part3"])
        render_reader_card(st.session_state["part3"]["emails"])

# ---------- Part 4 ----------
with part4:
    st.caption(
        "Full workflow: the reader agent categorises today's emails and passes its analysis to the writer agent, "
        f"which writes a reply for every email that needs action and saves it as a Gmail draft. {SERVER_HINT}"
    )

    if st.button("Read emails & write replies", type="primary"):
        with st.spinner("Reader is categorising, writer is drafting replies..."):
            try:
                st.session_state["part4"] = {**run_part4(), "fetched_at": now()}
            except Exception as exc:
                st.session_state.pop("part4", None)
                st.error(f"Could not run the workflow: {describe_error(exc)}")

    if "part4" in st.session_state:
        show_fetched_at(st.session_state["part4"])
        result = st.session_state["part4"]
        render_workflow_card(result["emails"], result["replies"])
