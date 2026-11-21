"""Start the Gmail MCP server (workspace-mcp) locally over streamable HTTP.

Run in its own terminal and keep it open:
    python src/mcp_server/start_server.py

The server then listens on http://localhost:8000/mcp.
Google credentials are read from .env (GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET).
Gmail access is limited to reading emails and creating drafts (see GMAIL_PERMISSIONS).
"""

import os
import shutil
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()

missing = [k for k in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET") if not os.getenv(k)]
if missing:
    sys.exit(f"Missing in .env: {', '.join(missing)}")

uvx = shutil.which("uvx") or os.path.join(os.path.dirname(sys.executable), "Scripts", "uvx.exe")

env = os.environ.copy()
env.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")  # allow the http://localhost OAuth callback
env.setdefault("WORKSPACE_MCP_PORT", "8000")

# Pinned version: only changes when you edit this line (avoids running unreviewed updates).
WORKSPACE_MCP_VERSION = "2.6.0"

# Least-privilege Gmail access: read emails + create drafts only.
# No sending, no label/modify, no settings. (Levels: readonly, organize, drafts, send, full)
GMAIL_PERMISSIONS = "gmail:readonly+drafts"

cmd = [
    uvx, "--from", f"workspace-mcp=={WORKSPACE_MCP_VERSION}", "workspace-mcp",
    "--transport", "streamable-http",
    "--permissions", GMAIL_PERMISSIONS,
    "--single-user",
]
print("Starting:", " ".join(cmd[1:]))
subprocess.run(cmd, env=env, check=False)
