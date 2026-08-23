# Repo Structure, Versioning & Changelog Format

## Folder layout

```
project-root/
├── indicators/
│   └── my_rsi_bands/
│       ├── src/my_rsi_bands.pine
│       ├── test/my_rsi_bands.test.pine   (optional, only if test logic got too big
│       │                                   for the in-file test block)
│       ├── version.json
│       └── CHANGELOG.md
├── strategies/
│   └── trend_break/
│       ├── src/trend_break.pine
│       ├── version.json
│       └── CHANGELOG.md
├── release/   (generated per project by generate_release_bundle.py; gitignored)
└── .pine-lint.json   (optional — overrides for scripts/pine_lint.py, e.g. custom
                        max line length or disabling a specific rule)
```

`scaffold_project.py` creates a project in exactly that shape.

Note that `indicators/` and `strategies/` are **git-ignored** in this repo: the
toolchain is public and the trading work built with it is not. They exist on
disk and every script here operates on them normally.

## Sharing code between projects

Pine Script has **no local file imports** — you cannot `import` a `.pine` file
from disk. There are only two real options:

1. **Copy the block and maintain both sides.** This is what
   a strategy does with its indicator's scoring
   engine. The rule: a change to the shared logic must be applied to both files
   **in the same commit**, and both projects get a version bump. Mark the region
   with a comment so the boundary is obvious to the next reader.
2. **Publish it as a TradingView library** (`library("Name")` + `import
   user/Name/1`). This is real reuse, but the library has to live on
   TradingView's servers, so it can't be validated or released by this toolchain
   the way a normal project can.

`references/snippets/` holds fragments meant for option 1.

Keep one indicator/strategy per folder even in a single-user repo — it keeps
versioning and changelogs independent, which matters once the user has more than
one or two scripts they maintain over time.

## version.json

```json
{
  "name": "my_rsi_bands",
  "version": "0.1.0",
  "pine_version": 6,
  "kind": "indicator"
}
```

`scripts/bump_version.py` reads/writes this file. Don't hand-edit the version field
unless correcting a mistake — always go through the bump script so the changelog
stays in sync.

## CHANGELOG.md format (Keep a Changelog style, simplified)

```markdown
# Changelog

## [Unreleased]
- (nothing yet)

## [0.2.0] - 2026-07-05
### Added
- New `smoothing` input for the signal line

### Fixed
- Off-by-one in the lookback window that included the current unclosed bar

## [0.1.0] - 2026-06-20
### Added
- Initial release: RSI with adaptive bands
```

Workflow:
1. While working, new entries go under `## [Unreleased]`.
2. On release, `bump_version.py --bump <major|minor|patch>` renames `[Unreleased]`
   to `[x.y.z] - <today's date>` and adds a fresh empty `[Unreleased]` section above
   it.

## Optional pre-commit hook

For users who do want real git automation and have a local git installation
(outside this sandboxed environment — Claude cannot install git hooks on a machine
it doesn't have shell access to, so give this as a file for them to add themselves):

`.git/hooks/pre-commit` (make executable with `chmod +x`):

```bash
#!/bin/sh
# Lints all staged .pine files before allowing a commit.
files=$(git diff --cached --name-only --diff-filter=ACM -- '*.pine')
if [ -z "$files" ]; then
  exit 0
fi

fail=0
for f in $files; do
  python3 scripts/pine_lint.py "$f" || fail=1
done

if [ "$fail" -ne 0 ]; then
  echo "pine_lint.py found errors — fix them or commit with --no-verify to skip."
  exit 1
fi
