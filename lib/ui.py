"""Quiet mission-control for the terminal: one cyan accent, generous whitespace, symbols carry state, nothing else shouts."""

import locale
import os
import re
import shutil
import sys
import threading
import time

# Palette: 5 semantic roles, plain ANSI, stdlib only.
_ACCENT = "36"   # cyan: ids, commands, the one thing to look at
_SUCCESS = "32"  # green: done, ok
_WARNING = "33"  # yellow: running, lost, needs attention
_ERROR = "31"    # red: failed, errors
_DIM = "90"      # gray: secondary text, timestamps, hints

_NO_COLOR_FLAG = False
_DEBUG_FLAG = False


def configure(no_color=False, debug=False):
    """Called once from hth.main() after argparse. All color decisions flow from here."""
    global _NO_COLOR_FLAG, _DEBUG_FLAG
    _NO_COLOR_FLAG = bool(no_color)
    _DEBUG_FLAG = bool(debug)


def is_debug():
    return _DEBUG_FLAG


def _no_color_env():
    # NO_COLOR spec: present (any value, even empty) means disable.
    return "NO_COLOR" in os.environ


def _force_color_env():
    # Escape hatch for demos/screenshots only. Real pipes stay plain.
    v = os.environ.get("HTH_FORCE_COLOR", "")
    return v not in ("", "0", "false", "False", "no")


def use_color(stream="stdout"):
    if _NO_COLOR_FLAG:
        return False
    if _no_color_env():
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    if _force_color_env():
        return True
    try:
        fh = sys.stdout if stream == "stdout" else sys.stderr
        return fh.isatty()
    except Exception:
        return False


def supports_unicode():
    if os.environ.get("HTH_ASCII", "") in ("1", "true", "True"):
        return False
    if os.environ.get("NO_UNICODE", "") not in ("", "0"):
        return False
    enc = getattr(sys.stdout, "encoding", None) or locale.getpreferredencoding(False) or ""
    enc = str(enc).lower().replace("-", "").replace("_", "")
    if enc in ("utf8", "utf"):
        return True
    # Common CI pipes report utf-8; unknown or ascii-only -> fallback.
    lang = os.environ.get("LANG", "") + os.environ.get("LC_ALL", "")
    if "UTF" in lang.upper():
        return True
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def c(text, role):
    """Colorize text for a semantic role, or return plain when color is off."""
    codes = {
        "accent": _ACCENT,
        "success": _SUCCESS,
        "warning": _WARNING,
        "error": _ERROR,
        "dim": _DIM,
        "bold": "1",
    }
    if role not in codes:
        return text
    # stdout/stderr may differ; default to stdout, errors explicitly use stream="stderr".
    if not use_color("stdout"):
        return text
    return "\x1b[%sm%s\x1b[0m" % (codes[role], text)


def _c_err(text, role):
    codes = {"accent": _ACCENT, "success": _SUCCESS, "warning": _WARNING,
             "error": _ERROR, "dim": _DIM, "bold": "1"}
    if role not in codes or not use_color("stderr"):
        return text
    return "\x1b[%sm%s\x1b[0m" % (codes[role], text)


def out(text=""):
    sys.stdout.write(str(text) + "\n")
    sys.stdout.flush()


def err(text=""):
    sys.stderr.write(str(text) + "\n")
    sys.stderr.flush()


def blank():
    out("")


def dim(text):
    return c(text, "dim")


def accent(text):
    return c(text, "accent")


def banner(title="hth", subtitle="hand off heavy work to Cloud Shell"):
    uni = supports_unicode() and use_color("stdout")
    mark = "◈" if uni else "+"
    out("%s %s" % (_c_mark(mark, "accent"), c(title, "bold") if use_color("stdout") else title))
    out(dim("  %s" % subtitle))
    blank()


def _c_mark(text, role):
    return c(text, role)


# ---------- status badges ----------

