"""Turn filing HTML into plain text and cut out the sections worth reading."""
import html.parser
import re

# What follows the item number in a heading: "Item 1.", "Item 1:", "Item 1\u2014Business", "Item 1 - Business".
S = r"\s*[.:\u2014\u2013-]"
# Sections read per form type: (label, start marker, markers that end it).
SECTIONS = {
    "10-K": [("Item 1 Business", rf"item\s+1{S}", [rf"item\s+1a{S}", rf"item\s+1b{S}", rf"item\s+2{S}"]),
             ("Item 1A Risk Factors", rf"item\s+1a{S}", [rf"item\s+1b{S}", rf"item\s+1c{S}", rf"item\s+2{S}"]),
             ("Item 7 MD&A", rf"item\s+7{S}", [rf"item\s+7a{S}", rf"item\s+8{S}"])],
    "10-Q": [("Item 2 MD&A", rf"item\s+2{S}", [rf"item\s+3{S}", rf"item\s+4{S}"])],
}
# A shorter span is not the section text: it is an entry in a cross-reference index
# ("Item 1A. Risk Factors / Pages 31-46", filings whose body has no item headings) or a
# sentence incorporating the section by reference. It is reported as not read.
MIN_SECTION = 2000


class _Text(html.parser.HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("td", "th"):
            self.parts.append(" ")  # adjacent cells otherwise run together: "stores1,761 1,753"

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(raw):
    p = _Text()
    p.feed(raw)
    text = "".join(p.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def section(text, start, ends):
    """Longest span from a `start` heading to the next `ends` heading.

    Only headings at the start of a line count: filings quote item names mid-sentence
    ('refer to Part II, "Item 8. Financial Statements"'). Headings repeat in the table of
    contents; the real section is the longest span. A span that runs over another `start`
    heading is not one section (a 10-Q contents lists "Item 2." twice, Part I and Part II,
    and the second would run to the real Item 3). The exception is a running page header:
    some filings repeat the same heading text at the top of every page of the section, so
    a repeat of the identical heading with no `ends` heading in between continues the
    section. Returns None when no span is found, so the caller can report it.
    """
    def heads(pat):
        return [m.start() for m in re.finditer(r"^[ \t]*" + pat, text, re.I | re.M)]

    def head(i):
        return " ".join(text[i:i + 40].split())

    starts = heads(start)
    stops = sorted(e for pat in ends for e in heads(pat))
    best = None
    for i, s in enumerate(starts):
        stop = next((e for e in stops if e > s), None)
        if stop is None:
            continue
        later = [n for n in starts[i + 1:] if n < stop]
        if any(head(n) != head(s) for n in later):
            continue
        if best is None or stop - s > len(best):
            best = text[s:stop]
    return best


def chunks(text, size=60000):
    return [text[i:i + size] for i in range(0, len(text), size)]


def normalize(s):
    """Whitespace- and quote-insensitive form used to check a quote against its source."""
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()
