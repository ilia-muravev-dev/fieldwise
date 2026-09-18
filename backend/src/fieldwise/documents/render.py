"""Page rendering: PDFs and images become JPEG page images of bounded size."""

from dataclasses import dataclass
from io import BytesIO

import pypdfium2 as pdfium
from PIL import Image, ImageOps

MAX_EDGE_PX = 2000  # stored pages: enough for OCR and for the review UI
JPEG_QUALITY = 90

PDF_MIME = "application/pdf"
IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/tiff"}


@dataclass(frozen=True)
class PageImage:
    page: int
    jpeg: bytes
    width: int
    height: int


class UnsupportedDocumentError(ValueError):
    pass


def sniff_mime(data: bytes) -> str:
    if data.startswith(b"%PDF"):
        return PDF_MIME
    try:
        with Image.open(BytesIO(data)) as image:
            fmt = (image.format or "").lower()
    except OSError as error:
        raise UnsupportedDocumentError("not a PDF or a readable image") from error
    return {
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "tiff": "image/tiff",
    }.get(fmt, f"image/{fmt}")


def render_pages(data: bytes, mime: str, max_edge: int = MAX_EDGE_PX) -> list[PageImage]:
    if mime == PDF_MIME:
        return _render_pdf(data, max_edge)
    if mime in IMAGE_MIMES:
        with Image.open(BytesIO(data)) as image:
            return [_page_from_image(image, page=1, max_edge=max_edge)]
    raise UnsupportedDocumentError(f"unsupported document type {mime!r}")


def _render_pdf(data: bytes, max_edge: int) -> list[PageImage]:
    pdf = pdfium.PdfDocument(data)
    pages: list[PageImage] = []
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            width_pt, height_pt = page.get_size()
            scale = max_edge / max(width_pt, height_pt)
            bitmap = page.render(scale=scale)
            with bitmap.to_pil() as image:
                pages.append(_page_from_image(image, page=index + 1, max_edge=max_edge))
    finally:
        pdf.close()
    return pages


def _page_from_image(image: Image.Image, page: int, max_edge: int) -> PageImage:
    rgb = ImageOps.exif_transpose(image) or image
    rgb = rgb.convert("RGB")
    rgb.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    rgb.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return PageImage(page=page, jpeg=buffer.getvalue(), width=rgb.width, height=rgb.height)


def downscale_jpeg(jpeg: bytes, max_edge: int, quality: int = 85) -> bytes:
    """A smaller copy for the model: fewer image tokens, same content."""
    with Image.open(BytesIO(jpeg)) as image:
        rgb = image.convert("RGB")
        rgb.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        rgb.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()
