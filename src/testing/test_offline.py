"""Offline tests for Parts 1-4 and the Streamlit app.

No API key, no Gmail and no MCP server needed: the LLM and the Gmail MCP tools are replaced with fakes.
The real parsing code, agents and LangGraph workflows still run.

Run from the project root:  python src/testing/test_offline.py
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))

import os  # noqa: E402

os.environ.setdefault("OPENAI_API_KEY", "offline-test")  # the LLM is faked below

from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402

from backend import workflow  # noqa: E402
from backend.agents import reader, writer  # noqa: E402
from mcp_server import gmail_client  # noqa: E402

# ---------------------------------------------------------------------------
# Fake inbox (text shaped exactly like workspace-mcp 2.6.0 tool output)
# ---------------------------------------------------------------------------
FAKE_EMAILS = {
    "m1": ("Priya Sharma <priya@example.com>", "Q1 timeline call",
           "Hi, are you free for a 30-minute call next week? Please send the requirements doc."),
    "m2": ("Deals Weekly <news@deals.com>", "Black Friday: 50% off",
           "Huge savings this week only. Unsubscribe anytime."),
    "m3": ("Rahul (Manager) <rahul@example.com>", "Approve the budget by Friday",
           "Can you review and approve the Q1 budget sheet by Friday?"),
}


def fake_search_output(ids, next_token=None):
    lines = [f"Found {len(ids)} messages:", "", "📧 MESSAGES:"]
    for i, mid in enumerate(ids, 1):
        lines += [f"  {i}. Message ID: {mid}", f"     Thread ID: t_{mid}", ""]
    if next_token:
        lines.append(f"📄 PAGINATION: To get the next page, call search_gmail_messages again with page_token='{next_token}'")
    return "\n".join(lines)


class FakeTool:
    def __init__(self, name, handler):
        self.name, self.handler, self.calls = name, handler, []
        self.args = {"user_google_email": {}}

    async def ainvoke(self, args):
        self.calls.append(args)
        return [{"type": "text", "text": self.handler(args), "id": "lc_1"}]


def search_handler(args):
    if "newer_than:1d" not in args["query"]:
        return fake_search_output(["m1"])                       # Part 2: newest inbox email
    if args.get("page_token") == "page2":
        return fake_search_output(["m3"])                       # Part 3/4: second page
    return fake_search_output(["m1", "m2"], next_token="page2")  # Part 3/4: first page


def content_handler(args):
    sender, subject, body = FAKE_EMAILS[args["message_id"]]
    return f"Subject: {subject}\nFrom: {sender}\nDate: Fri, 21 Nov 2026\n\n--- BODY ---\n{body}\n\n--- ATTACHMENTS ---\n1. a.pdf"


def draft_handler(args):
    return f"Draft created! Draft ID: draft_{args['thread_id']}"


search_tool = FakeTool("search_gmail_messages", search_handler)
content_tool = FakeTool("get_gmail_message_content", content_handler)
draft_tool = FakeTool("draft_gmail_message", draft_handler)


class FakeMCPClient:
    @asynccontextmanager
    async def session(self, name):
        yield None


async def fake_load_mcp_tools(session):
    return [search_tool, content_tool, draft_tool]


# ---------------------------------------------------------------------------
# Fake LLMs
# ---------------------------------------------------------------------------
FAKE_REPLY = "Hi,\n\nThanks for your email.\n\nBest regards"


class FakeWriterLLM:
    """Returns a fixed reply and remembers every prompt it was given."""

    def __init__(self):
        self.prompts = []

    def invoke(self, messages):
        self.prompts.append(messages[-1].content)
        return AIMessage(content=FAKE_REPLY)


def fake_classify(messages):
    email_text = messages[-1].content
    needs_action = "?" in email_text  # simple rule for the fake: a question needs action
    return reader.EmailAnalysis(
        needs_action=needs_action,
        summary="Fake summary.",
        reason="Asks me something." if needs_action else "Promotional email.",
        action_required="Reply to the sender." if needs_action else "",
    )


def install_fakes():
    gmail_client.mcp_client = FakeMCPClient()
    gmail_client.load_mcp_tools = fake_load_mcp_tools
    gmail_client.USER_EMAIL = "me@example.com"
    writer.llm = FakeWriterLLM()
    reader.classifier = RunnableLambda(fake_classify)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_part1_writer():
    result = workflow.run_part1("Can we meet next week?")
    assert result["reply"] == FAKE_REPLY


def test_part2_latest_email():
    result = workflow.run_part2()
    assert result["email_body"].startswith("From: Priya Sharma <priya@example.com>\nSubject: Q1 timeline call")
    assert "ATTACHMENTS" not in result["email_body"]
    assert result["reply"]


def test_part3_reader_categorises():
    emails = workflow.run_part3()["emails"]
    assert [e["id"] for e in emails] == ["m1", "m2", "m3"]           # both search pages were read
    assert [e["thread_id"] for e in emails] == ["t_m1", "t_m2", "t_m3"]
    assert [e["needs_action"] for e in emails] == [True, False, True]
    assert emails[0]["action_required"] == "Reply to the sender." and emails[1]["action_required"] == ""
    assert search_tool.calls[-1]["user_google_email"] == "me@example.com"


def test_part4_reader_passes_context_to_writer_and_saves_drafts():
    writer.llm.prompts.clear()
    draft_tool.calls.clear()
    result = workflow.run_part4()

    assert [r["email"]["id"] for r in result["replies"]] == ["m1", "m3"]   # only emails needing action
    assert len(writer.llm.prompts) == 2
    for prompt in writer.llm.prompts:                                     # writer got the reader's analysis
        assert "Context from the reader agent" in prompt and "Reply to the sender." in prompt

    # every reply saved as a Gmail draft, in the original thread, addressed to the sender
    assert [r["draft_id"] for r in result["replies"]] == ["draft_t_m1", "draft_t_m3"]
    assert [(c["thread_id"], c["to"], c["body"]) for c in draft_tool.calls] == [
        ("t_m1", "priya@example.com", FAKE_REPLY),
        ("t_m3", "rahul@example.com", FAKE_REPLY),
    ]


def test_app_all_tabs():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(SRC / "frontend" / "app.py")).run(timeout=60)
    assert [t.label for t in app.tabs] == [
        "Part 1 · Paste an email", "Part 2 · Reply from Gmail inbox",
        "Part 3 · Reader agent", "Part 4 · Reader → Writer",
    ]
    app.tabs[0].text_area[0].input("Can we meet next week?").run(timeout=60)
    for tab in range(4):
        app.tabs[tab].button[0].click().run(timeout=60)
    assert not app.error, [e.value for e in app.error]

    cards = [app.tabs[i].get("iframe")[0].proto.srcdoc for i in range(4)]
    assert "Can we meet next week?" in cards[0]
    assert "Q1 timeline call" in cards[1]
    assert "Need action (2)" in cards[2] and "Does not need action (1)" in cards[2]
    assert "Reader context" in cards[3] and "Approve the budget by Friday" in cards[3]
    assert cards[3].count("Reply saved in Drafts") == 2 and "Generated draft" in cards[3]


if __name__ == "__main__":
    install_fakes()
    tests = [test_part1_writer, test_part2_latest_email, test_part3_reader_categorises,
             test_part4_reader_passes_context_to_writer_and_saves_drafts, test_app_all_tabs]
    for test in tests:
        test()
        print(f"PASS  {test.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
