"""Image clean-up before OCR (OpenCV).

Steps for scanned / photographed land records:
1. upscale small images (Tesseract works best at roughly 300 dpi)
2. remove uneven background: yellowed paper, stains, shadows (divide by a blurred background)
3. estimate and correct page skew (projection-profile search, +-10 degrees)
4. candidates: as is / with table grid lines removed / adaptive threshold (faded ink) without lines

Chosen by measurement on degraded test scans (see README "OCR accuracy"): denoising and
CLAHE contrast boosting were tried and made results worse, so they are not used.

ocr.py runs Tesseract on the plain image first and only uses these variants when the
page looks skewed or the first result is not confident, keeping clean pages fast.
"""

import cv2
import numpy as np
from PIL import Image

TARGET_MIN_WIDTH = 2000
MAX_SKEW_DEGREES = 10.0


def to_gray_array(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L"))


def upscale(gray: np.ndarray) -> np.ndarray:
    h, w = gray.shape
    if w >= TARGET_MIN_WIDTH:
        return gray
    scale = TARGET_MIN_WIDTH / w
    return cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)


def normalize_background(gray: np.ndarray) -> np.ndarray:
    """Flatten paper colour, stains and shadows so text is dark on an even white page."""
    k = max(15, (min(gray.shape) // 40) | 1)
    background = cv2.medianBlur(cv2.dilate(gray, np.ones((7, 7), np.uint8)), k)
    norm = cv2.divide(gray, background, scale=255)
    return cv2.normalize(norm, None, 0, 255, cv2.NORM_MINMAX)


def estimate_skew(gray: np.ndarray) -> float:
    """Angle (degrees) that makes text lines horizontal, found by maximising row-profile sharpness."""
    small = gray
    if gray.shape[1] > 1000:
        f = 1000 / gray.shape[1]
        small = cv2.resize(gray, (1000, int(gray.shape[0] * f)), interpolation=cv2.INTER_AREA)
    _, binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = binary.shape
    centre = (w / 2, h / 2)

    def score(angle):
        m = cv2.getRotationMatrix2D(centre, angle, 1.0)
        rotated = cv2.warpAffine(binary, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        rows = rotated.sum(axis=1, dtype=np.float64)
        return float(np.sum(np.diff(rows) ** 2))

    coarse = max(np.arange(-MAX_SKEW_DEGREES, MAX_SKEW_DEGREES + 0.01, 1.0), key=score)
    fine = max(np.arange(coarse - 1, coarse + 1.01, 0.2), key=score)
    return float(round(fine, 1))


def rotate(gray: np.ndarray, angle: float) -> np.ndarray:
    if abs(angle) < 0.2:
        return gray
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(gray, m, (nw, nh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def remove_table_lines(gray: np.ndarray, min_fraction: float = 1 / 25) -> np.ndarray:
    """Erase long horizontal / vertical rules (table grids), which confuse Tesseract's layout analysis.
    min_fraction = shortest line removed, as a share of the page width / height. Keep it large where
    Devanagari matters: the headline (shirorekha) joining letters is itself a horizontal stroke."""
    _, inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = gray.shape
    horizontal = cv2.morphologyEx(inv, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, int(w * min_fraction)), 1)))
    vertical = cv2.morphologyEx(inv, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(40, int(h * min_fraction)))))
    lines = cv2.dilate(cv2.bitwise_or(horizontal, vertical), np.ones((3, 3), np.uint8))
    out = gray.copy()
    out[lines > 0] = 255
    return out


def adaptive_binarize(gray: np.ndarray) -> np.ndarray:
    """Local threshold that recovers faint / faded ink."""
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 12)


def enhanced_variants(image: Image.Image, skew: float | None = None) -> dict[str, Image.Image]:
    """Cleaned-up versions of a page, as PIL images, keyed by a short description."""
    flat = normalize_background(upscale(to_gray_array(image)))
    angle = estimate_skew(flat) if skew is None else skew
    flat = rotate(flat, angle)
    label = f"deskew {angle:+.1f}°, " if abs(angle) >= 0.2 else ""
    return {
        f"enhanced ({label}background removed)": Image.fromarray(flat),
        f"enhanced ({label}background + table lines removed)": Image.fromarray(remove_table_lines(flat)),
        f"enhanced ({label}adaptive threshold for faded ink, lines removed)":
            Image.fromarray(remove_table_lines(adaptive_binarize(flat))),
    }


def quick_skew(image: Image.Image) -> float:
    """Cheap skew estimate on the original image (used to decide whether clean-up is needed)."""
    return estimate_skew(normalize_background(to_gray_array(image)))
