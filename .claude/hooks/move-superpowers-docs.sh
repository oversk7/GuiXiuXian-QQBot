#!/bin/bash
# Hook: Auto-move superpowers output from docs/superpowers/ to llmdoc/design/
# Triggered after Write tool — no-ops when nothing to move

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"

[ -d "docs/superpowers" ] || exit 0

moved=0

for f in docs/superpowers/specs/*.md; do
    [ -f "$f" ] || continue
    mkdir -p llmdoc/design/specs
    mv "$f" llmdoc/design/specs/
    moved=$((moved + 1))
done

for f in docs/superpowers/plans/*.md; do
    [ -f "$f" ] || continue
    mkdir -p llmdoc/design/plans
    mv "$f" llmdoc/design/plans/
    moved=$((moved + 1))
done

# Clean up empty directories
rmdir docs/superpowers/specs 2>/dev/null
rmdir docs/superpowers/plans 2>/dev/null
rmdir docs/superpowers 2>/dev/null
rmdir docs 2>/dev/null

[ $moved -gt 0 ] && echo "Moved $moved file(s) from docs/superpowers/ to llmdoc/design/"
exit 0
