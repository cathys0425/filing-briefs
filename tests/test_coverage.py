"""Offline tests. The model and SEC are replaced by stubs; run with: python3 -m unittest -v"""
import json
import os
import tempfile
import unittest
from unittest import mock

from coverage import extract, onepager, run, text

BUSINESS = "We sell widgets to retailers under annual contracts priced per unit shipped. " * 40
RISK = "A single customer accounted for 42% of net sales in fiscal 2025. " * 40
MDNA = "Net sales rose 12% on higher unit volume; we expect to open a second plant in March 2027. " * 40
TEN_K = ("<html><body><p>Item 1. Business</p><p>Item 1A. Risk Factors</p><p>Item 7. MD&amp;A</p>"  # table of contents
         f"<p>Item 1. Business</p><p>{BUSINESS}</p><p>Item 1A. Risk Factors</p><p>{RISK}</p>"
         "<p>Item 1B. Unresolved</p><p>Item 2. Properties</p>"
         f"<p>Item 7. Management Discussion</p><p>{MDNA}</p><p>Item 7A. Market risk</p><p>Item 8. Statements</p>"
         "</body></html>")


class TextTests(unittest.TestCase):
    def test_section_skips_table_of_contents(self):
        body = text.html_to_text(TEN_K)
        label, start, ends = text.SECTIONS["10-K"][0]
        self.assertIn("annual contracts", text.section(body, start, ends))
        self.assertNotIn("42%", text.section(body, start, ends))

    def test_section_ignores_cross_references_and_second_contents_entry(self):
        # Pattern seen in real 10-Q filings: the contents lists "Item 2." for Part I and
        # Part II, and the body quotes item names mid-sentence.
        body = ("Item 1.\nFinancial Statements\n2\nItem 2.\nMD&A\n27\nItem 3.\nMarket Risk\n39\n"
                "Item 1.\nLegal Proceedings\n40\nItem 2.\nUnregistered Sales\n42\n"
                "Item 1. Financial Statements\n" + "balance sheet " * 50 + "\n"
                "Item 2. Management's Discussion\nRevenue grew on pricing; refer to Part II, "
                "\u201cItem 3. Legal Proceedings\u201d for the tax case. Volume was flat.\n"
                "Item 3. Quantitative Disclosures\nSee the annual report.\n")
        got = text.section(body, r"item\s+2\.", [r"item\s+3\.", r"item\s+4\."])
        self.assertTrue(got.startswith("Item 2. Management's Discussion"))
        self.assertTrue(got.rstrip().endswith("Volume was flat."))

    def test_section_spans_running_page_headers(self):
        # Pattern seen in real 10-Q filings: the section heading is repeated as a page
        # header on every page of the section, after a contents page.
        h = "ITEM 2. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION\n"
        body = ("Item 2.\nManagement's Discussion\n26\nItem 3.\nMarket Risk\n37\n"
                "Item 2.\nPurchases of Equity Securities\n39\nItem 6.\nExhibits\n40\n"
                "ITEM 1. FINANCIAL STATEMENTS\n" + "balance sheet " * 50 + "\n"
                + h + "Revenue grew on pricing.\n" + h + "Volume was flat.\n" + h + "Fuel fell.\n"
                "ITEM 3. QUANTITATIVE DISCLOSURES\nNo change.\n"
                "Item 2. Purchases of Equity Securities\nWe bought shares.\nItem 3. Defaults\nNone\n")
        got = text.section(body, r"item\s+2\.", [r"item\s+3\.", r"item\s+4\."])
        for phrase in ("Revenue grew on pricing.", "Volume was flat.", "Fuel fell."):
            self.assertIn(phrase, got)
        self.assertNotIn("balance sheet", got)
        self.assertNotIn("We bought shares", got)

    def test_section_heading_with_colon(self):
        # Pattern seen in real 10-K filings: "Item 1:" instead of "Item 1.".
        body = ("Item 1:\nBusiness\n4\nItem 1A:\nRisk Factors\n13\nItem 1B:\nUnresolved\n27\n"
                "Item 1: Business\nWe make tools.\nItem 1A: Risk Factors\nDemand is cyclical.\n"
                "Item 1B: Unresolved Staff Comments\nNone.\n")
        label, start, ends = text.SECTIONS["10-K"][0]
        self.assertEqual(text.section(body, start, ends), "Item 1: Business\nWe make tools.\n")
        label, start, ends = text.SECTIONS["10-K"][1]
        self.assertEqual(text.section(body, start, ends), "Item 1A: Risk Factors\nDemand is cyclical.\n")

    def test_missing_section_is_none(self):
        self.assertIsNone(text.section("no headings here", r"item\s+7\.", [r"item\s+8\."]))


