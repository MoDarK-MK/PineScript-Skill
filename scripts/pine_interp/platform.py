"""
Platform constants and the values TradingView supplies that a machine offline
cannot.

Every entry here is a decision about what to say when there is no real answer,
and the decisions are not uniform on purpose:

  * `barstate.isconfirmed` is TRUE, always. This interpreter runs confirmed
    bars only, so that is not a stand-in — it is the truth about this run.

  * `barstate.isrealtime` is FALSE for the same reason.

  * `request.security_lower_tf()` returns na. There is no intrabar data
    offline and inventing some would produce a profile that looks measured and
    is fabricated. A well-written script HANDLES that na — this repo's own
    indicator falls back to its bar-level model — so returning na exercises
    the fallback path rather than hiding it.

  * `request.security()` on the SAME symbol at a higher timeframe returns the
    chart value. That is an approximation and it is flagged in the run report,
    because a higher-timeframe value is genuinely different data.

Anything not listed raises rather than resolving to a mystery object.
"""
from .runtime import NA


def timeframe_seconds(tf):
    """"5" -> 300, "1H" -> 3600, "30S" -> 30, "1D" -> 86400."""
    if not isinstance(tf, str) or not tf:
        return NA
    text = tf.strip().upper()
    unit, digits = "", ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        else:
            unit += ch
    count = int(digits) if digits else 1
    return count * {"": 60, "S": 1, "D": 86400, "W": 604800, "M": 2592000}.get(unit, 60)


class Platform:
    """Per-run symbol and chart settings, overridable by the harness."""

    def __init__(self, mintick=0.01, ticker="TEST", timeframe="5",
                 pointvalue=1.0, currency="USD"):
        self.mintick = mintick
        self.ticker = ticker
        self.timeframe = timeframe
        self.pointvalue = pointvalue
        self.currency = currency

    def constants(self, interp):
        """Resolves a dotted path to a value, or returns MISSING."""
        return {
            "barstate.isconfirmed": True,
            "barstate.islast": interp.is_last,
            "barstate.isrealtime": False,
            "barstate.ishistory": not interp.is_last,
            "barstate.isfirst": interp.bar_index == 0,
            "barstate.isnew": True,
            "barstate.islastconfirmedhistory": interp.is_last,

            "syminfo.mintick": self.mintick,
            "syminfo.ticker": self.ticker,
            "syminfo.tickerid": self.ticker,
            "syminfo.pointvalue": self.pointvalue,
            "syminfo.currency": self.currency,
            "syminfo.type": "crypto",

            "timeframe.period": self.timeframe,
            "timeframe.isintraday": timeframe_seconds(self.timeframe) < 86400,
            "timeframe.isdaily": timeframe_seconds(self.timeframe) == 86400,
            "timeframe.multiplier": int("".join(
                c for c in self.timeframe if c.isdigit()) or 1),

            "bar_index": interp.bar_index,
            "last_bar_index": (len(interp.bars) - 1),
        }


# Enum-ish constants that only ever get passed around. Their identity matters
# (array.sort checks for `order.descending`), their value does not.
PASSTHROUGH_PREFIXES = (
    "color.", "size.", "location.", "shape.", "display.", "position.",
    "extend.", "order.", "alert.", "format.", "text.", "scale.", "plot.",
    "hline.", "line.style_", "label.style_", "barmerge.", "session.",
    "dayofweek.", "currency.", "math.pi", "math.e", "xloc.", "yloc.", "font.",
    "strategy.", "adjustment.", "settlement_as_close.", "earnings.",
    "dividends.", "splits.", "backadjustment.",
)
