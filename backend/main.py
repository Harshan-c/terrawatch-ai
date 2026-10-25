from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import cv2
import numpy as np
import base64
import os
from datetime import datetime, timezone

app = FastAPI(
    title="TerraWatch AI",
    description="Satellite screenshot change detection prototype",
    version="1.7.0",
)

# Set FRONTEND_URL in the Vercel backend project's Environment Variables to your
# deployed frontend origin (for example, https://your-frontend.vercel.app).
# The regex also permits Vercel preview domains; remove it if you want to allow
# only explicitly listed origins.
frontend_url = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
if frontend_url:
    allowed_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://[a-zA-Z0-9-]+(?:-[a-zA-Z0-9-]+)*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Approximate site polygon for the exact screenshot framing shared earlier.
# Coordinates are normalized x,y values in the range 0..1.
# Recalibrate whenever either uploaded image is cropped/framed differently.
SITE_POLYGON = [
    (0.15, 0.92),
    (0.25, 0.34),
    (0.65, 0.12),
    (0.94, 0.60),
    (0.76, 0.73),
    (0.79, 0.75),
]

# Heuristic RGB screenshot settings, not scientifically validated thresholds.
# The algorithm now requires evidence that a pixel looked vegetated BEFORE
# and then became less green, rather than flagging any color difference.
MIN_BEFORE_EXG = 12.0
MIN_EXG_DROP = 22.0
MIN_REGION_FRACTION = 0.0005
MAX_REGIONS = 30


def decode_image(data: bytes):
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not read image. Upload a valid JPG, PNG, or WEBP.")
    return image


def to_data_url(image):
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        raise ValueError("Could not encode output image.")
    return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")


def resize_image(image, width, height):
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)


