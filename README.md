# james-

## 21st MCP (formerly Magic MCP)

This repo ships a project-scoped MCP server config in [`.mcp.json`](.mcp.json).
Any Claude Code session opened on this repo picks it up automatically and gets
the 21st.dev UI tooling: search a catalog of React/Tailwind components, generate
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