class VerifyTests(unittest.TestCase):
    def test_fabricated_quote_is_dropped(self):
        real = {"category": "risk", "claim": "c", "quote": "A single customer accounted for 42% of net sales"}
        fake = {"category": "risk", "claim": "c", "quote": "A single customer accounted for 24% of net sales"}
        ok, bad = extract.verify([real, fake], RISK)
        self.assertEqual((ok, bad), ([real], [fake]))

    def test_number_missing_from_quote_is_dropped(self):
        quote = "A single customer accounted for 42% of net sales in fiscal 2025."
        good = {"category": "risk", "claim": "One customer was 42% of FY2025 sales", "quote": quote}
        bad = {"category": "risk", "claim": "One customer was 42% of sales, up from 30%", "quote": quote}
        self.assertEqual(extract.verify([good, bad], RISK), ([good], [bad]))

    def test_whitespace_differences_still_match(self):
        n = {"category": "risk", "claim": "c", "quote": "A single  customer\naccounted for 42% of net sales"}
        self.assertEqual(extract.verify([n], RISK)[0], [n])

    def test_malformed_reply_raises(self):
        with self.assertRaises(ValueError):
            extract.parse_notes("I could not find anything.")
        with self.assertRaises(ValueError):
            extract.parse_notes('[{"category": "vibes", "claim": "c", "quote": "q"}]')


class CitationTests(unittest.TestCase):
    def test_uncited_and_unknown_ids_are_flagged(self):
        body = "## Business model\n- Sells widgets [N1]\n- Great management\n- Growing fast [N99]"
        self.assertEqual(onepager.check_citations(body, {"N1"}), ["- Great management", "- Growing fast [N99]"])


class IndustryTests(unittest.TestCase):
    def test_bullets_must_cite_every_company_they_name(self):
        pages = {"AAA": "- Sells widgets [N1]\n## Revenue as first reported\n[N9]", "BBB": "- Sells gears [N2]\n"}
        reply = ("- Both sell parts [AAA N1][BBB N2]\n- AAA and BBB grow fast [AAA N1]\n"
                 "- AAA cites the appendix [AAA N9]\n- No citation")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(onepager, "CACHE", d):
            view, _ = run.industry_view("parts", pages, "m", complete=lambda m, model: (reply, {"cost": 0.01}, 0.1))
        flagged = [line for line in view.splitlines() if line.startswith("- Bullet without")]
        self.assertEqual(len(flagged), 3)
        self.assertNotIn("Both sell parts", " ".join(flagged))


