"""Educational scope checks; behavior is exercised by API and Node VM suites."""
from html.parser import HTMLParser
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids = {}
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            assert attrs["id"] not in self.ids, attrs["id"]
            self.ids[attrs["id"]] = (tag, attrs)


def test_both_labs_expose_six_sections_and_optional_local_predictions():
    for filename, prefix in [("attacks.html", "attack"), ("labs.html", "tamper")]:
        text = (ROOT / "ui" / filename).read_text(encoding="utf-8")
        page = Page(text)
        for suffix in ["objectives", "knowledge", "prediction", "practice", "causes", "limits"]:
            assert prefix + "-" + suffix in page.ids
        tag, attrs = page.ids[prefix + "-prediction-input"]
        assert tag == "textarea"
        assert "required" not in attrs
        assert 'for="' + prefix + '-prediction-input"' in text


def test_security_theory_is_bounded_and_sourced():
    text = (ROOT / "ui/theory.html").read_text(encoding="utf-8")
    chapter = text.split('<section id="chuong-7"', 1)[1].split("</section>", 1)[0]
    assert "bảo vệ tài sản của bạn tuyệt đối" not in text
    assert "xác minh 100%" not in text
    assert "không thể làm giả" not in text
    for topic in ["51%", "Sybil", "Eclipse", "Timejacking"]:
        assert topic in chapter
    assert chapter.count("chưa mô phỏng") >= 3
    for source in ["https://bitcoin.org/bitcoin.pdf",
                   "https://www.microsoft.com/en-us/research/publication/the-sybil-attack/",
                   "https://www.usenix.org/conference/usenixsecurity15/technical-sessions/presentation/heilman",
                   "https://bitcoincore.org/en/releases/27.0/"]:
        assert source in chapter
    # Related signature/hash sentences are in scope; unrelated chapters stay exact.
    import subprocess
    before = subprocess.check_output(
        ["git", "show", "bcf019dbee16f2282ae7a55979b5cf4cd643818d:ui/theory.html"],
        cwd=ROOT, encoding="utf-8")
    for n in [1, 4, 5, 6, 8]:
        pattern = rf'<section id="chuong-{n}".*?</section>'
        assert re.search(pattern, text, re.S).group() == re.search(pattern, before, re.S).group()


def test_learning_headings_preserve_vietnamese_accents():
    text = (ROOT / "ui" / "attacks.html").read_text(encoding="utf-8")
    assert "4. Thực hành — chọn thí nghiệm" in text
    assert "5. Kết quả &amp; nguyên nhân" in text
