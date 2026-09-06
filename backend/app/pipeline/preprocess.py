"""Stage 1 - upload pre-processing.

* Split PDFs into per-page images (pdf2image / poppler).
* Load standalone image uploads.
* Deskew + denoise every page with OpenCV so OMR gets a clean input.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np


def is_pdf(filename: str) -> bool:
    return filename.lower().endswith(".pdf")


def is_image(filename: str) -> bool:
    return filename.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"))


def pdf_to_page_images(
    pdf_path: Path, out_dir: Path, dpi: int = 300, threads: int = 4
) -> list[Path]:
    """Rasterise each PDF page to a PNG. Requires poppler to be installed."""
    from pdf2image import convert_from_path

    out_dir.mkdir(parents=True, exist_ok=True)
    # output_file/paths_only makes poppler write the PNGs itself, so the pages
    # never all sit in memory as PIL images at once - a 300 DPI A4 page is ~25MB
    # decoded, which adds up fast on a long score.
    paths = convert_from_path(
        str(pdf_path),
        dpi=dpi,
        thread_count=max(1, threads),
        fmt="png",
        output_folder=str(out_dir),
        output_file="page",
        paths_only=True,
    )
    renamed: list[Path] = []
    for idx, raw in enumerate(paths):  # pdf2image returns these in page order
        dest = out_dir / f"page_{idx + 1:03d}.png"
        Path(raw).replace(dest)
        renamed.append(dest)
    return renamed


# OpenCV's default thread count, read once before anything has narrowed it.
_CV_BASELINE_THREADS = cv2.getNumThreads()

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


def estimate_noise(gray: np.ndarray) -> float:
    """Cheap noise estimate: median absolute deviation of the Laplacian.

    Costs ~0.2s against the ~2.5s the denoiser takes on a 300 DPI page, so it
    pays for itself immediately on the digital PDFs that need no denoising at
    all (they measure ~0, while scans land far above the threshold).
    """
    lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    return float(np.median(np.abs(lap - np.median(lap))))


def _denoise(gray: np.ndarray, threshold: float) -> np.ndarray:
    """Denoise only when the page is actually noisy.

    Non-local means dominates preprocessing, and a vector PDF rasterised by
    poppler has no sensor noise to remove - running it there costs seconds per
    page and softens the staff lines for nothing.
    """
    if estimate_noise(gray) <= threshold:
        return gray
    # Full-strength non-local means. A narrower searchWindowSize would run ~2.4x
    # faster but measured 1.9 dB worse (32.5 vs 34.4 dB PSNR against a clean
    # reference) - and this branch only runs on genuinely noisy scans, which are
    # precisely the pages where OMR needs the cleanest input it can get. The
    # speed comes from skipping this entirely on clean pages, not from
    # weakening it here.
    return cv2.fastNlMeansDenoising(gray, h=7)


def preprocess_page(src: Path, dest: Path, noise_threshold: float = 1.5) -> Path:
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
    denoised = _denoise(deskewed, noise_threshold)
    cleaned = _upscale_for_omr(denoised)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), cleaned)
    return dest


def preprocess_upload(
    src_path: Path,
    filename: str,
    work_dir: Path,
    workers: int = 4,
    dpi: int = 300,
    noise_threshold: float = 1.5,
) -> list[Path]:
    """Turn an uploaded file into a list of cleaned, OMR-ready page images."""
    work_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = work_dir / "raw"
    clean_dir = work_dir / "clean"
    raw_dir.mkdir(parents=True, exist_ok=True)
    clean_dir.mkdir(parents=True, exist_ok=True)

    if is_pdf(filename):
        raw_pages = pdf_to_page_images(src_path, raw_dir, dpi=dpi, threads=workers)
    elif is_image(filename):
        raw_pages = [src_path]
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    jobs = [
        (page, clean_dir / f"page_{idx + 1:03d}.png")
        for idx, page in enumerate(raw_pages)
    ]
    if len(jobs) == 1:
        return [preprocess_page(*jobs[0], noise_threshold)]

    # Pages are independent, and the heavy steps (denoise, warpAffine, resize)
    # are OpenCV C++ calls that release the GIL, so threads genuinely overlap.
    # cv2's own thread pool is capped so the two levels of parallelism don't
    # oversubscribe the box and thrash.
    pool_size = max(1, min(workers, len(jobs)))
    # Restored from the baseline captured at import, not from the live value:
    # cv2's thread count is process-global, so two concurrent Celery tasks
    # reading each other's reduced value would ratchet it down permanently.
    cv2.setNumThreads(max(1, _CV_BASELINE_THREADS // pool_size))
    try:
        with ThreadPoolExecutor(max_workers=pool_size) as pool:
            return list(
                pool.map(lambda j: preprocess_page(j[0], j[1], noise_threshold), jobs)
            )
    finally:
        cv2.setNumThreads(_CV_BASELINE_THREADS)