class PipelineTests(unittest.TestCase):
    def test_end_to_end_with_stubs(self):
        def fake_complete(messages, model):
            prompt = messages[0]["content"]
            if "Return JSON only" in prompt:
                notes = [{"category": "risk", "claim": "made up",
                          "quote": "this passage is not in the document at all"}]
                if "Item 1 Business" in prompt:
                    notes.append({"category": "business_model", "claim": "Sells widgets per unit",
                                  "quote": "We sell widgets to retailers under annual contracts"})
                return json.dumps(notes), {"cost": 0.01}, 0.1
            if "Write at most 8 bullets" in prompt:
                return "- Sold widgets per unit [N1]\n- No citation here\n- Unknown id [N99]", {"cost": 0.01}, 0.1
            assert "2026\n- Sold widgets per unit [N1]" in prompt  # the writer sees the year digest
            return "## Business model\n- Sells widgets per unit [N1]\n- Unsupported bullet", {"cost": 0.02}, 0.1

        filing = {"form": "10-K", "accession": "a", "filed": "2026-02-01", "period": "2025-12-31",
                  "items": "", "url": "u"}
        revenue = [{"period_end": "2025-12-31", "value": 5e9, "filed": "2026-02-01", "tag": "Revenues",
                    "later_differing_values": 0}]
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(extract, "CACHE", d), \
                mock.patch.object(onepager, "CACHE", d), \
                mock.patch.object(run.transcripts, "fetch", return_value=(0, 0)), \
                mock.patch.object(run.edgar, "cik_for", return_value="0000000001"), \
                mock.patch.object(run.edgar, "company", return_value={
                    "cik": "1", "name": "Widget Co", "tickers": ["WDGT"], "sic": "1", "sic_description": "Widgets"}), \
                mock.patch.object(run.edgar, "filings", return_value=[filing]), \
                mock.patch.object(run.edgar, "get", return_value=TEN_K.encode()), \
                mock.patch.object(run.edgar, "annual_revenue", return_value=revenue):
            cwd = os.getcwd()
            os.chdir(d)
            try:
                page = run.cover("WDGT", "2020-01-01", "m1", "m2", complete=fake_complete)
            finally:
                os.chdir(cwd)
        self.assertIn("| 2025-12-31 | 5,000 | 2026-02-01 | 0 |", page)
        self.assertIn("1 notes whose quote was found verbatim", page)
        self.assertIn("Not read: earnings calls: ticker not in the transcript dataset", page)
        self.assertIn("3 notes dropped", page)
        self.assertIn("through 1 year digests", page)
        self.assertIn("2 digest bullets were dropped", page)  # one fabricated note per section
        self.assertIn("Bullet without a valid citation: - Unsupported bullet", page)
        self.assertIn('N1 (10-K 2025-12-31 Item 1 Business): "We sell widgets', page)


    def test_cross_reference_index_is_not_read(self):
        # Pattern seen in real filings: no item headings in the body, only an index at the
        # end mapping each item to page numbers. Those entries are not the section text.
        index = ("<html><body><p>Our business</p><p>" + BUSINESS + "</p>"
                 "<p>Item 1.Business</p><p>Pages 3-20</p><p>Item 1A.Risk Factors</p><p>Pages 31-46</p>"
                 "<p>Item 1B.Unresolved Staff Comments</p><p>None</p><p>Item 2.Properties</p><p>Page 8</p>"
                 "<p>Item 7.MD&amp;A</p><p>Pages 21-30</p><p>Item 7A.Market risk</p><p>Page 47</p>"
                 "<p>Item 8.Statements</p></body></html>")
        filing = {"form": "10-K", "accession": "a", "filed": "2026-02-01", "period": "2025-12-31",
                  "items": "", "url": "u"}
        seen = []

        def fake_complete(messages, model):
            seen.append(messages[0]["content"])
            raise AssertionError("no section should reach the model")

        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(extract, "CACHE", d), \
                mock.patch.object(run.transcripts, "fetch", return_value=(0, 0)), \
                mock.patch.object(run.edgar, "cik_for", return_value="0000000001"), \
                mock.patch.object(run.edgar, "company", return_value={
                    "cik": "1", "name": "Widget Co", "tickers": ["WDGT"], "sic": "1", "sic_description": "Widgets"}), \
                mock.patch.object(run.edgar, "filings", return_value=[filing]), \
                mock.patch.object(run.edgar, "get", return_value=index.encode()), \
                mock.patch.object(run.glob, "glob", return_value=[]):
            with self.assertRaises(RuntimeError) as e:
                run.cover("WDGT", "2020-01-01", "m1", "m2", complete=fake_complete)
        self.assertEqual(seen, [])
        self.assertEqual(str(e.exception).count("not the section text"), 3)


if __name__ == "__main__":
    unittest.main()