_BADGES = {
    # state: (unicode symbol, ascii fallback, role, label)
    "running": ("●", ">", "warning", "running"),
    "done": ("✔", "ok", "success", "done"),
    "failed": ("✘", "x", "error", "failed"),
    "lost": ("◌", "!", "warning", "lost"),
    "missing": ("◌", "!", "warning", "lost"),
    "queued": ("○", "-", "dim", "queued"),
    "killed": ("■", "#", "dim", "killed"),
    "dry-run": ("○", "-", "dim", "dry-run"),
}

_BADGE_ORDER = ["running", "done", "failed", "lost", "queued"]


def badge(status):
    key = str(status or "").lower()
    if key.startswith("failed"):
        key = "failed"
    if key in ("missing",):
        key = "missing"
    sym_u, sym_a, role, label = _BADGES.get(key, ("·", "-", "dim", key or "?"))
    sym = sym_u if supports_unicode() else sym_a
    text = "%s %s" % (sym, label)
    if not use_color("stdout"):
        return text
    return c(text, role)


def badge_legend():
    return "  ".join(badge(s) for s in _BADGE_ORDER)


# ---------- tables ----------

def terminal_width(default=100):
    try:
        w = shutil.get_terminal_size().columns
        return max(40, min(160, int(w)))
    except Exception:
        return default


def truncate(text, width):
    text = str(text)
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 1] + "…"


def table(headers, rows, min_widths=None):
    """Aligned columns, whitespace-separated, truncated to terminal width. No borders."""
    if not rows:
        return
    n = len(headers)
    widths = [len(h) for h in headers]
    for r in rows:
        for i in range(n):
            widths[i] = max(widths[i], len(_plain(str(r[i]) if i < len(r) else "")))
    total = terminal_width()
    # Reserve 2 spaces between columns.
    avail = total - 2 * (n - 1)
    # Last column (usually elapsed/exit) stays fixed; shrink id/command first.
    # Simple policy: cap command column, then id column.
    caps = [None] * n
    if n >= 2:
        caps[1] = 42  # command
    caps[0] = 24      # id
    for i in range(n):
        if caps[i] is not None:
            widths[i] = min(widths[i], caps[i])
    while sum(widths) > avail and max(widths) > 8:
        i = max(range(n), key=lambda k: widths[k])
        if widths[i] <= 8:
            break
        widths[i] -= 1
    if min_widths:
        for i, m in enumerate(min_widths):
            if i < n:
                widths[i] = max(widths[i], m)
    # Header in dim.
    head = "  ".join(_pad(headers[i], widths[i]) for i in range(n)).rstrip()
    if use_color("stdout"):
        out(c(head, "dim"))
    else:
        out(head)
    for r in rows:
        cells = [(str(r[i]) if i < len(r) else "") for i in range(n)]
        # Truncate plain length but keep color codes: truncate first, then badge/color already applied?
        # Callers pass pre-colored badges; _plain() measured them. Truncating colored strings
        # naively could cut escape codes, so only truncate uncolored columns (id/command).
        line_parts = []
        for i in range(n):
            cell = cells[i]
            plain = _plain(cell)
            if len(plain) > widths[i]:
                if "\x1b[" in cell:
                    cell = plain[: widths[i] - 1] + "…" if widths[i] > 1 else plain[: widths[i]]
                else:
                    cell = truncate(cell, widths[i])
                line_parts.append(_pad(cell, widths[i]))
            else:
                # pad by plain length so colors don't break alignment
                line_parts.append(cell + " " * (widths[i] - len(plain)))
        out("  ".join(line_parts).rstrip())


def _plain(text):
    return re.sub(r"\x1b\[[0-9;]*m", "", text or "")


def _pad(text, width):
    p = len(_plain(text))
    if p >= width:
        return text
    return text + " " * (width - p)


# ---------- single-line progress ----------

