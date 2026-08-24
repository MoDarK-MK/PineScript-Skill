"""
Lexer and parser for the Pine subset this interpreter executes.

Pine is indentation-structured like Python, but with two wrinkles that shape
everything here:

  1. A wrapped line is NOT marked. There is no backslash and no required
     bracket. `a = b ? c :\n     d` is one statement, and the only signal is
     that the previous line cannot possibly have ended. So continuation is
     decided by looking at what the accumulated text ends with, plus bracket
     depth.

  2. `if` and `switch` are EXPRESSIONS. `x = if cond \n 1 \n else \n 2` is
     legal, and a block's value is the value of its last statement. That single
     rule removes the need for a separate statement/expression split in blocks,
     so it is modelled directly: every Block evaluates to its last value.

The AST is deliberately plain tuples-with-names (small classes, no dataclass
machinery) so the evaluator can pattern-match on `node.kind` cheaply.
"""
import re

KEYWORDS = {
    "if", "else", "for", "to", "by", "in", "while", "switch", "var", "varip",
    "and", "or", "not", "true", "false", "na", "break", "continue", "type",
    "export", "method", "import", "as", "return",
}

TYPE_WORDS = {
    "int", "float", "bool", "string", "color", "label", "line", "box", "table",
    "linefill", "polyline", "chart", "array", "matrix", "map", "simple",
    "series", "const", "input",
}

# Final TOKENS that mean "this line cannot be the end of a statement".
#
# Compared as tokens, never as a text suffix. `=>` ends with the character `>`,
# so suffix matching glued every multi-line function declaration to its first
# body line — and a variable named `x_or` would have done the same against
# `or`. The token is the unit; the character never was.
#
# `=>` is deliberately ABSENT: it introduces a BODY on the following indented
# lines and never continues an expression.
CONTINUATION_TAILS = frozenset({
    "+", "-", "*", "/", "%", "?", ":", ",", "=", "==", "!=", "<", ">", "<=",
    ">=", "(", "[", ":=", "+=", "-=", "*=", "/=", "%=",
})

# The same idea for the word operators, which the lexer classes as keywords.
WORD_TAILS = frozenset({"and", "or", "not"})

TOKEN_RE = re.compile(r"""
    (?P<float>\d+\.\d*(?:[eE][+-]?\d+)?
             |\.\d+(?:[eE][+-]?\d+)?
             |\d+[eE][+-]?\d+)          # 1e-10 has no dot and is still a float
  | (?P<int>\d+)
  | (?P<color>\#[0-9a-fA-F]{6,8})
  | (?P<name>[A-Za-z_]\w*)
  | (?P<op>:=|==|!=|<=|>=|\+=|-=|\*=|/=|%=|=>|[-+*/%<>=?:,.\[\]()])
""", re.VERBOSE)


class PineSyntaxError(Exception):
    def __init__(self, message, line=None):
        super().__init__(f"line {line}: {message}" if line else message)
        self.line = line


class Tok:
    __slots__ = ("kind", "value", "line")

    def __init__(self, kind, value, line):
        self.kind, self.value, self.line = kind, value, line

    def __repr__(self):
        return f"Tok({self.kind},{self.value!r},L{self.line})"


def strip_comment(text):
    """Removes a trailing // comment without touching one inside a string."""
    out, in_str, i = [], None, 0
    while i < len(text):
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in ("'", '"'):
            in_str = ch
            out.append(ch)
        elif ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def logical_lines(source):
    """Yields (line_no, indent, text) for each LOGICAL line.

    Joining is the fiddly part: Pine marks a wrapped line with nothing at all,
    so a line is joined to the previous when brackets are still open, or when
    what we have so far ends on a token that cannot end a statement."""
    lines = source.split("\n")
    buf, buf_line, buf_indent, depth = "", None, 0, 0
    for i, raw in enumerate(lines):
        text = strip_comment(raw)
        if not text.strip():
            continue
        indent = len(text) - len(text.lstrip(" \t"))
        body = text.strip()

        if buf:
            buf += " " + body
        else:
            buf, buf_line, buf_indent = body, i + 1, indent

        depth = 0
        in_str = None
        for j, ch in enumerate(buf):
            if in_str:
                if ch == in_str and buf[j - 1] != "\\":
                    in_str = None
                continue
            if ch in ("'", '"'):
                in_str = ch
            elif ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1

        unfinished = depth > 0
        if not unfinished:
            try:
                toks = tokenize(buf, i + 1)
            except PineSyntaxError:
                toks = []
            if toks:
                last = toks[-1]
                # `and`/`or`/`not` are KEYWORDS, not operators, and a line
                # ending in one is just as unfinished as one ending in `+`.
                # Requiring kind == "op" here silently un-joined every wrapped
                # boolean expression in the repo.
                if ((last.kind == "op" and last.value in CONTINUATION_TAILS)
                        or (last.kind == "kw" and last.value in WORD_TAILS)):
                    unfinished = True
        if unfinished:
            continue
        yield buf_line, buf_indent, buf
        buf, buf_line = "", None
    if buf:
        yield buf_line, buf_indent, buf


