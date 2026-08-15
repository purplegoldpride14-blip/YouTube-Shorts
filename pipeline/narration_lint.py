#!/usr/bin/env python3
"""
Find and fix anything in a script that makes a voice-over narrator stumble.

Two classes of issue:

  BLOCKING  - deterministic to fix, so the linter fixes them itself.
              Dashes, symbols (& % / @ + = $ # ~), abbreviations (e.g. Dr. vs.),
              smart quotes, ellipses, brackets, markdown, stray whitespace.

  ADVISORY  - needs a human or agent judgement call, so the linter only reports.
              Bare numerals, ALL-CAPS tokens, roman numerals, URLs, currency
              amounts. These read differently on different engines; the fix is
              to rewrite the sentence, not to substitute a token.

Usage:
    python3 narration_lint.py <script.txt>              # report only
    python3 narration_lint.py <script.txt> --fix        # rewrite in place
    python3 narration_lint.py <script.txt> --fix -o out.txt
    python3 narration_lint.py <script.txt> --strict     # advisory issues exit 1
"""
import sys
import re
import argparse

from config import DASH_CHARS

# ---------------------------------------------------------------- blocking

# Order matters: longer patterns first.
SYMBOL_FIXES = [
    (r"&", " and "),
    (r"%", " percent"),
    (r"\+", " plus "),
    (r"=", " equals "),
    (r"#(?=\d)", "number "),
    (r"#", " "),
    (r"@", " at "),
    (r"~(?=\d)", "about "),
    (r"~", " "),
    (r"\u00b0", " degrees"),
    (r"\u00d7", " by "),
    (r"\u00b1", " plus or minus "),
    (r"\u2026", ". "),          # ellipsis
    (r"\.\.\.", ". "),
    (r"\*|_{2,}|`", " "),       # markdown emphasis / code ticks
    (r"^\s*#{1,6}\s+", "", re.M),  # markdown headings
    (r"^\s*[-*\u2022]\s+", "", re.M),  # bullet markers
]

ABBREV_FIXES = [
    (r"\be\.g\.,?", "for example,"),
    (r"\bi\.e\.,?", "that is,"),
    (r"\betc\.", "and so on."),
    (r"\bvs\.?\b", "versus"),
    (r"\bapprox\.", "approximately"),
    (r"\bDr\.\s", "Doctor "),
    (r"\bMr\.\s", "Mister "),
    (r"\bMrs\.\s", "Missus "),
    (r"\bMs\.\s", "Miz "),
    (r"\bProf\.\s", "Professor "),
    (r"\bSt\.\s", "Saint "),
    (r"\bMt\.\s", "Mount "),
    (r"\bNo\.\s(?=\d)", "number "),
    (r"\bU\.S\.A?\.?", "the United States"),
    (r"\bU\.K\.", "the United Kingdom"),
    (r"\ba\.m\.", "in the morning"),
    (r"\bp\.m\.", "in the evening"),
    (r"\bB\.?C\.?E\.?\b", "BCE"),   # normalised, then flagged as ALL CAPS
    (r"\bA\.?D\.?\b", "AD"),
]

QUOTE_FIXES = [
    ("\u201c", '"'), ("\u201d", '"'),
    ("\u2018", "'"), ("\u2019", "'"),
    ("\u00a0", " "), ("\u200b", ""),
]

# ---------------------------------------------------------------- advisory

NUMERAL_RE = re.compile(r"\b\d[\d,.]*(?:st|nd|rd|th|s)?\b")
ALLCAPS_RE = re.compile(r"\b[A-Z]{2,}\b")
ROMAN_RE = re.compile(r"\b(?=[MDCLXVI]{2,}\b)M*(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})\b")
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+|\S+@\S+\.\S+")
CURRENCY_RE = re.compile(r"[$\u00a3\u20ac\u00a5]\s?\d")
PAREN_RE = re.compile(r"[()\[\]{}]")
SEMICOLON_RE = re.compile(r";")