class step:
    """Single-line spinner that resolves to check/cross + duration.

    TTY: animates on stderr, resolves in place.
    Pipes/CI/no-color: prints nothing at start, one plain line at the end.
    """

    FRAMES_U = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    FRAMES_A = ["-", "\\", "|", "/"]

    def __init__(self, label):
        self.label = label
        self._t0 = None
        self._stop = False
        self._thread = None
        self._tty = use_color("stderr") and sys.stderr.isatty()

    def __enter__(self):
        self._t0 = time.monotonic()
        if self._tty:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        dt = time.monotonic() - (self._t0 or time.monotonic())
        if self._thread is not None:
            self._stop = True
            try:
                self._thread.join(timeout=0.5)
            except Exception:
                pass
            sys.stderr.write("\r\x1b[K")
        if exc_type is None:
            self.succeed("(%.1fs)" % dt)
        else:
            self.fail("(%.1fs)" % dt)
        return False

    def _spin(self):
        frames = self.FRAMES_U if supports_unicode() else self.FRAMES_A
        i = 0
        while not self._stop:
            f = frames[i % len(frames)]
            sys.stderr.write("\r%s %s" % (f, self.label))
            sys.stderr.flush()
            time.sleep(0.08)
            i += 1

    def succeed(self, suffix=""):
        uni = supports_unicode()
        mark = "✔" if uni else "ok"
        msg = "%s %s %s" % (mark, self._past(self.label), suffix or "")
        msg = msg.rstrip()
        if use_color("stderr"):
            err(_c_err(msg, "success"))
        else:
            # Plain, prefixed so pipes stay greppable.
            err("ok: %s %s" % (self._past(self.label), suffix or ""))

    def fail(self, suffix=""):
        uni = supports_unicode()
        mark = "✘" if uni else "x"
        msg = "%s %s %s" % (mark, self.label, suffix or "")
        if use_color("stderr"):
            err(_c_err(msg.strip(), "error"))
        else:
            err("failed: %s %s" % (self.label, suffix or ""))

    @staticmethod
    def _past(label):
        # "Starting X" -> "Started X". Fallback: label unchanged.
        mapping = [
            ("Starting", "Started"),
            ("Creating", "Created"),
            ("Copying", "Copied"),
            ("Launching", "Launched"),
            ("Checking", "Checked"),
            ("Fetching", "Fetched"),
            ("Killing", "Killed"),
            ("Cleaning", "Cleaned"),
            ("Pulling", "Pulled"),
        ]
        for a, b in mapping:
            if label.startswith(a):
                return b + label[len(a):]
        return label


# ---------- logs ----------

_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)")
_ERR_RE = re.compile(r"(?i)\b(error|exception|traceback|failed|fail|fatal|denied|quota|exhausted)\b")


def format_log_line(line):
    line = line.rstrip("\n")
    if not use_color("stdout"):
        return line
    m = _TS_RE.search(line)
    if m:
        line = line.replace(m.group(1), c(m.group(1), "dim"), 1)
    if _ERR_RE.search(line):
        return c(line, "error")
    if "[hth]" in line:
        return line.replace("[hth]", c("[hth]", "dim"), 1)
    return line


def print_logs(text):
    for ln in (text or "").splitlines():
        out(format_log_line(ln))


# ---------- messages ----------

def info(text):
    out(text)


def hint(text):
    out(dim(text))


def warn(text):
    prefix = "warning: "
    if use_color("stderr"):
        err(_c_err("warning", "warning") + ": " + text)
    else:
        err(prefix + text)


def next_step(text):
    """Every command ends with one of these. Short, exact, copy-pasteable."""
    if use_color("stdout"):
        out(dim("Next: ") + text)
    else:
        out("Next: " + _plain(text))


def dry_run_cmd(argv):
    import shlex as _shlex
    try:
        shown = _shlex.join(argv)
    except Exception:
        shown = " ".join(argv)
    out(dim("+ ") + shown)


def error(title, why=None, fix=None):
    if use_color("stderr"):
        err(_c_err("Error", "error") + ": " + title)
    else:
        err("Error: " + _plain(title))
    if why:
        for ln in str(why).splitlines():
            err("  %s" % ln)
    if fix:
        if use_color("stderr"):
            err("  " + _c_err("Fix", "bold") + ": " + _plain(fix))
        else:
            err("  Fix: " + _plain(fix))


def debug_exc():
    if not _DEBUG_FLAG:
        return
    import traceback
    traceback.print_exc()
