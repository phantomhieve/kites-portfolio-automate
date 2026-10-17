#!/usr/bin/env bash
set -eo pipefail

echo "==> Running Kites Automate pre-commit checks..."

# 1. Prevent secret / sensitive files from being staged (CRITICAL)
FORBIDDEN_PATTERNS='(\.env$|\.env\..*|credentials\.json$|profiles\.json$|\.key\.json$|id_rsa|\.pem$|\.pfx$|.*_formatting_state\.json$)'
STAGED_FILES=$(git diff --cached --name-only)

for file in $STAGED_FILES; do
    if echo "$file" | grep -Eq "$FORBIDDEN_PATTERNS"; then
        echo "❌ ERROR: Attempting to commit forbidden secret/credential file: $file"
        echo "Please unstage this file immediately before committing."
        exit 1
    fi
done

# 2. Check for merge conflict markers
CONFLICT_PATTERN='^[<]{7} '
if git diff --cached -G"$CONFLICT_PATTERN" --quiet; then
    :
else
    echo "❌ ERROR: Unresolved merge conflict markers detected in staged changes."
    exit 1
fi

# 3. Python syntax and bytecode compilation check on staged Python files
PYTHON_STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true)
if [ -n "$PYTHON_STAGED" ]; then
    echo "==> Verifying Python syntax on staged files..."
    for pyfile in $PYTHON_STAGED; do
        if [ -f "$pyfile" ]; then
            python3 -m py_compile "$pyfile"
        fi
    done
fi

# 4. Synchronize CodeGraph knowledge index if installed
if command -v codegraph >/dev/null 2>&1; then
    echo "==> Synchronizing CodeGraph..."
    codegraph sync >/dev/null 2>&1 || true
elif [ -x "/opt/homebrew/bin/codegraph" ]; then
    echo "==> Synchronizing CodeGraph..."
    /opt/homebrew/bin/codegraph sync >/dev/null 2>&1 || true
fi

echo "✅ All pre-commit checks passed successfully!"
exit 0