ALLCAPS_OK = {"I", "A", "OK", "TV", "AI", "US", "UK", "CEO", "DNA", "NASA", "FBI", "CIA", "NBA", "NFL"}


def _line_of(text, idx):
    return text.count("\n", 0, idx) + 1


CHAR_NAMES = {
    "\u2014": "em dash", "\u2013": "en dash", "\u2012": "figure dash",
    "\u2015": "horizontal bar", "\u2212": "minus sign", "\u2026": "ellipsis",
    "\u00b0": "degree sign", "\u00d7": "multiplication sign",
    "\u00b1": "plus-minus sign", "\u00a0": "non-breaking space",
    "\u201c": "curly quote", "\u201d": "curly quote",
    "\u2018": "curly apostrophe", "\u2019": "curly apostrophe",
    "\u200b": "zero-width space",
}


def _human(pat):
    for ch, name in CHAR_NAMES.items():
        if ch in pat or ch.encode("unicode_escape").decode() in pat:
            return name
    """Turn a regex back into something worth printing."""
    out = re.sub(r"\(\?[:=!<][^)]*\)", "", pat)
    out = out.replace("\\b", "").replace("\\.", ".").replace("\\s", " ")
    out = out.replace("\\", "").replace("^", "").replace("$", "")
    out = re.sub(r"\{\d+,?\d*\}|\[[^\]]*\]|[+*?]", "", out)
    out = out.replace("|", " or ").strip()
    try:
        out = out.encode("ascii", "backslashreplace").decode()
    except Exception:
        pass
    return out or pat


def _mask_urls(text):
    """URLs must survive the symbol rules intact so they can be reported as-is."""
    found = []

    def keep(m):
        found.append(m.group(0))
        return f"\x00URL{len(found) - 1}\x00"

    return URL_RE.sub(keep, text), found


def _unmask_urls(text, found):
    for i, u in enumerate(found):
        text = text.replace(f"\x00URL{i}\x00", u)
    return text