def align_images(reference, moving):
    """Align moving image to reference using ORB feature matches and RANSAC."""
    ref_gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    mov_gray = cv2.cvtColor(moving, cv2.COLOR_BGR2GRAY)
    orb = cv2.ORB_create(nfeatures=5000)
    kp_ref, des_ref = orb.detectAndCompute(ref_gray, None)
    kp_mov, des_mov = orb.detectAndCompute(mov_gray, None)

    diagnostics = {
        "reference_features": len(kp_ref),
        "moving_features": len(kp_mov),
        "good_matches": 0,
        "inlier_ratio": None,
        "overlap_ratio": None,
    }
    empty_mask = np.zeros(reference.shape[:2], np.uint8)
    if des_ref is None or des_mov is None:
        return moving, False, empty_mask, diagnostics

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(des_mov, des_ref, k=2)
    good = [
        pair[0] for pair in pairs
        if len(pair) == 2 and pair[0].distance < 0.72 * pair[1].distance
    ]
    diagnostics["good_matches"] = len(good)
    if len(good) < 12:
        return moving, False, empty_mask, diagnostics

    src = np.float32([kp_mov[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp_ref[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    matrix, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    if matrix is None or inliers is None or not np.isfinite(matrix).all():
        return moving, False, empty_mask, diagnostics

    inlier_ratio = float(inliers.mean())
    diagnostics["inlier_ratio"] = round(inlier_ratio, 3)
    if inlier_ratio < 0.25:
        return moving, False, empty_mask, diagnostics

    h, w = reference.shape[:2]
    aligned = cv2.warpPerspective(moving, matrix, (w, h))
    source_mask = np.full(moving.shape[:2], 255, np.uint8)
    valid_mask = cv2.warpPerspective(
        source_mask, matrix, (w, h), flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0
    )
    overlap_ratio = float(cv2.countNonZero(valid_mask)) / max(1, w * h)
    diagnostics["overlap_ratio"] = round(overlap_ratio, 3)
    if overlap_ratio < 0.50:
        return moving, False, empty_mask, diagnostics
    return aligned, True, valid_mask, diagnostics


def normalize_luminance(reference, moving):
    """Match global LAB lightness; local shadows and seasonal differences remain."""
    ref_lab = cv2.cvtColor(reference, cv2.COLOR_BGR2LAB)
    mov_lab = cv2.cvtColor(moving, cv2.COLOR_BGR2LAB)
    ref_l = ref_lab[:, :, 0].astype(np.float32)
    mov_l = mov_lab[:, :, 0].astype(np.float32)
    ref_mean, ref_std = float(ref_l.mean()), float(ref_l.std())
    mov_mean, mov_std = float(mov_l.mean()), float(mov_l.std())
    if mov_std > 1e-5:
        adjusted = (mov_l - mov_mean) * (max(ref_std, 1.0) / mov_std) + ref_mean
        mov_lab[:, :, 0] = np.clip(adjusted, 0, 255).astype(np.uint8)
    return cv2.cvtColor(mov_lab, cv2.COLOR_LAB2BGR)


def build_site_mask(image):
    h, w = image.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    points = np.array(
        [[round(x * (w - 1)), round(y * (h - 1))] for x, y in SITE_POLYGON],
        dtype=np.int32,
    )
    cv2.fillPoly(mask, [points], 255)
    return mask


def excess_green(image):
    """Simple normalized RGB excess-green proxy; not NDVI."""
    b, g, r = cv2.split(image.astype(np.float32))
    total = r + g + b + 1e-6
    rn, gn, bn = r / total, g / total, b / total
    return (2.0 * gn - rn - bn) * 255.0


def make_change_mask(before, after, valid_mask):
    before_blur = cv2.GaussianBlur(before, (5, 5), 0)
    after_blur = cv2.GaussianBlur(after, (5, 5), 0)

    exg_before = cv2.GaussianBlur(excess_green(before_blur), (5, 5), 0)
    exg_after = cv2.GaussianBlur(excess_green(after_blur), (5, 5), 0)
    exg_drop = exg_before - exg_after

    # Require BOTH (1) meaningful green signal in the before image and
    # (2) a drop in that signal. This avoids flagging pixels just because
    # their color differs between dates.
    candidate = (exg_before >= MIN_BEFORE_EXG) & (exg_drop >= MIN_EXG_DROP)
    mask = np.zeros(valid_mask.shape, np.uint8)
    mask[candidate] = 255
    mask = cv2.bitwise_and(mask, valid_mask)

    # Clean speckles and join nearby candidate pixels.
    open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=1)
    mask = cv2.bitwise_and(mask, valid_mask)

    contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_pixels = max(1, cv2.countNonZero(valid_mask))
    min_area = max(150, int(valid_pixels * MIN_REGION_FRACTION))
    clean_mask = np.zeros_like(mask)
    regions = []

    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = int(cv2.contourArea(contour))
        if area < min_area:
            continue
        x, y, rw, rh = cv2.boundingRect(contour)
        cv2.drawContours(clean_mask, [contour], -1, 255, cv2.FILLED)
        regions.append({
            "id": len(regions) + 1,
            "x": int(x), "y": int(y),
            "width": int(rw), "height": int(rh),
            "pixels": area,
            "relative_size_pct": round(area / valid_pixels * 100, 3),
        })
        if len(regions) >= MAX_REGIONS:
            break

    return clean_mask, regions, min_area


@app.get("/")
def root():
    return {"name": "TerraWatch AI", "status": "running", "version": app.version}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(before: UploadFile = File(...), after: UploadFile = File(...)):
    if before.content_type not in ALLOWED_TYPES or after.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Upload JPG, PNG, or WEBP images.")

    try:
        before_bytes, after_bytes = await before.read(), await after.read()
        if not before_bytes or not after_bytes:
            raise ValueError("One or both uploaded images are empty.")
        before_original = decode_image(before_bytes)
        after_original = decode_image(after_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    orig_h, orig_w = after_original.shape[:2]
    scale = min(1.0, 1200.0 / max(orig_w, orig_h))
    width, height = max(1, int(orig_w * scale)), max(1, int(orig_h * scale))
    before_img = resize_image(before_original, width, height)
    after_img = resize_image(after_original, width, height)

    site_mask = build_site_mask(after_img)
    aligned_before, alignment_ok, overlap_mask, alignment_info = align_images(after_img, before_img)

    warnings = [
        "This is a heuristic RGB screenshot detector, not a validated satellite land-cover model.",
        "The site polygon is approximate and only valid for the previously shared screenshot framing.",
        "Google Earth labels, shadows, seasonal changes, and imagery enhancement may cause false detections.",
    ]

    if not alignment_ok:
        warnings.append("Image alignment failed; change score suppressed.")
        before_preview = before_img
        valid_mask = np.zeros((height, width), np.uint8)
        clean_mask = np.zeros_like(valid_mask)
        regions = []
        min_area = max(150, int(cv2.countNonZero(site_mask) * MIN_REGION_FRACTION))
        changed_pixels, changed_pct = 0, 0.0
        change_level = "Unavailable"
    else:
        before_img = normalize_luminance(after_img, aligned_before)
        valid_mask = cv2.bitwise_and(site_mask, overlap_mask)
        before_preview = before_img
        clean_mask, regions, min_area = make_change_mask(before_img, after_img, valid_mask)
        valid_pixels = max(1, cv2.countNonZero(valid_mask))
        changed_pixels = int(cv2.countNonZero(clean_mask))
        changed_pct = round(changed_pixels / valid_pixels * 100, 2)

        if changed_pct >= 50:
            change_level = "Review required"
            warnings.append(
                "More than half the selected area is flagged. Inspect the binary mask; "
                "do not interpret this percentage as confirmed cleared land."
            )
        elif changed_pct >= 15:
            change_level = "High candidate vegetation loss"
        elif changed_pct >= 5:
            change_level = "Moderate candidate vegetation loss"
        elif changed_pct >= 1:
            change_level = "Low candidate vegetation loss"
        else:
            change_level = "Minimal candidate vegetation loss"

    overlay = after_img.copy()
    red_layer = np.zeros_like(after_img)
    red_layer[:] = (30, 40, 235)
    blended = cv2.addWeighted(after_img, 0.55, red_layer, 0.45, 0)
    selected = clean_mask > 0
    overlay[selected] = blended[selected]

    for region in regions[:20]:
        x, y, rw, rh = region["x"], region["y"], region["width"], region["height"]
        cv2.rectangle(overlay, (x, y), (x + rw, y + rh), (30, 230, 245), 2)
        cv2.putText(
            overlay, f"R{region['id']}", (x, max(16, y - 5)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 230, 245), 1, cv2.LINE_AA
        )

    report = {
        "project": "TerraWatch AI",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "before_filename": before.filename or "before image",
        "after_filename": after.filename or "after image",
        "image_dimensions": {"width": width, "height": height},
        "alignment": {"succeeded": alignment_ok, "diagnostics": alignment_info},
        "analysis": {
            "method": "ORB/RANSAC alignment + LAB lightness normalization + before-vegetation ExG proxy + ExG decrease threshold + morphology",
            "minimum_before_exg": MIN_BEFORE_EXG,
            "minimum_exg_drop": MIN_EXG_DROP,
            "minimum_region_pixels": min_area,
            "site_polygon_enabled": True,
            "site_polygon_normalized_points": SITE_POLYGON,
        },
        "results": {
            "changed_pixel_count": changed_pixels,
            "changed_area_percentage": changed_pct,
            "analysis_area_pixels": int(cv2.countNonZero(valid_mask)),
            "detected_regions": len(regions),
            "change_level": change_level,
        },
        "regions": regions,
        "warnings": warnings,
        "interpretation": "Candidate vegetation loss only. RGB screenshots cannot confirm deforestation or real-world area.",
        "limitations": [
            "The site polygon is approximate and tied to the original screenshot framing.",
            "Excess green is an RGB proxy, not NDVI or a trained classifier.",
            "Image dates may differ in lighting, season, atmosphere, and processing.",
            "The changed percentage is a pixel ratio, not real-world land area.",
        ],
    }

    return JSONResponse({
        "before_preview": to_data_url(before_preview),
        "after_preview": to_data_url(after_img),
        "overlay": to_data_url(overlay),
        "mask": to_data_url(clean_mask),
        "stats": {
            "width": width, "height": height,
            "changed_pixel_count": changed_pixels,
            "changed_area_percentage": changed_pct,
            "detected_regions": len(regions),
            "threshold": MIN_EXG_DROP,
            "change_level": change_level,
            "alignment_succeeded": alignment_ok,
            "warnings": warnings,
        },
        "regions": regions,
        "report": report,
    })
