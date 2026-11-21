"""Turn filing HTML into plain text and cut out the sections worth reading."""
import html.parser
import re

# Sections read per form type: (label, start marker, markers that end it).
SECTIONS = {
    "10-K": [("Item 1 Business", r"item\s+1\.", [r"item\s+1a\.", r"item\s+1b\.", r"item\s+2\."]),
             ("Item 1A Risk Factors", r"item\s+1a\.", [r"item\s+1b\.", r"item\s+1c\.", r"item\s+2\."]),
             ("Item 7 MD&A", r"item\s+7\.", [r"item\s+7a\.", r"item\s+8\."])],
    "10-Q": [("Item 2 MD&A", r"item\s+2\.", [r"item\s+3\.", r"item\s+4\."])],
}


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
    """Longest span from a `start` marker to the next `ends` marker.

    Filings repeat item headings in the table of contents; the real section is the longest
    span. Returns None when no span is found, so the caller can report it.
    """
    best = None
    for m in re.finditer(start, text, re.I):
        stops = [e.start() for pat in ends for e in re.finditer(pat, text[m.end():], re.I)]
        if not stops:
            continue
        span = text[m.start(): m.end() + min(stops)]
        if best is None or len(span) > len(best):
            best = span
    return best


def chunks(text, size=60000):
    return [text[i:i + size] for i in range(0, len(text), size)]


def normalize(s):
    """Whitespace- and quote-insensitive form used to check a quote against its source."""
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()