def autofix(text):
    """Apply every deterministic fix. Returns (new_text, [descriptions])."""
    fixes = []
    out, urls = _mask_urls(text)

    for a, b in QUOTE_FIXES:
        if a in out:
            fixes.append(f"normalised {out.count(a)}x {CHAR_NAMES.get(a, a)} -> {b!r}")
            out = out.replace(a, b)

    for d in DASH_CHARS:
        if d in out:
            n = out.count(d)
            fixes.append(f"replaced {n}x {CHAR_NAMES.get(d, 'dash')} with a comma pause")
            # "word - word" reads as a pause; a bare dash between digits is a range
            out = re.sub(r"\s*" + re.escape(d) + r"\s*", ", ", out)

    # hyphen used as a dash or a range, not as a compound word
    if re.search(r"\s-\s", out):
        n = len(re.findall(r"\s-\s", out))
        fixes.append(f"replaced {n}x spaced hyphen with a comma pause")
        out = re.sub(r"\s-\s", ", ", out)
    if re.search(r"(\d)\s*-\s*(\d)", out):
        n = len(re.findall(r"(\d)\s*-\s*(\d)", out))
        fixes.append(f"expanded {n}x numeric range 'a-b' to 'a to b'")
        out = re.sub(r"(\d)\s*-\s*(\d)", r"\1 to \2", out)

    # slash between words reads as "slash"
    if re.search(r"(?<=[A-Za-z])\s*/\s*(?=[A-Za-z])", out):
        n = len(re.findall(r"(?<=[A-Za-z])\s*/\s*(?=[A-Za-z])", out))
        fixes.append(f"expanded {n}x 'a/b' to 'a or b'")
        out = re.sub(r"(?<=[A-Za-z])\s*/\s*(?=[A-Za-z])", " or ", out)

    for pat, rep in ABBREV_FIXES:
        new, n = re.subn(pat, rep, out)
        if n:
            fixes.append(f"expanded {n}x {_human(pat)!r} -> {rep.strip()!r}")
            out = new

    for rule in SYMBOL_FIXES:
        pat, rep = rule[0], rule[1]
        flags = rule[2] if len(rule) > 2 else 0
        new, n = re.subn(pat, rep, out, flags=flags)
        if n:
            fixes.append(f"expanded {n}x {_human(pat)!r} -> {rep.strip()!r}")
            out = new

    # brackets: keep the words, drop the punctuation
    if PAREN_RE.search(out):
        n = len(PAREN_RE.findall(out))
        fixes.append(f"removed {n}x bracket character(s)")
        out = PAREN_RE.sub(" ", out)

    # semicolons read as a hard stop by most engines; a full stop is cleaner
    if SEMICOLON_RE.search(out):
        n = len(SEMICOLON_RE.findall(out))
        fixes.append(f"replaced {n}x semicolon with a full stop")
        out = SEMICOLON_RE.sub(".", out)

    # whitespace and punctuation tidy-up
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r" ?, ?,", ",", out)
    out = re.sub(r" +([,.!?])", r"\1", out)
    out = re.sub(r"([,.!?]){2,}", r"\1", out)
    out = re.sub(r"\bthe the\b", "the", out)
    # an expansion can leave a sentence starting lower case
    out = re.sub(r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = "\n\n".join(p.strip() for p in out.split("\n\n") if p.strip()) + "\n"
    out = _unmask_urls(out, urls)

    return out, fixes


def advisories(text):
    """Issues that need a rewrite rather than a substitution."""
    found = []

    def add(kind, m, note):
        found.append((_line_of(text, m.start()), kind, m.group(0).strip(), note))

    for m in URL_RE.finditer(text):
        add("url", m, "a narrator cannot read a URL; say the name instead")
    for m in CURRENCY_RE.finditer(text):
        add("currency", m, "write it the way it is spoken, e.g. 'five million dollars'")
    for m in NUMERAL_RE.finditer(text):
        add("numeral", m, "spell it out so every engine reads it the same way")
    for m in ROMAN_RE.finditer(text):
        add("roman", m, "roman numerals are read letter by letter")
    for m in ALLCAPS_RE.finditer(text):
        if m.group(0) not in ALLCAPS_OK:
            add("allcaps", m, "spell it out, or space the letters, e.g. 'N A S A'")

    return found


def report(text, strict=False):
    issues = advisories(text)
    if not issues:
        print("  no advisory issues")
        return 0

    by_kind = {}
    for line, kind, snip, note in issues:
        by_kind.setdefault(kind, []).append((line, snip, note))

    for kind, items in sorted(by_kind.items()):
        note = items[0][2]
        print(f"  {'FAIL' if strict else 'WARN'}: {len(items)}x {kind} - {note}")
        for line, snip, _ in items[:8]:
            print(f"        line {line}: {snip}")
        if len(items) > 8:
            print(f"        ... and {len(items) - 8} more")

    return 1 if strict else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("script")
    ap.add_argument("--fix", action="store_true", help="apply the blocking fixes")
    ap.add_argument("-o", "--out", help="write the fixed text here instead of in place")
    ap.add_argument("--strict", action="store_true", help="advisory issues exit non-zero")
    a = ap.parse_args()

    text = open(a.script, encoding="utf-8").read()
    fixed, fixes = autofix(text)

    print("Blocking issues:")
    if fixes:
        for f in fixes:
            print(f"  {'fixed' if a.fix else 'FAIL'}: {f}")
    else:
        print("  none")

    print("Advisory issues:")
    rc_adv = report(fixed, strict=a.strict)

    if a.fix:
        dest = a.out or a.script
        open(dest, "w", encoding="utf-8").write(fixed)
        print(f"\nwrote {dest}")
        return rc_adv

    if fixes:
        print("\nRun again with --fix to apply the blocking fixes.")
        return 1
    return rc_adv


if __name__ == "__main__":
    sys.exit(main())
