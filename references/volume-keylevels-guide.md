# Volume & Key Levels Engineering Guide (Pine Script v6)

A definitive, institutional-grade engineering manual for developing high-precision,
high-performance volume and key level indicators and strategies in TradingView Pine Script v6.

---

## 1. Architectural Foundations: Auction Market Theory (AMT)

Financial markets operate as continuous dual-auction mechanisms designed to facilitate trade.
Price is what advertises value; volume is the market's response to that advertisement.

```
       [Low Volume Node / LVN]      <-- Price rejected rapidly (liquidity vacuum / imbalance)
                 │
  ┌──────────────┴──────────────┐
  │   Value Area High (VAH)     │   <-- Upper edge of accepted fair value (70% Volume)
  │                             │
  │   Point of Control (POC)    │   <-- Price of maximum accepted agreement / highest volume
  │                             │
  │   Value Area Low (VAL)      │   <-- Lower edge of accepted fair value (70% Volume)
  └──────────────┬──────────────┘
                 │
       [Low Volume Node / LVN]      <-- Price rejected rapidly (liquidity vacuum / imbalance)
```

### 1.1 Volume Profile & Value Area (VA) Math
- **Point of Control (POC)**: The price row containing the highest accumulated volume over the profiled period.
- **Value Area (VA)**: The price range around the POC containing approximately **70%** (or statistical $1\sigma \approx 68.2\%$) of total profiled volume.
- **Exact Calculation Algorithm**:
  1. Find the POC bin index ($I_{\text{poc}}$). Add its volume to $V_{\text{accum}}$. Target volume $V_{\text{target}} = 0.70 \times V_{\text{total}}$.
  2. Maintain two pointers: $p_{\text{up}} = I_{\text{poc}} + 1$ and $p_{\text{down}} = I_{\text{poc}} - 1$.
  3. Compare the sum of the next 2 bins above ($V_{\text{up}}$) versus the next 2 bins below ($V_{\text{down}}$).
  4. Whichever is larger, expand the value area boundary in that direction and add its volume to $V_{\text{accum}}$.
  5. Repeat until $V_{\text{accum}} \ge V_{\text{target}}$.

### 1.2 Virgin / Naked POCs (vPOC / nPOC)
- A **Virgin POC (vPOC)** is a historical POC level that has **not been retested (touched)** by price in subsequent bars.
- vPOCs act as major magnet levels and high-probability reaction zones because significant market interest was established there without subsequent price equilibrium verification.
- **Mitigation Logic in Pine Script v6**:
  Track active vPOCs in a bounded `var array<float>` with corresponding creation timestamps/bar indices. On each confirmed bar, test if `low <= vpoc && high >= vpoc`. When touched, flag as mitigated and remove from the active drawing pool to conserve resources.

### 1.3 High Volume Nodes (HVN) vs. Low Volume Nodes (LVN)
- **High Volume Nodes (HVN)**: Prices where high volume accumulated. Represent fair value, balance, and acceptance. Price tends to slow down, chop, or rotate inside HVNs.
- **Low Volume Nodes (LVN)**: Prices where low volume traded. Represent rejection, liquidity vacuums, or rapid repricing. Price moves quickly through LVNs, making them ideal targets or invalidation boundaries.

---

## 2. Order Flow, Footprint & Delta Mechanics

Pine Script does not have direct L2 order book or tick-level bid/ask market depth access, but accurate order flow approximations are achieved via intrabar decomposition.

### 2.1 Aggressor Side Estimation Models

| Method | Resolution / Mechanism | Precision | Cost / Limitations |
|---|---|---|---|
| **Intrabar LTF (`request.security_lower_tf`)** | Pulls sub-bars (e.g. 1S, 5S, 1M) within the chart candle; applies tick rule per sub-bar | Highest | Requires LTF budget, seconds require TV Premium plan |
| **Tick Rule Approximation** | Compares `close` to `close[1]` on each sub-bar: `close > close[1] ? Buy : Sell` | High | Standard exchange-accepted trade-flow approximation |
| **Candle Range Split (Normalized)** | `buyShare = (close - low) / (high - low)` | Medium | Fast, pure single-bar calculation; no MTF calls |

### 2.2 Volume Delta & Cumulative Volume Delta (CVD)
$$\text{Delta} = V_{\text{buy}} - V_{\text{sell}}$$
$$\text{CVD}_t = \text{CVD}_{t-1} + \text{Delta}_t \quad (\text{optionally reset per session/day})$$

