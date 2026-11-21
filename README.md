# Email Agents

Two LangGraph agents that work with your Gmail through a local Gmail MCP server (streamable HTTP):

- **Reader agent** reads today's emails and sorts them into *need action* / *does not need action*.
- **Writer agent** writes replies. The reader passes its analysis to the writer, and every reply
  is saved as a Gmail draft in the original thread, so you can review it before sending.

Each assignment part builds on the previous one and has its own tab in the Streamlit UI:

| Part | What it does | LangGraph workflow |
|---|---|---|
| 1 | Reply to a pasted email | `writer` |
| 2 | Reply to the newest inbox email | `fetch_latest_email → writer` |
| 3 | Reader agent: categorise today's emails | `read_emails → categorize_emails` |
| 4 | Reader → Writer: draft replies for emails that need action | `read_emails → categorize_emails → write_replies → save_drafts` |

## Project structure

```
src/
├── backend/
│   ├── llm.py              # the one shared LLM instance
│   ├── agents/
│   │   ├── reader.py       # reader agent
│   │   └── writer.py       # writer agent
│   └── workflow.py         # all LangGraph graphs
├── frontend/app.py         # Streamlit UI
├── mcp_server/
│   ├── start_server.py     # starts the Gmail MCP server (workspace-mcp)
│   └── gmail_client.py     # reads emails / saves drafts over MCP
└── testing/                # offline tests, connection test, screenshot script
```

## Setup

1. Python 3.10+ and `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in:
   - `OPENAI_API_KEY`, `OPENAI_MODEL`
   - `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` (Google Cloud → Desktop OAuth client, Gmail API enabled)
   - `USER_GOOGLE_EMAIL`
3. Gmail access is limited to **reading emails and creating drafts** (no sending).

## Run (from the project root)

```
python src/mcp_server/start_server.py     # terminal 1: Gmail MCP server
streamlit run src/frontend/app.py         # terminal 2: UI
```

The first Gmail call returns a Google sign-in link; open it once and approve.

## Tests

```
python src/testing/test_offline.py            # all parts, fake LLM + fake Gmail (no keys needed)
python src/testing/test_gmail_connection.py   # real Gmail connection check
```
