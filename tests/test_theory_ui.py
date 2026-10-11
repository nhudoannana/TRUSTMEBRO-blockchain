"""
Tests for Bitcoin & Blockchain Theory UI page (ui/theory.html) and navigation integration.
Verifies structure, sticky TOC, embedded 3Blue1Brown video, lab bridges, theme support,
and presence in modes.html and labs.html mastheads.
"""

from fastapi.testclient import TestClient
from api.wallet_api import app

client = TestClient(app)


def test_theory_html_served_and_structured():
    """Verify ui/theory.html is served with 200 and has correct metadata."""
    resp = client.get("/ui/theory.html")
    assert resp.status_code == 200
    html = resp.text

    # Title & UTF-8
    assert "Lý thuyết Nền tảng: Bitcoin & Blockchain — TrustMeBro" in html
    assert 'charset="utf-8"' in html.lower()

    # Halftone nebula canvas & scripts
    assert 'id="nebula-bg"' in html
    assert 'id="nebula-canvas"' in html
    assert "/ui/halftone-nebula.js" in html
    assert "/ui/halftone-nebula.css" in html

    # Reading progress bar
    assert 'id="reading-progress"' in html

    # Theme toggle
    assert 'id="theme-toggle"' in html
    assert "trustmebro-theme" in html


def test_theory_chapters_and_toc():
    """Verify all 8 chapter sections and TOC navigation links exist."""
    resp = client.get("/ui/theory.html")
    assert resp.status_code == 200
    html = resp.text

    # TOC navigation links
    for i in range(1, 9):
        target = f"chuong-{i}"
        assert f'href="#{target}"' in html, f"Missing TOC anchor for {target}"
        assert f'id="{target}"' in html, f"Missing section id for {target}"
        assert f'data-target="{target}"' in html, f"Missing data-target for {target}"

    # Specific chapter titles
    assert "Bài toán Niềm tin & Sự ra đời của Sổ cái phân tán" in html
    assert "Quyền sở hữu & Chữ ký số (Digital Signatures)" in html
    assert "Tính toàn vẹn & Hàm băm mật mã SHA-256" in html
    assert "Đóng gói giao dịch & Cây Merkle (Merkle Tree)" in html
    assert "Trái tim của Bitcoin: Chuỗi khối & Proof of Work (PoW)" in html
    assert "Mạng P2P, Rẽ nhánh (Fork) & Quy tắc Chuỗi dài nhất" in html
    assert "An ninh & Giới hạn thực tế: Tấn công 51% & Giả mạo" in html
    assert "Bạn đã sẵn sàng — Bắt đầu thực hành" in html


def test_theory_embedded_youtube_video():
    """Verify 3Blue1Brown video is embedded with responsive iframe and timestamp 268s."""
    resp = client.get("/ui/theory.html")
    assert resp.status_code == 200
    html = resp.text

    # Embed iframe with correct video ID and start timestamp 268s (4:28)
    assert "https://www.youtube-nocookie.com/embed/bBC-nXj3Ng4?start=268" in html
    assert "3Blue1Brown" in html
    assert "https://www.youtube.com/watch?v=bBC-nXj3Ng4&t=268s" in html


def test_theory_lab_bridges_and_ctas():
    """Verify direct bridges to simulation labs and next-step actions."""
    resp = client.get("/ui/theory.html")
    assert resp.status_code == 200
    html = resp.text

    # Lab bridges
    assert "/ui/labs.html#signatures" in html
    assert "/ui/labs.html#sha" in html
    assert "/ui/labs.html#merkle" in html
    assert "/ui/labs.html#consensus" in html
    assert "/ui/labs.html#fork" in html
    assert "/ui/attacks.html" in html

    # Next steps CTAs
    assert "/ui/trustmebro.html" in html
    assert "/ui/modes.html#labs" in html
    assert "/ui/quiz.html" in html


def test_theory_css_served():
    """Verify ui/theory.css is served with correct styles."""
    resp = client.get("/ui/theory.css")
    assert resp.status_code == 200
    css = resp.text

    assert ".theory-layout" in css
    assert ".theory-sidebar" in css
    assert ".chapter-section" in css
    assert ".video-player-container" in css
    assert ".lab-bridge-card" in css
    assert "html[data-theme=\"light\"]" in css


def test_modes_page_includes_theory_mode():
    """Verify ui/modes.html features the new Theory mode card alongside the two simulation modes."""
    resp = client.get("/ui/modes.html")
    assert resp.status_code == 200
    html = resp.text

    # Mode card
    assert 'id="theory-mode"' in html
    assert 'href="/ui/theory.html"' in html
    assert "00 / NỀN TẢNG" in html
    assert "Lý thuyết" in html

    # Utilities header link
    assert '<a href="/ui/theory.html">Lý thuyết</a>' in html


def test_labs_page_utilities_includes_theory():
    """Verify ui/labs.html header includes the Theory link."""
    resp = client.get("/ui/labs.html")
    assert resp.status_code == 200
    html = resp.text

    assert '<a href="/ui/theory.html">Lý thuyết</a>' in html