### 2.3 Order Flow Signatures

```
[Absorption Pattern]
Price:    ───┐ (Stalls at Key Resistance / High)
             │
Volume:   ▲▲▲  (Massive volume surge)
Delta:    ▲▲▲  (Heavy aggressive buying absorbed by passive limit sell orders)
Result:   ▼▼▼  (Price reverses downward — trapped aggressive buyers)
```

1. **Volume Absorption**:
   - **Characteristics**: Extremely high volume and strongly biased Delta at a key support/resistance level, but price fails to make progress or closes back inside the range.
   - **Interpretation**: Passive institutional limit orders are absorbing aggressive market orders (e.g. iceberg orders).
2. **Volume Exhaustion**:
   - **Characteristics**: Price makes a new high/low on significantly below-average volume and declining Delta.
   - **Interpretation**: Lack of market participation / buyers or sellers stepping aside.
3. **Delta Divergence**:
   - **Regular Bearish Divergence**: Price makes a Higher High ($P_2 > P_1$) while CVD makes a Lower High ($\text{CVD}_2 < \text{CVD}_1$). Aggressive buying is exhausted; probability of reversal is elevated.
   - **Regular Bullish Divergence**: Price makes a Lower Low ($P_2 < P_1$) while CVD makes a Higher Low ($\text{CVD}_2 > \text{CVD}_1$). Aggressive selling is exhausted.

---

## 3. Anchored VWAP (AVWAP) & Statistical Dispersion Bands

Volume-Weighted Average Price (VWAP) represents the true benchmark price of a financial asset over a specific accumulation period.

$$\text{VWAP} = \frac{\sum (P_i \times V_i)}{\sum V_i}, \quad \text{where } P_i = \frac{\text{high}_i + \text{low}_i + \text{close}_i}{3}$$

### 3.1 Statistical Standard Deviation Bands
To measure market extension and mean-reversion elasticity:

$$\sigma = \sqrt{\frac{\sum (P_i - \text{VWAP})^2 \times V_i}{\sum V_i}} = \sqrt{\frac{\sum (P_i^2 \times V_i)}{\sum V_i} - \text{VWAP}^2}$$

$$\text{Band}_{\pm k} = \text{VWAP} \pm k \times \sigma, \quad k \in \{1.0, 2.0, 3.0\}$$

### 3.2 High-Impact Anchor Selection
1. **Macro / HTF Anchors**: Yearly Open, Monthly Open, Weekly Open, Daily Session Open (RTH).
2. **Structural Anchors**: Major Swing Highs / Swing Lows (Pivots).
3. **Event / Catalyst Anchors**: High-Volume Climax Bars (Capitulation bars with $V > 3 \times \text{SMA}_{20}(V)$), earnings releases, CPI / FOMC announcements.
4. **Market Structure Breaks**: Anchor from the inception bar of a confirmed BOS (Break of Structure) or MSS (Market Structure Shift).

---

## 4. Multi-Timeframe Key Level Architecture & Clustering

Isolated lines on a chart create cognitive overload and low statistical reliability. Institutional key levels rely on **multi-dimensional confluence**.

```
                           [Level Clustering Engine]
   HTF Levels (PDH/PDL/PWH) ────┐
   Virgin POC (vPOC)        ────┼──► [DBSCAN Proximity Cluster] ──► [Weighted Confluence Zone]
   Liquidity Pools (EQH/EQL)────┤                                    Score: 85/100 (Strong Tier)
   Anchored VWAP            ────┘
```

### 4.1 Key Level Hierarchy

| Tier | Category | Components | Pine Script Access & Repaint Guard |
|---|---|---|---|
| **Tier 1 (HTF Macro)** | Period Extremes & Opens | Previous Day High/Low (PDH/PDL), Previous Week High/Low (PWH/PWL), Monthly Open (MO) | `request.security(syminfo.tickerid, "D", [high[1], low[1]], lookahead=barmerge.lookahead_off)` |
| **Tier 2 (Volume Structure)** | Volume Profile & VWAP | Developing/Session POC, Virgin POCs, Anchored VWAPs ($\pm 1\sigma, \pm 2\sigma$) | Stateful array accumulators + mitigation culling |
| **Tier 3 (Liquidity Pools)** | Structural Stop Zones | Equal Highs (EQH), Equal Lows (EQL), Range Midpoints | Pivot detection with tight price tolerance ($\le 0.1\%$ spread) |

