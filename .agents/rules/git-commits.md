# Git Commit Guidelines

## Policy:
1. **Always Have a Proper Conventional Commit Message**:
   - Write clear, concise, imperative subject lines using conventional commit types:
     - `feat: ...` for new features or capabilities
     - `fix: ...` for bug fixes and patches
     - `refactor: ...` for code structure cleanups and modernizations
     - `security: ...` for credential handling and sandboxing
     - `docs: ...` for documentation and README updates
   - Keep the first line under 72 characters and capitalized.
   - Include a body paragraph whenever the context, rationale, or trade-offs are not obvious from the subject line.

2. **Pre-commit Verification**:
   - Always run pre-commit verification before finalizing changes:
     1. Secret scanning (ensure `.env`, `credentials.json`, `profiles.json` are not staged).
     2. Python syntax and bytecode compilation verification (`python3 -m py_compile ...`).
     3. Ensure no merge conflict markers exist.
     4. Synchronize CodeGraph (`codegraph sync`).
