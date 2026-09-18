from io import BytesIO

import pytest
from PIL import Image

from fieldwise.documents.render import (
    PDF_MIME,
    UnsupportedDocumentError,
    downscale_jpeg,
    render_pages,
    sniff_mime,
)


def _image_bytes(fmt: str, size: tuple[int, int] = (300, 500)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=fmt)
    return buffer.getvalue()


def _pdf_bytes(pages: int = 2) -> bytes:
    buffer = BytesIO()
    images = [Image.new("RGB", (300, 500), "white") for _ in range(pages)]
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


def test_sniff_mime() -> None:
    assert sniff_mime(_pdf_bytes()) == PDF_MIME
    assert sniff_mime(_image_bytes("JPEG")) == "image/jpeg"
    assert sniff_mime(_image_bytes("PNG")) == "image/png"
    with pytest.raises(UnsupportedDocumentError):
        sniff_mime(b"hello")


def test_render_image_bounds_the_long_edge() -> None:
    pages = render_pages(_image_bytes("PNG", (3000, 6000)), "image/png", max_edge=1000)
    assert len(pages) == 1
    assert (pages[0].width, pages[0].height) == (500, 1000)
    assert pages[0].jpeg.startswith(b"\xff\xd8")


def test_render_pdf_renders_every_page() -> None:
    pages = render_pages(_pdf_bytes(pages=3), PDF_MIME, max_edge=800)
    assert [p.page for p in pages] == [1, 2, 3]
    assert all(max(p.width, p.height) == 800 for p in pages)


def test_downscale_jpeg() -> None:
    page = render_pages(_image_bytes("JPEG", (1600, 800)), "image/jpeg", max_edge=1600)[0]
    smaller = downscale_jpeg(page.jpeg, max_edge=400)
    with Image.open(BytesIO(smaller)) as image:
        assert image.size == (400, 200)


def test_unknown_mime_is_rejected() -> None:
    with pytest.raises(UnsupportedDocumentError):
        render_pages(b"...", "text/plain")
