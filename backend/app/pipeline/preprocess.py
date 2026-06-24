"""Stage 1 - upload pre-processing.

* Split PDFs into per-page images (pdf2image / poppler).
* Load standalone image uploads.
* Deskew + denoise every page with OpenCV so OMR gets a clean input.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def is_pdf(filename: str) -> bool:
    return filename.lower().endswith(".pdf")


def is_image(filename: str) -> bool:
    return filename.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"))


def pdf_to_page_images(pdf_path: Path, out_dir: Path, dpi: int = 300) -> list[Path]:
    """Rasterise each PDF page to a PNG. Requires poppler to be installed."""
    from pdf2image import convert_from_path

    out_dir.mkdir(parents=True, exist_ok=True)
    images = convert_from_path(str(pdf_path), dpi=dpi)
    paths: list[Path] = []
    for idx, image in enumerate(images):
        dest = out_dir / f"page_{idx + 1:03d}.png"
        image.save(dest, "PNG")
        paths.append(dest)
    return paths


# OMR engines (Audiveris) need a staff interline of ~16px+ to detect systems.
# Low-resolution uploads are upscaled so the longer side reaches this target.
_OMR_TARGET_LONG_SIDE = 2200
_OMR_MAX_SCALE = 3.0
# Skews beyond this are treated as detection noise, not a genuine page tilt.
_MAX_DESKEW_DEG = 15.0


def _deskew(gray: np.ndarray) -> np.ndarray:
    """Estimate page skew from the dominant text/staff angle and rotate flat."""
    inverted = cv2.bitwise_not(gray)
    thresh = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.shape[0] < 50:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    # minAreaRect's angle convention is ambiguous (OpenCV reports it in (0, 90]
    # or [-90, 0) depending on version). Normalize into [-45, 45] so an already
    # straight page (e.g. a digital engraving reported as 90.0) is not spun 90°.
    if angle > 45:
        angle -= 90
    if angle < -45:
        angle += 90
    # Ignore sub-pixel noise and implausibly large angles (mis-detection).
    if abs(angle) < 0.1 or abs(angle) > _MAX_DESKEW_DEG:
        return gray
    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        gray, matrix, (w, h),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )


def _upscale_for_omr(gray: np.ndarray) -> np.ndarray:
    """Enlarge small scans so OMR can resolve staff lines; never downscale."""
    longer = max(gray.shape)
    if longer >= _OMR_TARGET_LONG_SIDE:
        return gray
    factor = min(_OMR_MAX_SCALE, _OMR_TARGET_LONG_SIDE / longer)
    return cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)


def preprocess_page(src: Path, dest: Path) -> Path:
    """Deskew + denoise a single page image and write the cleaned version."""
    image = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
    if image is None:
        # Not a readable raster image; copy bytes through untouched.
        dest.write_bytes(src.read_bytes())
        return dest

    deskewed = _deskew(image)
    # Light denoise only. Audiveris performs its own binarization and needs the
    # grayscale staff lines intact, so we deliberately do NOT adaptive-threshold
    # here (aggressive binarization fragments thin staves and breaks detection).
    denoised = cv2.fastNlMeansDenoising(deskewed, h=7)
    cleaned = _upscale_for_omr(denoised)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), cleaned)
    return dest


def preprocess_upload(src_path: Path, filename: str, work_dir: Path) -> list[Path]:
    """Turn an uploaded file into a list of cleaned, OMR-ready page images."""
    work_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = work_dir / "raw"
    clean_dir = work_dir / "clean"
    raw_dir.mkdir(parents=True, exist_ok=True)
    clean_dir.mkdir(parents=True, exist_ok=True)

    if is_pdf(filename):
        raw_pages = pdf_to_page_images(src_path, raw_dir)
    elif is_image(filename):
        raw_pages = [src_path]
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    cleaned: list[Path] = []
    for idx, page in enumerate(raw_pages):
        dest = clean_dir / f"page_{idx + 1:03d}.png"
        cleaned.append(preprocess_page(page, dest))
    return cleaned
