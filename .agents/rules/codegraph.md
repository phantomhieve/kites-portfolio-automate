# CodeGraph Knowledge Graph Usage & Synchronization

## Policy:
1. **Explore First**:
   - Before answering architectural questions, refactoring modules, or modifying symbols, query the knowledge graph via the `codegraph_explore` MCP tool or `/opt/homebrew/bin/codegraph explore <query>` CLI.
   - Inspect symbol definitions, callers, callees, and dependencies across `src/kites_automate/` to understand downstream impact.

2. **Keep Synchronized**:
   - After adding, renaming, or refactoring symbols or files, ensure the knowledge graph is synchronized by running `codegraph sync`.
   - Never commit the SQLite database `.codegraph/codegraph.db` (enforced by `.codegraph/.gitignore`).
