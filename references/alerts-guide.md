# Alerts Guide

Every script in this repo fires alerts. None of them could be wired to anything
automatically, because the message was a fixed string with no data in it. This
file closes that gap.

---

## 1. `alertcondition()` vs `alert()` — they are not alternatives

They solve different problems and a serious script usually wants both.

| | `alertcondition()` | `alert()` |
|---|---|---|
| Evaluated | Compile time | Runtime, when reached |
| Message | **Constant string** — no `str.tostring()` | Any expression |
| Appears in the alert dialog as | Its own named condition | "Any alert() function call" |
| Scope | Global only | Anywhere it executes |
| Frequency control | In the dialog | In code, via `freq =` |
| Strategies | Works, rarely what you want | Works |

`alertcondition()` gives the user a **named** condition to pick from a dropdown,
which is the discoverable, self-documenting option. Its cost is that the message
cannot contain live values — only placeholders (§3).

`alert()` can say anything, including formatted numbers and JSON. Its cost is
that every `alert()` in the script shares one dialog entry, so the user cannot
choose between them; the script decides.

```pinescript
// Discoverable: one named condition per signal.
alertcondition(bullSignal, "Bullish Reversal", "Bullish reversal on {{ticker}} {{interval}}")

// Actionable: real values, real payload.
if bullSignal
    alert(str.format("BUY {0} @ {1} score {2}", syminfo.ticker, close, score),
         alert.freq_once_per_bar_close)
```

---

## 2. Frequency — the parameter that decides whether alerts are trustworthy

```pinescript
alert.freq_once_per_bar         // first time the condition is true in the bar
alert.freq_once_per_bar_close   // only on the bar's close
alert.freq_all                  // every tick the condition holds  (rarely right)
```

`freq_once_per_bar` fires **mid-bar**, on a condition that can still disappear
before the bar closes. That is the same problem `barstate.isconfirmed` exists to
solve, and it is why every signal alert in this repo defaults to bar close.

Use `freq_all` only for something that genuinely is about ticks — a price
crossing a level you want to know about immediately, accepting that it may
un-cross.

> The honest framing: `freq_once_per_bar_close` gives fewer alerts, later, that
> are true. `freq_once_per_bar` gives more, sooner, some of which never
> happened.

---

## 3. Placeholders (`alertcondition` messages only)

Filled in by TradingView when the alert fires. They do **not** work in `alert()`
— there the values are already available as real variables.

| Placeholder | Gives |
|---|---|
| `{{ticker}}` | `EURUSD` |
| `{{exchange}}` | `OANDA` |
| `{{interval}}` | `5` |
| `{{close}}` `{{open}}` `{{high}}` `{{low}}` `{{volume}}` | The bar's values |
| `{{time}}` | Bar time, UTC |
| `{{timenow}}` | When the alert fired, UTC |
| `{{plot_0}}`, `{{plot("My Title")}}` | A plotted series' value |

`{{plot("...")}}` is the escape hatch for getting a computed number into an
`alertcondition` message: plot the value (with `display = display.none` if it
should not be on the chart) and reference it by title.

### Strategy alerts

In a strategy's alert message, these describe the order that triggered it:

| Placeholder | Gives |
|---|---|
| `{{strategy.order.action}}` | `buy` / `sell` |
| `{{strategy.order.contracts}}` | Quantity |
| `{{strategy.order.price}}` | Fill price |
| `{{strategy.order.id}}` | The entry/exit id |
| `{{strategy.order.alert_message}}` | The `alert_message =` you passed to the order call |
| `{{strategy.position_size}}` | Position size after the order |
| `{{strategy.market_position}}` | `long` / `short` / `flat` |

`alert_message =` on each `strategy.entry()` / `strategy.exit()` is the clean
way to give every order its own payload without a separate alert per order.

---

## 4. Webhook payloads

A TradingView alert can POST its message body to a URL. The message becomes the
body **verbatim** — so if the body is valid JSON, the receiver gets JSON.

Two rules decide whether this works:

1. **The JSON must be valid after substitution.** Placeholders are string
   replacements; TradingView does not validate the result.
2. **Quote anything that could arrive empty.** `{{strategy.order.contracts}}`
   unquoted becomes `"qty": ` if it is ever blank, and that is a parse error at
   the receiver, not at TradingView.

### From an `alertcondition` (placeholders)

```
{"ticker":"{{ticker}}","exchange":"{{exchange}}","tf":"{{interval}}","action":"reversal_bull","price":"{{close}}","time":"{{timenow}}"}
```

### From `alert()` (real values — preferred)

```pinescript
// Building the payload in code means it can be validated in code.
alertJson(string action, float price, int score) =>
    str.format(
         '{{"ticker":"{0}","exchange":"{1}","tf":"{2}","action":"{3}",' +
         '"price":"{4}","score":{5},"time":"{6}"}}',
         syminfo.ticker, syminfo.prefix, timeframe.period, action,
         str.tostring(price, format.mintick), score,
         str.format_time(timenow, "yyyy-MM-dd'T'HH:mm:ss'Z'", "UTC"))

if bullSignal
    alert(alertJson("buy", close, score), alert.freq_once_per_bar_close)
```

Note the doubled braces: `str.format()` treats `{` as a placeholder delimiter,
so a literal brace is written `{{`. Getting this wrong produces a runtime error
in `str.format`, not malformed JSON — which is the good failure mode.

---

## 5. Security, plainly

The alert message is sent to whatever URL the user configures, over the public
internet, to an endpoint TradingView does not authenticate on your behalf.

- **Never put an API key, secret or token in an alert message.** Anyone able to
  see the alert configuration can read it, and the payload travels to a URL that
  is a plain text field.
- Authenticate at the receiver by giving each user a **unique, revocable URL
  path**, not by embedding a shared secret in the payload.
- Treat every field as untrusted at the receiver. An alert body is user-supplied
  input arriving over HTTP; validate it like any other.

---

## 6. Limits worth knowing before designing around them

- Alert message length is capped. A verbose JSON payload with long strings can
  be truncated, which produces invalid JSON at the receiver — test with your
  longest realistic values, not your shortest.
- `alertcondition()` counts against the **64 plot-count limit** (PINE009). Ten
  named conditions is ten plot counts.
- Alerts are created by the user on their chart; a script cannot create one.
  Anything the user must do is documentation, not code, and belongs in the
  publish description — which is what `release/PUBLISH_DESCRIPTION.md` and
  `release/INPUTS.md` are for.

---

## 7. Checklist

- [ ] Every signal alert defaults to `barstate.isconfirmed` or
      `alert.freq_once_per_bar_close`
- [ ] Named `alertcondition()`s exist for the signals a user would pick from a
      dropdown
- [ ] `alert()` is used where the message needs live values
- [ ] Webhook JSON quotes every substituted field
- [ ] No secrets in any message
- [ ] Alert count checked against the plot-count budget (PINE009)
- [ ] The payload has been tested against the receiver with a real alert, not
      just read