def tokenize(text, line_no):
    """Tokenises ONE logical line. Strings are single tokens."""
    toks, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch in " \t":
            i += 1
            continue
        if ch in ("'", '"'):
            quote, j, out = ch, i + 1, []
            while j < len(text):
                if text[j] == "\\" and j + 1 < len(text):
                    nxt = text[j + 1]
                    out.append({"n": "\n", "t": "\t", "\\": "\\",
                                '"': '"', "'": "'"}.get(nxt, nxt))
                    j += 2
                    continue
                if text[j] == quote:
                    break
                out.append(text[j])
                j += 1
            if j >= len(text):
                raise PineSyntaxError("unterminated string", line_no)
            toks.append(Tok("str", "".join(out), line_no))
            i = j + 1
            continue
        m = TOKEN_RE.match(text, i)
        if not m:
            raise PineSyntaxError(f"unexpected character {ch!r}", line_no)
        kind = m.lastgroup
        value = m.group()
        if kind == "float":
            toks.append(Tok("num", float(value), line_no))
        elif kind == "int":
            toks.append(Tok("num", int(value), line_no))
        elif kind == "color":
            toks.append(Tok("color", value, line_no))
        elif kind == "name":
            toks.append(Tok("kw" if value in KEYWORDS else "name", value, line_no))
        else:
            toks.append(Tok("op", value, line_no))
        i = m.end()
    return toks


# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------
class Node:
    __slots__ = ("kind", "line", "a", "b", "c", "d", "uid")
    _counter = [0]

    def __init__(self, kind, line, a=None, b=None, c=None, d=None):
        self.kind, self.line = kind, line
        self.a, self.b, self.c, self.d = a, b, c, d
        Node._counter[0] += 1
        # Every node gets an identity. Stateful builtins (ta.sma and friends)
        # keep their state per CALL SITE, exactly as Pine does — two calls to
        # ta.sma in different places are two independent moving averages.
        self.uid = Node._counter[0]

    def __repr__(self):
        return f"<{self.kind} L{self.line}>"