### 4.2 Liquidity Sweeps / Stop Runs
A true institutional liquidity sweep occurs when:
1. Price temporarily pierces a known key level (e.g. PDH, EQH, or major swing high).
2. Intrabar volume surges (stop-loss triggering + aggressive absorption).
3. Price closes back inside the previous range before bar confirmation.
4. Subsequent candle confirms rejection.

### 4.3 Algorithmic Level Clustering Formula
When multiple independent technical levels lie within an $\epsilon$-neighborhood ($\Delta P \le \text{ATR}_{14} \times 0.25$):
- Cluster them into a single **Confluence Zone**.
- Calculate weighted center: $P_{\text{cluster}} = \frac{\sum (P_i \times w_i)}{\sum w_i}$
- Score the cluster ($0 - 100$) based on:
  - HTF Weight ($+30$)
  - Volume/vPOC Confluence ($+25$)
  - Liquidity Pool / EQH / EQL ($+20$)
  - Untested / Virgin Status ($+15$)
  - Recent Touch Rejection Count ($+10$)

---

## 5. Volume Spread Analysis (VSA) & Wyckoff Principles

Volume Spread Analysis evaluates the relationship between price spread (range $\text{high} - \text{low}$), closing position, and volume.

### 5.1 Core VSA Metrics
- **Normalized Spread Ratio**: $S_{\text{ratio}} = \frac{\text{high} - \text{low}}{\text{ATR}_{14}}$
- **Normalized Volume Ratio**: $V_{\text{ratio}} = \frac{\text{volume}}{\text{SMA}_{20}(\text{volume})}$
- **Effort vs. Result Ratio**:
  $$\text{EVR} = \frac{V_{\text{ratio}}}{\max(S_{\text{ratio}}, 0.1)}$$
  - $\text{EVR} > 2.5$ on a narrow candle: **High Effort, Little Result** (Strong Absorption / Hidden Institutional Accumulation/Distribution).
  - $\text{EVR} < 0.5$ on a wide candle: **Low Effort, Large Result** (Slippage / Liquidity Vacuum).

---

## 6. Pine Script v6 Implementation Patterns & Performance

Volume and Level indicators process large historical loops and dense drawings. Strict adherence to performance patterns is mandatory:

### 6.1 Array Memory Pooling (`var array`)
Do not reallocate arrays inside loops or on every bar. Declare once with `var` and reset using `array.fill()` or `array.clear()`:
```pinescript
// BAD: Allocates new memory on every bar/tick (GC overhead & latency)
float[] buyVols = array.new_float(row_count, 0.0)

// GOOD: Reuses memory pool
var float[] buyVolsPool = array.new_float(MAX_ROWS, 0.0)
array.fill(buyVolsPool, 0.0)
```

### 6.2 Fingerprint Caching on Live Ticks
```pinescript
// Gated scan: Recompute heavy volume profile only when new candle or swing moves
var int lastCalculatedBar = -1
bool needsRecalc = (barstate.isconfirmed or lastCalculatedBar != bar_index)

if barstate.islast and needsRecalc
    lastCalculatedBar := bar_index
    recalculateVolumeProfile()
// Drawing repositioning runs live every tick with zero computational lag
```

### 6.3 Drawing Pool Management (500 Element Cap)
TradingView strictly enforces a limit of 500 lines, 500 boxes, and 500 labels per script.
Maintain an active ring buffer:
```pinescript
var box[] boxPool = array.new_box()

addManagedBox(box newBox, int maxAllowed = 100) =>
    array.push(boxPool, newBox)
    if array.size(boxPool) > maxAllowed
        box.delete(array.shift(boxPool))
```

---

## 7. Checklist for Building Volume & Key Level Indicators

- [ ] Target `//@version=6` exclusively.
- [ ] Set `max_bars_back = 1000` when dynamic historical indexing is used.
- [ ] Always guard `request.security` with `lookahead = barmerge.lookahead_off` on historical data or pass closed bars `high[1]`/`low[1]`.
- [ ] Implement automatic fallback from seconds resolution to `1` or `5` minute for non-Premium TV plans.
- [ ] Cluster nearby levels into unified zones to keep charts readable and within the 500-drawing budget.
- [ ] Implement active vPOC mitigation detection and dynamic culling.
- [ ] Use theme-adaptive colors (`#089981` Bull, `#f23645` Bear, `#d98b1f` POC/Accent) with contrasting label text.
- [ ] Provide an on-chart HUD / Dashboard summarizing live Delta, CVD, VAH/VAL/POC status, and nearest Key Level Confluence.
