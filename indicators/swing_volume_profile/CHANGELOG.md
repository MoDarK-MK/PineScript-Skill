# Changelog

## [Unreleased]
- (nothing yet)

## [0.5.0] - 2026-08-23
### Added
- **Intrabar volume distribution** (`request.security_lower_tf`, on by default at 1 minute). This is the largest accuracy gain available to the script. Without it a bar's volume has to be SPREAD across every price it touched using a guess about where inside the bar the trading happened; with it each sub-bar is placed at its own narrow range carrying its own close position, so the profile is largely measured rather than modelled and the buy/sell split gets one estimate per sub-bar instead of one per candle.
- Falls back to the bar-level model **per bar**, wherever TradingView returns no intrabar data — its intrabar budget is finite and older history runs out. Nothing breaks; that part of the chart is simply modelled the old way.
- New table row **Data** reports what share of the shown swing was built from real intrabar data. A number whose provenance is invisible invites more trust than it has earned.
- Fetched as ONE tuple request rather than four separate ones: four calls could return arrays of differing length, and indexing them in lockstep would read one sub-bar's price against another's volume — a corruption that would look like noise rather than a bug. It also costs one slot against the 40-request cap instead of four.
- **Low Volume Nodes** are tinted separately in the profile. They are the opposite of the POC and just as informative: price accelerates through them because there is nothing there to trade against, which makes them poor targets and poor places to stand. Costs no extra drawings — the rows were already being drawn.
- **Naked POC**: the most-agreed price of a finished leg that price has not returned to, with its own table row and alert. Built from the post-swing range each swing already maintains, so it is a comparison rather than a search.
- **Value migration**: whether the POC moved up, down or stayed flat between the last two finished legs — the cheapest read of control there is. A move smaller than one row is FLAT, because that is rounding, not migration.

### Changed
- Entry levels now need **two** independent floors: Minimum Strength (how one-sided the row was) and the new Minimum Row Volume (whether enough traded there for one-sidedness to mean anything). A thin shelf can be 90% buying and still be nothing — price does not defend a price nobody was at.
- Seconds timeframes are called out in the Intrabar Timeframe tooltip: on a non-Premium plan a seconds value fails the WHOLE script, not just the feature. The default is one minute for that reason.

## [0.4.0] - 2026-08-22
### Added
- **Measured hit rate.** Every level the indicator would draw is recorded when its swing closes and then followed: when price reaches it, did the move that followed travel the target distance in the level's favour before travelling the same distance against? The table reports the share that did, with the sample size, greyed under 20 samples. It measures the levels actually drawn, not an easier proxy — a statistic about something else would look like evidence for the line on screen while being about a different thing.
- When a single bar covers both the target and the stop, the order they happened in is unknowable from bar data and it is counted as a LOSS. Calling it a win would inflate every number in the block.
- **Untested levels only** (default on). Rows price has already traded back through since the swing ended are skipped. An imbalance that has been revisited has had its argument tested; one that has not is still standing. Implemented as a running min/max per stored swing, so it costs one comparison per swing per bar rather than a rescan.
- **Swing source** is now pluggable: pivots on the chart timeframe, pivots on a higher timeframe, or trading sessions. All three feed the same pipeline. Sessions are exact. The higher-timeframe pivot's price is exact but its bar is converted by the timeframe ratio, so across gaps the left edge can land a bar or two off — said in the input tooltip, not just here.
- **Confluence zones.** Levels from different swings landing within a configurable ATR distance are merged into one band labelled with how many agree. The agreement is the information, and three separate lines hide it. Drawn from 8 boxes held back from the row budget so a dense profile can never starve them.
- **Absorption detection.** A swing that makes a new extreme while the OTHER side's share of its volume rises: the extreme says one side pushed, the rising share says the other side was there to take it. Both halves are required — a new low on rising selling is just a downtrend. Two alert conditions.
- **JSON alert payloads** for webhooks, with a fixed key order because that ordering is the contract a receiving bot is written against.

### Changed
- Table gained hit rate, absorption and confluence rows, placed with the entry block rather than below the reference prices: the hit rate is the only line on the panel that says whether the entry block has been worth anything.
- `MAX_ROW_BOXES` drops from 492 to 484 to reserve the confluence boxes.

## [0.3.1] - 2026-08-22
### Fixed
- Pivots were recorded on any tick where `ta.pivothigh`/`ta.pivotlow` returned a value, but their window includes the bar still forming — a pivot can confirm on one tick and be invalidated by a higher high on the next. The comment at that spot claimed `var` protected against exactly this. It does not: `var` restores the variable on a realtime rollback, never the contents of the array it points at, so the phantom swing stayed recorded. Pivots are now recorded on `barstate.isconfirmed`. Found by the new PINE054 rule.

