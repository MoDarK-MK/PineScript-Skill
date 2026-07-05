# Publishing Guide (TradingView House Rules, condensed)

Source: TradingView's official "Publishing scripts" docs page. This is a condensed,
practical checklist — always point the user to the live pages below for anything
consequential, since these rules are TradingView policy and can change:

- House Rules: https://www.tradingview.com/house-rules/
- Script Publishing Rules: https://www.tradingview.com/support/solutions/43000590599-script-publishing-rules/
- Vendor Requirements (invite-only/paid scripts): https://www.tradingview.com/support/solutions/43000549951-vendor-requirements/

## Privacy vs visibility (two separate choices, neither changeable after publishing)

**Privacy** — who can find it:
- **Public** — discoverable by everyone in Community Scripts; subject to moderation
  against House Rules; only editable for **15 minutes** after publishing, then
  permanently locked (title/description) except via a new "update" with release
  notes.
- **Private** — only accessible via direct URL, not moderated, always editable/
  deletable. Cannot be linked to from any public TradingView content.

**Always publish a private draft first**, verify it looks right, then publish the
public version using the verified text. This is TradingView's own recommendation —
the 15-minute public edit window is easy to blow through while double-checking
formatting.

**Visibility** — who can see/use the code:
- **Open** (open-source) — code visible to anyone; Mozilla Public License 2.0 by
  default unless another license is specified in the source; most common; only
  open-source scripts are eligible for Editors' Picks.
- **Protected** — closed-source, but free and usable by anyone; requires a paid
  plan; description must explain what's unique enough to justify hiding the code.
- **Invite-only** — closed-source, usable only by users the author explicitly
  grants access to; the only visibility type where charging money is allowed;
  requires Premium+ plan; author becomes a "vendor" subject to Vendor Requirements.

## Source-code checklist before publishing

- No lookahead-biased `request.security()` calls (non-offset expression +
  `barmerge.lookahead_on` on historical bars) — this specifically breaks
  publication rules, not just correctness.
- `input.*()` calls include `minval`/`maxval`/`options` where relevant, to block
  nonsensical user input.
- Titles/comments/identifiers are readable (see `references/style-guide.md`).
- The `title=` argument of `indicator()`/`strategy()`/`library()` is meaningful and
  searchable — this becomes the default publication title.
- Run the CI/CD pipeline in this skill first: `pine_lint.py` clean, `testMode`
  input defaults to `false`, version bumped, changelog updated.

## Strategy-specific realism requirements (if publishing a strategy)

TradingView explicitly moderates for these — an unrealistic backtest is a rules
violation, not just bad practice:

- `initial_capital` should reflect a realistic amount for an average trader — not
  inflated to make returns look better.
- Set realistic `commission_*`, `slippage`, and `margin_*` for the instrument/
  exchange in question.
- Don't risk more than ~10% of equity on a single trade as a rule of thumb for
  "sustainable" sizing.
- Aim for **100+ simulated trades** in the published backtest — too few trades
  don't demonstrate anything statistically meaningful.
- Publish using the strategy's actual default settings (don't publish a fine-tuned-
  for-this-one-chart config) and explain the defaults in the description.
- Resolve every Strategy Tester warning before publishing.
- Never use a non-standard chart type (Heikin Ashi, Renko, Line Break, Kagi,
  Point & Figure, Range) for a script that trades, alerts, or shows signals — those
  charts show synthetic prices, not real ones, and can badly mislead users.

## Title rules

- English text, standard 7-bit ASCII only — no emoji/special characters.
- No ALL CAPS except real abbreviations (RSI, EMA, etc).
- No unsubstantiated claims ("90% win rate") and no links/handles/advertising.

## Description rules

- Self-contained: explain purpose, how it works, how to use it, and why it's
  original — even for open-source scripts, since not every user reads the code.
- Closed-source (protected/invite-only) publications must explain what's uniquely
  valuable enough to justify hiding the source.
- No unsubstantiated performance claims.
- Primarily English; other languages are fine as long as English comes first, and
  any non-English UI text in the script (input titles, etc.) gets an English
  translation in the description.
- Supported markup tags in the description field: `[b][/b]`, `[i][/i]`, `[s][/s]`,
  `[pine][/pine]` (code block), `[list][/list]` / `[list=1][/list]` (bulleted /
  numbered, items marked with `[*]`), `[quote][/quote]`, `[url=...][/url]`,
  `[image][/image]`, and `$TICKER` (e.g. `$AMEX:SPY`) to auto-link a symbol.

## Chart preparation before publishing

- The script must actually be on the chart (not just open in the editor).
- Remove other scripts/drawings/images unless directly relevant to demonstrating
  this one; if something extra is genuinely needed, explain why in the description.
- Status line should show symbol + timeframe + script name (enable "Title/Titles").
- Show the script's *default* settings (use "Reset settings" if you'd been tuning
  it live) so users see what they'll actually get by default.

## What `scripts/generate_release_bundle.py` automates

The script in this skill drafts a `PUBLISH_DESCRIPTION.md` covering the structural
requirements above (purpose/how-it-works/how-to-use-it/originality sections,
strategy realism disclosure block if applicable) so the user isn't starting from a
blank text field — but the actual prose explaining the script's unique logic has to
come from the user (or from Claude, informed by the actual script logic), and the
user still needs to manually go through TradingView's "Publish script" UI — there is
no public API for publishing.