class Parser:
    def __init__(self, source):
        self.lines = list(logical_lines(source))
        self.pos = 0

    # ---------------- line-level helpers
    def peek_line(self):
        return self.lines[self.pos] if self.pos < len(self.lines) else None

    def block(self, parent_indent):
        """Parses every statement indented past parent_indent."""
        stmts = []
        while True:
            nxt = self.peek_line()
            if nxt is None or nxt[1] <= parent_indent:
                break
            stmts.append(self.statement())
        if not stmts:
            raise PineSyntaxError("expected an indented block",
                                  self.lines[self.pos - 1][0] if self.pos else None)
        return stmts

    # ---------------- statements
    def statement(self):
        line_no, indent, text = self.lines[self.pos]
        self.pos += 1
        toks = tokenize(text, line_no)
        self.toks, self.ti, self.line_no, self.indent = toks, 0, line_no, indent

        if self.at_kw("type"):
            return self.parse_type_def()
        if self.at_kw("if"):
            return self.parse_if()
        if self.at_kw("for"):
            return self.parse_for()
        if self.at_kw("while"):
            return self.parse_while()
        if self.at_kw("else"):
            raise PineSyntaxError(
                "`else` with no matching `if` at the same indent. If this looks "
                "correct, the block above it is misindented.", line_no)
        if self.at_kw("break"):
            return Node("break", line_no)
        if self.at_kw("continue"):
            return Node("continue", line_no)

        func = self.try_parse_func_def()
        if func is not None:
            return func
        return self.parse_simple()

    def at_kw(self, word):
        t = self.cur()
        return t is not None and t.kind == "kw" and t.value == word

    def at_op(self, *values):
        """True when the token at the cursor is an OPERATOR with one of these
        texts.

        The kind check is the entire point. A string literal token carries its
        contents in .value, so `cur().value == "-"` is true for the string "-"
        — which is how `(v >= 0 ? "+" : "")` came to parse its "+" as a unary
        plus. Any operator that can also be a whole string literal hits this,
        and "+", "-", ":" and "," all appear as literals in formatting code."""
        t = self.cur()
        return t is not None and t.kind == "op" and t.value in values

    def next_is_op(self, offset, *values):
        t = self.cur(offset)
        return t is not None and t.kind == "op" and t.value in values

    def cur(self, offset=0):
        i = self.ti + offset
        return self.toks[i] if i < len(self.toks) else None

    def eat(self, kind=None, value=None):
        t = self.cur()
        if t is None:
            raise PineSyntaxError("unexpected end of line", self.line_no)
        if kind and t.kind != kind:
            raise PineSyntaxError(f"expected {kind}, got {t.value!r}", self.line_no)
        if value is not None and t.value != value:
            raise PineSyntaxError(f"expected {value!r}, got {t.value!r}", self.line_no)
        self.ti += 1
        return t

    def accept(self, kind, value=None):
        t = self.cur()
        if t and t.kind == kind and (value is None or t.value == value):
            self.ti += 1
            return t
        return None

    def try_parse_func_def(self):
        """`name(params) =>` — possibly `export name(...)` or `method name(...)`.

        Detected by scanning for a top-level `=>` after a balanced paren group,
        which is unambiguous and cheaper than backtracking a full parse."""
        start = self.ti
        if self.at_kw("export") or self.at_kw("method"):
            self.ti += 1
        t = self.cur()
        if not t or t.kind != "name" or not self.next_is_op(1, "("):
            self.ti = start
            return None
        name = t.value
        self.ti += 1
        depth, j = 0, self.ti
        while j < len(self.toks):
            v = self.toks[j].value
            if v == "(":
                depth += 1
            elif v == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j + 1 >= len(self.toks) or self.toks[j + 1].value != "=>":
            self.ti = start
            return None

        # Split on top-level commas FIRST. Walking token by token turned
        # `float o` into two parameters, because a type word in front looks
        # exactly like a parameter of its own until you know where the commas
        # are.
        self.eat("op", "(")
        groups, current, depth = [], [], 1
        while True:
            tok = self.cur()
            if tok is None:
                raise PineSyntaxError("unclosed parameter list", self.line_no)
            self.ti += 1
            if tok.kind == "op" and tok.value in ("(", "["):
                depth += 1
            elif tok.kind == "op" and tok.value in (")", "]"):
                depth -= 1
                if depth == 0:
                    if current:
                        groups.append(current)
                    break
            if depth == 1 and tok.kind == "op" and tok.value == ",":
                groups.append(current)
                current = []
                continue
            current.append(tok)

        params = []
        for group in groups:
            eq = next((k for k, tk in enumerate(group)
                       if tk.kind == "op" and tk.value == "="), None)
            head = group[:eq] if eq is not None else group
            names = [tk.value for tk in head if tk.kind in ("name", "kw")]
            if not names:
                raise PineSyntaxError("parameter without a name", self.line_no)
            default = None
            if eq is not None:
                saved = (self.toks, self.ti)
                self.toks, self.ti = group[eq + 1:], 0
                default = self.expression()
                self.toks, self.ti = saved
            params.append((names[-1], default))
        self.eat("op", "=>")

        if self.ti < len(self.toks):          # single-line body
            body = [Node("expr", self.line_no, self.expression())]
        else:
            body = self.block(self.indent)
        return Node("funcdef", self.line_no, name, params, body)

    def parse_type_def(self):
        self.eat("kw", "type")
        name = self.eat("name").value
        fields = []
        parent_indent = self.indent
        while True:
            nxt = self.peek_line()
            if nxt is None or nxt[1] <= parent_indent:
                break
            fline, _fi, ftext = nxt
            self.pos += 1
            ftoks = tokenize(ftext, fline)
            # `float lo` or `array<float> buyRows` or `float lo = 0.0`
            k = 0
            while k < len(ftoks) and ftoks[k].value in ("<", ">") or (
                    k < len(ftoks) - 1 and ftoks[k + 1].value in ("<", ">", ".")):
                k += 1
            fname = None
            for tok in reversed(ftoks):
                if tok.kind == "name":
                    fname = tok.value
                    break
            eq = next((i for i, tk in enumerate(ftoks)
                       if tk.kind == "op" and tk.value == "="), None)
            default = None
            if eq is not None:
                fname = ftoks[eq - 1].value
                saved = (self.toks, self.ti, self.line_no)
                self.toks, self.ti, self.line_no = ftoks, eq + 1, fline
                default = self.expression()
                self.toks, self.ti, self.line_no = saved
            fields.append((fname, default))
        return Node("typedef", self.line_no, name, fields)

    def parse_if(self):
        # Captured BEFORE the body is parsed. self.indent belongs to whichever
        # statement is being parsed right now, and block() parses nested ones —
        # so reading it afterwards yields the indent of the LAST line of the
        # body. That made every `else` fail to match its `if`, get parsed as a
        # separate statement, and run UNCONDITIONALLY.
        my_indent = self.indent
        my_line = self.line_no
        self.eat("kw", "if")
        cond = self.expression()
        body = self.block(my_indent)
        else_body = None
        nxt = self.peek_line()
        if nxt is not None and nxt[1] == my_indent and nxt[2].startswith("else"):
            eline, eindent, etext = nxt
            self.pos += 1
            self.toks = tokenize(etext, eline)
            self.ti, self.line_no, self.indent = 0, eline, eindent
            self.eat("kw", "else")
            if self.at_kw("if"):
                else_body = [self.parse_if()]
            else:
                else_body = self.block(eindent)
        self.indent = my_indent
        return Node("if", my_line, cond, body, else_body)

    def parse_for(self):
        self.eat("kw", "for")
        # `for [k, v] in arr` | `for x in arr` | `for i = a to b (by s)`
        if self.at_op("["):
            self.eat("op", "[")
            names = []
            while not self.accept("op", "]"):
                names.append(self.eat("name").value)
                self.accept("op", ",")
            self.eat("kw", "in")
            iterable = self.expression()
            body = self.block(self.indent)
            return Node("forin", self.line_no, names, iterable, body)
        name = self.eat("name").value
        if self.accept("kw", "in"):
            iterable = self.expression()
            body = self.block(self.indent)
            return Node("forin", self.line_no, [name], iterable, body)
        self.eat("op", "=")
        start = self.expression()
        self.eat("kw", "to")
        end = self.expression()
        step = self.expression() if self.accept("kw", "by") else None
        body = self.block(self.indent)
        return Node("for", self.line_no, (name, start, end, step), body)

    def parse_while(self):
        self.eat("kw", "while")
        cond = self.expression()
        body = self.block(self.indent)
        return Node("while", self.line_no, cond, body)

    def parse_simple(self):
        """Declaration, assignment, or a bare expression."""
        start = self.ti
        qualifier = None
        if self.at_kw("var") or self.at_kw("varip"):
            qualifier = self.eat().value

        # Tuple destructuring: `[a, b] = expr`
        if self.at_op("[") and qualifier is None:
            save = self.ti
            self.eat("op", "[")
            names, ok = [], True
            while True:
                t = self.cur()
                if t is None:
                    ok = False
                    break
                if t.kind == "op" and t.value == "]":
                    self.ti += 1
                    break
                if t.kind != "name":
                    ok = False
                    break
                names.append(self.eat().value)
                self.accept("op", ",")
            if ok and self.at_op("="):
                self.eat("op", "=")
                return Node("tupledecl", self.line_no, names, self.expression())
            self.ti = save

        # Optional type words before the name: `int x = ...`, `array<float> a = ...`
        type_words = []
        while True:
            t = self.cur()
            if t is None or t.kind not in ("name", "kw"):
                break
            nxt = self.cur(1)
            if t.value in TYPE_WORDS and self.next_is_op(1, "<"):
                type_words.append(self.eat().value)
                depth = 0
                while self.cur():
                    v = self.eat().value
                    if v == "<":
                        depth += 1
                    elif v == ">":
                        depth -= 1
                        if depth == 0:
                            break
                continue
            # A bare type word followed by a NAME is a declaration type.
            if nxt and nxt.kind == "name" and (t.value in TYPE_WORDS or t.kind == "name"):
                if t.kind == "kw" and t.value not in TYPE_WORDS:
                    break
                type_words.append(self.eat().value)
                continue
            break

        t = self.cur()
        if t and t.kind == "name" and self.next_is_op(
                1, "=", ":=", "+=", "-=", "*=", "/=", "%="):
            name = self.eat().value
            op = self.eat().value
            value = self.expression_or_block()
            if op == "=":
                return Node("decl", self.line_no, (qualifier, name), value, type_words)
            return Node("assign", self.line_no, name, value, op)

        # Member assignment: `p.lo := 1`
        if t and t.kind == "name" and self.next_is_op(1, "."):
            save = self.ti
            target = self.postfix(self.primary())
            if self.at_op(":=", "+=", "-=", "*=", "/=", "%="):
                op = self.eat().value
                return Node("setattr", self.line_no, target, self.expression(), op)
            self.ti = save

        self.ti = start if qualifier is None else self.ti
        return Node("expr", self.line_no, self.expression_or_block())

    def expression_or_block(self):
        """RHS may be an `if`/`switch` block, which in Pine is an expression."""
        if self.at_kw("if"):
            return self.parse_if()
        if self.at_kw("switch"):
            return self.parse_switch()
        return self.expression()

    def parse_switch(self):
        self.eat("kw", "switch")
        subject = None
        if self.ti < len(self.toks):
            subject = self.expression()
        cases, default = [], None
        parent_indent = self.indent
        while True:
            nxt = self.peek_line()
            if nxt is None or nxt[1] <= parent_indent:
                break
            cline, cindent, ctext = nxt
            self.pos += 1
            ctoks = tokenize(ctext, cline)
            arrow = next((i for i, tk in enumerate(ctoks)
                          if tk.kind == "op" and tk.value == "=>"), None)
            if arrow is None:
                raise PineSyntaxError("switch case without =>", cline)
            saved = (self.toks, self.ti, self.line_no, self.indent)
            if arrow == 0:
                self.toks, self.ti, self.line_no, self.indent = ctoks, 1, cline, cindent
                default = self.expression() if self.ti < len(ctoks) else \
                    Node("block", cline, self.block(cindent))
            else:
                self.toks, self.ti, self.line_no, self.indent = ctoks, 0, cline, cindent
                label = self.expression()
                self.eat("op", "=>")
                value = self.expression() if self.ti < len(ctoks) else \
                    Node("block", cline, self.block(cindent))
                cases.append((label, value))
            self.toks, self.ti, self.line_no, self.indent = saved
        return Node("switch", self.line_no, subject, cases, default)

    # ---------------- expressions (precedence climbing)
    def expression(self):
        return self.ternary()

    def ternary(self):
        cond = self.logic_or()
        if self.accept("op", "?"):
            a = self.ternary()
            self.eat("op", ":")
            b = self.ternary()
            return Node("ternary", self.line_no, cond, a, b)
        return cond

    def logic_or(self):
        left = self.logic_and()
        while self.at_kw("or"):
            self.ti += 1
            left = Node("binary", self.line_no, "or", left, self.logic_and())
        return left

    def logic_and(self):
        left = self.equality()
        while self.at_kw("and"):
            self.ti += 1
            left = Node("binary", self.line_no, "and", left, self.equality())
        return left

    def equality(self):
        left = self.comparison()
        while self.at_op("==", "!="):
            op = self.eat().value
            left = Node("binary", self.line_no, op, left, self.comparison())
        return left

    def comparison(self):
        left = self.additive()
        while self.at_op("<", ">", "<=", ">="):
            op = self.eat().value
            left = Node("binary", self.line_no, op, left, self.additive())
        return left

    def additive(self):
        left = self.multiplicative()
        while self.at_op("+", "-"):
            op = self.eat().value
            left = Node("binary", self.line_no, op, left, self.multiplicative())
        return left

    def multiplicative(self):
        left = self.unary()
        while self.at_op("*", "/", "%"):
            op = self.eat().value
            left = Node("binary", self.line_no, op, left, self.unary())
        return left

    def unary(self):
        if self.at_kw("not"):
            self.ti += 1
            return Node("unary", self.line_no, "not", self.unary())
        if self.at_op("-"):
            self.ti += 1
            return Node("unary", self.line_no, "-", self.unary())
        if self.at_op("+"):
            self.ti += 1
            return self.unary()
        return self.postfix(self.primary())

    def postfix(self, node):
        while True:
            t = self.cur()
            if t is None:
                return node
            if t.kind != "op":
                return node
            if t.value == ".":
                self.ti += 1
                node = Node("member", self.line_no, node, self.eat().value)
            elif t.value == "(":
                self.ti += 1
                args = []
                while not self.accept("op", ")"):
                    name = None
                    if (self.cur() and self.cur().kind in ("name", "kw")
                            and self.next_is_op(1, "=")
                            and not self.next_is_op(2, "=")):
                        name = self.eat().value
                        self.eat("op", "=")
                    args.append((name, self.expression()))
                    self.accept("op", ",")
                node = Node("call", self.line_no, node, args)
            elif t.kind == "op" and t.value == "<" and self.generic_span() is not None:
                # `array.new<float>(0)` — the angle brackets are a TYPE
                # argument, not two comparisons. Without this the expression
                # parser reads `array.new < float > (0)` and compares two
                # namespaces, which is exactly as confusing as it sounds.
                self.ti = self.generic_span()
                continue
            elif t.value == "[":
                self.ti += 1
                offset = self.expression()
                self.eat("op", "]")
                node = Node("history", self.line_no, node, offset)
            else:
                return node

    def generic_span(self):
        """If the `<` at the cursor opens a TYPE argument list, returns the
        index just past its `>`; otherwise None.

        The test is deliberately strict: everything between the angles must be
        a name, a comma or another angle, and the token straight after the
        closing `>` must be `(`. A real comparison cannot look like that, so
        this cannot swallow one."""
        i, depth = self.ti, 0
        while i < len(self.toks):
            tok = self.toks[i]
            v = tok.value if tok.kind == "op" else None
            if v == "<":
                depth += 1
            elif v == ">":
                depth -= 1
                if depth == 0:
                    nxt = self.toks[i + 1] if i + 1 < len(self.toks) else None
                    return i + 1 if nxt is not None and nxt.value == "(" else None
            elif tok.kind in ("name", "kw") or v == ",":
                pass
            else:
                return None
            i += 1
        return None

    def primary(self):
        t = self.cur()
        if t is None:
            raise PineSyntaxError("unexpected end of expression", self.line_no)
        if t.kind == "num":
            self.ti += 1
            return Node("num", self.line_no, t.value)
        if t.kind == "str":
            self.ti += 1
            return Node("str", self.line_no, t.value)
        if t.kind == "color":
            self.ti += 1
            return Node("color", self.line_no, t.value)
        if t.kind == "kw" and t.value in ("true", "false"):
            self.ti += 1
            return Node("bool", self.line_no, t.value == "true")
        if t.kind == "kw" and t.value == "na":
            # `na` the LITERAL and `na(x)` the FUNCTION are the same word. A
            # following `(` is the only thing that separates them, and reading
            # it as the literal made every na() check an uncallable value.
            self.ti += 1
            if self.next_is_op(0, "("):
                return Node("name", self.line_no, "na")
            return Node("na", self.line_no)
        if t.kind == "kw" and t.value in ("if", "switch"):
            return self.expression_or_block()
        if t.kind == "op" and t.value == "(":
            self.ti += 1
            inner = self.expression()
            self.eat("op", ")")
            return inner
        if t.kind == "op" and t.value == "[":
            self.ti += 1
            items = []
            while not self.accept("op", "]"):
                items.append(self.expression())
                self.accept("op", ",")
            return Node("tuple", self.line_no, items)
        if t.kind in ("name", "kw"):
            self.ti += 1
            return Node("name", self.line_no, t.value)
        raise PineSyntaxError(f"unexpected token {t.value!r}", self.line_no)


def parse(source):
    p = Parser(source)
    stmts = []
    while p.peek_line() is not None:
        stmts.append(p.statement())
    return stmts