## [0.3.0] - 2026-08-22
### Added
- **Entry level.** One line marking the strongest volume IMBALANCE on the tradeable side of price: for a buy, the row below price where buying most outweighed selling; for a sell, the row above price where selling most outweighed buying. Scored as `(buy - sell) / busiest row`, one number carrying both how lopsided the row was and how much volume it held — a row where buyers barely won on tiny volume scores near zero, and so does a huge row that was evenly matched. Neither is a level.
- Below the Minimum Strength input nothing is drawn at all and the table says "none". A profile with no strong imbalance genuinely has no level to offer, and inventing one would be the exact failure this feature must not have.
- The search covers every drawn swing by default, not just the newest: the strongest level available is often in an older leg price has not returned to yet, and an untested imbalance is more interesting than a tested one.
- **Value Area (VAH / VAL)** per swing, built the standard way — grown outward from the POC, always taking the heavier neighbour, until 70% of the swing's volume is inside. Standard matters here because other traders are drawing the same two lines.
- **Total volume label above each swing's profile**, with the buy share. The developing swing is prefixed with `~` because its number is still moving. The tooltip carries the buy/sell split, bar count and row count.
- Alert when price reaches a drawn entry level, on bar close. Mid-bar a touch can un-happen, and an alert for something that never finished is worse than no alert.
- Table gained Entry level, Strength, Distance, Swing volume and Value area rows, with the entry block first — it is the only line on the chart that answers a question rather than describing history.

### Changed
- **Volume distribution is now body-weighted by default.** Spreading a bar's volume evenly across every row it spans gives a wick the same volume per row as the body, which is wrong in an obvious way: a wick is a price the market REJECTED and traded through quickly. Even distribution is still available. The weighting is closed-form, so it costs no extra pass over the rows, and it preserves each bar's total volume exactly.
- New "Buy/Sell Estimate" option blending close-in-range with bar direction. The default is left on plain close-in-range: neither is verifiably better everywhere, and quietly changing the numbers under a chart someone has been reading would be worse than offering the choice.
- **The profile drawing now runs once per bar instead of once per tick.** Up to 492 box `.set_*()` calls were re-running on every tick to redraw a picture that was already correct — by far the most expensive thing this script did. Only the entry level tracks live price, so only it stays on the per-tick path: one pass over the rows plus two line updates.
- The redraw trigger is a generation counter bumped by every change to the set of profiles, not the swing count. A push plus a drop on the same tick leaves the count identical and the picture wrong.

### Fixed
- In "Best Side Only" mode both entry prices were published while only one was drawn, so the alert could fire for a level that was not on the chart. Only drawn levels are published now.
- Removed `drawableSwings`, dead since the 0.2.0 budget rework, and two write-only `array.shift()` results. All three were found by the new PINE051 rule.

## [0.2.0] - 2026-08-22
### Added
- Price Rows Per Swing now goes to 500, up from 60. Rows are built at the resolution you ask for regardless of how many get drawn, so POC / Max Buy / Max Sell sharpen with every row added.
- Summary table reports rows actually built and the box budget in use, so the two limits that can bite are visible instead of silent.

### Changed
- Rows holding no volume no longer consume a box. At high resolution most rows in a swing are empty, and that is what makes a high row count affordable; the drawing also breaks out of the loop once the budget is gone.
- Swings draw newest first. If the box budget does run out it is now the oldest swing that thins, never the leg price is trading in.
- Rows are no longer capped by a fixed per-swing budget derived from swing count. Only the drawing is rationed now.

### Fixed
- A swing spanning fewer ticks than the requested row count had its range inflated to `mintick * rows`, drawing a profile taller than the swing it described. The floor is one tick, and rows are reduced to the tick count the swing actually spans — invisible at 30 rows, wrong at 500.

## [0.1.0] - 2026-08-22
### Added
- Initial version. A horizontal volume profile built PER SWING rather than over a fixed last-N-bars window, so the profile always describes the leg price is actually in.
- Swings are detected automatically from pivots, with Pivot Length configurable; defaults are tuned for the 5-minute chart (length 10, roughly 50-minute swings).
- Three marker lines per swing, which is the point of the profile: POC (most total volume), Max Buy (most estimated buying) and Max Sell (most estimated selling). They are frequently different rows, and that separation is the signal.
- Each profile row can be split into a sell segment and a buy segment, or drawn as one bar coloured by whichever side dominated.
- Profile can be drawn over the swing (width capped as a share of the swing so it never buries the candles) or to the right of it.
- Summary table showing POC, max buy, max sell, buy share, and the row count actually in use.
- Fully customisable: swing count, rows, width, transparency, line width/style/extend, labels, colours, theme, table position.

### Notes on method
- Buy/sell is estimated from where each bar closed inside its own range (`(close - low) / (high - low)`). Pine exposes no bid/ask, so no script can know the true aggressor; this is the standard approximation for a profile of this kind and is documented in the file header rather than implied.
- `request.security_lower_tf()` was deliberately not used: on a 5-minute chart the finest intrabar resolution available without a Premium plan is 1 minute — five sub-bars per candle, barely better than the range split and far more expensive.

### Performance
- A completed swing's profile is computed once, when the swing closes, and afterwards only repositioned. Only the developing swing is recomputed, and that is memoised per bar rather than per realtime tick.
- Drawings use `var` pools updated with `.set_*()`; nothing is deleted and rebuilt.
- Rows per swing are derived from the remaining box budget, so a high swing count reduces rows instead of silently hitting TradingView's 500-box cap.
