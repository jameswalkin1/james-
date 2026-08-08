# james-

This repo ships a project-scoped MCP server config in [`.mcp.json`](.mcp.json).
Any Claude Code session opened on this repo picks the servers up automatically.
Both read their credentials from the environment, so no secret is committed.

| Server      | What it gives you                                        | Env var                 |
| ----------- | -------------------------------------------------------- | ----------------------- |
| `21st`      | React/Tailwind component catalog, UI generation, logos    | `TWENTY_FIRST_API_KEY`  |
| `firecrawl` | Web scraping, crawling, search, and page-to-markdown      | `FIRECRAWL_API_KEY`     |

## 21st MCP (formerly Magic MCP)

The 21st.dev UI tooling: search a catalog of React/Tailwind components, generate
new UI, and search logos.

`21st-dev/magic-mcp` is deprecated. The `@21st-dev/magic` npm package still
works, but it is now only a thin stdio proxy that forwards to the same
`https://21st.dev/api/mcp` endpoint this config points at directly. The direct
HTTP config below is the current, supported setup — one less hop, no npx
download on every session start.

### Setup

The config reads your key from the environment, so no secret is committed.

1. Generate an API key at <https://21st.dev/mcp>.

   Keys from the old Magic console were reset and no longer work anywhere —
   if you have one, generate a fresh key.

2. Export it wherever your shell reads env vars (`~/.zshrc`, `~/.bashrc`, a
   direnv `.envrc`, or your sandbox's environment settings):

   ```bash
   export TWENTY_FIRST_API_KEY="your_key_here"
   ```

3. Start Claude Code in this repo. On first run it asks you to approve the
   project-scoped server; approve it. Verify with:

   ```
   /mcp
   ```

   `21st` should be listed as connected.

### Tools

Legacy Magic tool names are translated automatically by the server, so older
prompts and configs keep working:

| Legacy name                        | Current name      |
| ---------------------------------- | ----------------- |
| `21st_magic_component_builder`     | `generate`        |
| `21st_magic_component_refiner`     | `generate`        |
| `21st_magic_component_inspiration` | `get_inspiration` |
| `logo_search`                      | `search_logo`     |

Beyond these, the server exposes catalog search, code retrieval, bookmarks,
team libraries, and profile management. Run `/mcp` in Claude Code to see the
full live list.

### Alternative: the 21st CLI

To write this config into a different client instead of using the repo copy:

```bash
npx @21st-dev/cli@latest init --client claude
```

`--client` also accepts `cursor`, `vscode`, `windsurf`, and `codex`.

### Network note

`https://21st.dev/api/mcp` must be reachable. In sandboxed or proxied
environments with a restrictive egress policy, allowlist `21st.dev` or the
server will fail to connect.

## Firecrawl MCP

<https://github.com/firecrawl/firecrawl-mcp-server> — scrape a page to clean
markdown, crawl a whole site, run a web search, extract structured data, parse
PDFs and docs, and monitor pages for changes.

`.mcp.json` points at Firecrawl's **hosted** endpoint,
`https://mcp.firecrawl.dev/v2/mcp`, rather than running the `firecrawl-mcp` npm
package over stdio. Same tools, no npx download on every session start, and
upstream keeps it current.

### Setup

1. Generate an API key at <https://firecrawl.dev/app/api-keys>. Keys look like
   `fc-...`.

2. Export it alongside your other keys:

   ```bash
   export FIRECRAWL_API_KEY="fc-your_key_here"
   ```

3. Start Claude Code in this repo, approve the project-scoped server on first
   run, and verify with `/mcp` — `firecrawl` should be listed as connected.

Never put the key in the URL; it belongs in the `Authorization: Bearer …`
header, which is how `.mcp.json` sends it.

### Tools

| Tool                                  | Use                                                  |
| ------------------------------------- | ---------------------------------------------------- |
| `firecrawl_scrape`                    | One URL → markdown / JSON / structured extraction     |
| `firecrawl_map`                       | List the URLs a site exposes                          |
| `firecrawl_search`                    | Web search, optionally with page content pulled in    |
| `firecrawl_crawl` / `_check_crawl_status` | Multi-page crawl (async — poll the status tool)   |
| `firecrawl_parse`                     | PDFs, Word docs, spreadsheets → text                  |
| `firecrawl_agent` / `_agent_status`   | Autonomous research returning structured output       |
| `firecrawl_interact` / `_interact_stop` | Click, type, and navigate a live page               |
| `firecrawl_developer_search`          | Search GitHub issues, PRs, and docs                   |
| `firecrawl_monitor_*`                 | Watch pages on a schedule and diff the changes        |

Run `/mcp` for the full live list.

### Alternatives

- **Keyless free tier** — drop the `headers` block from the `firecrawl` entry
  and the hosted endpoint works unauthenticated at a reduced rate limit.
- **Search only** — point `url` at `https://mcp.firecrawl.dev/v2/mcp-search`
  for a smaller surface (fewer tools in the context window).
- **Local stdio** — replace the entry with the npm package:

  ```json
  "firecrawl": {
    "command": "npx",
    "args": ["-y", "firecrawl-mcp"],
    "env": { "FIRECRAWL_API_KEY": "${FIRECRAWL_API_KEY}" }
  }
  ```

- **Self-hosted Firecrawl** — use the stdio form above and add
  `"FIRECRAWL_API_URL": "https://firecrawl.your-domain.com"` to `env`.

### Network note

`https://mcp.firecrawl.dev` must be reachable. Allowlist `mcp.firecrawl.dev` in
restrictive egress environments, or the server will fail to connect. (This
sandbox blocks `docs.firecrawl.dev`, for instance.)
