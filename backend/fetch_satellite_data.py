#!/usr/bin/env python3
"""
Fetch real satellite imagery from NASA GIBS WMS for the India region.
Uses EPSG:3857 endpoint so images match the OpenLayers map CRS exactly.
Downloads multiple dates, masks NoData (black swath gaps), then runs RIFE.

Usage:
    cd backend
    python fetch_satellite_data.py
"""
import os
import sys
import math
import requests
import cv2
import numpy as np

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
# India bounding box as EPSG:3857 metres (pre‑computed from [68,6,98,36] EPSG:4326)
# minX, minY, maxX, maxY
EXTENT_3857 = [7569725.37, 669141.06, 10909310.10, 4300621.37]

# Pixel dimensions — aspect ratio must match the geographic extent
# extent_w / extent_h = 3339585 / 3631480 ≈ 0.9196  → 960 wide × 1024 tall
WIDTH  = 960
HEIGHT = 1024

# NASA GIBS EPSG:3857 WMS endpoint
WMS_URL = "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi"

# MODIS Terra True Color — daily, full global coverage
LAYER = "MODIS_Terra_CorrectedReflectance_TrueColor"

# Consecutive dates = realistic cloud-movement interpolation
DATES = [
    "2024-06-01",
    "2024-06-02",
    "2024-06-03",
]

# Intermediate frames per pair (RIFE)
NUM_INTERP = 3

# Directories
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
RAW_DIR   = os.path.join(BASE_DIR, "data", "raw_frames")
INTERP_DIR = os.path.join(BASE_DIR, "data", "interpolated_frames")


# ------------------------------------------------------------------
# WMS fetch
# ------------------------------------------------------------------
def fetch_frame(date: str, output_path: str) -> bool:
    """
    Fetch a satellite frame from the EPSG:3857 GIBS endpoint.
    BBOX format for EPSG:3857 WMS 1.3.0: minX,minY,maxX,maxY (metres).
    """
    bbox_str = ",".join(str(v) for v in EXTENT_3857)

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "LAYERS":  LAYER,
        "STYLES":  "",
        "CRS":     "EPSG:3857",
        "BBOX":    bbox_str,
        "WIDTH":   str(WIDTH),
        "HEIGHT":  str(HEIGHT),
        "FORMAT":  "image/png",   # PNG to preserve exact pixel values for masking
        "TIME":    date,
        "TRANSPARENT": "FALSE",
    }

    print(f"  Fetching {date} from GIBS EPSG:3857...")

    try:
        r = requests.get(WMS_URL, params=params, timeout=60)
        r.raise_for_status()

        ct = r.headers.get("Content-Type", "")
        if "image" not in ct:
            print(f"    [ERROR] Unexpected content-type: {ct}")
            print(f"    Body: {r.text[:400]}")
            return False

        raw = np.frombuffer(r.content, np.uint8)
        img = cv2.imdecode(raw, cv2.IMREAD_COLOR)   # BGR, uint8
        if img is None:
            print(f"    [ERROR] cv2 could not decode image")
            return False

        print(f"    Raw shape: {img.shape}, mean={img.mean():.1f}, std={img.std():.1f}")

        # Mask NoData (black swath gaps from MODIS)
        img_out = mask_nodata(img)

        cv2.imwrite(output_path, img_out)
        kb = os.path.getsize(output_path) / 1024
        print(f"    Saved: {os.path.basename(output_path)} ({kb:.0f} KB)")
        return True

    except requests.RequestException as e:
        print(f"    [ERROR] Request failed: {e}")
        return False


# ------------------------------------------------------------------
# NoData masking
# ------------------------------------------------------------------
def mask_nodata(img_bgr: np.ndarray,
                black_thresh: int = 10,
                noise_thresh: int = 20) -> np.ndarray:
    """
    Convert pure‑black (NoData) pixels to transparent.

    Logic:
    - A pixel is NoData if all channels < black_thresh.
    - We also run a morphological closing to fill tiny isolated dark pixels
      that are valid data (shadows) vs large contiguous black regions (swaths).
    - Returns BGRA image.
    """
    b, g, r = cv2.split(img_bgr)
    # combined brightness
    brightness = cv2.add(b, cv2.add(g, r)).astype(np.uint16)  # 0‑765

    # Primary NoData mask: all channels very dark
    nodata_mask = (img_bgr.max(axis=2) < black_thresh).astype(np.uint8) * 255

    # Erode small isolated dark specs (they're likely valid shadows, not NoData)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    nodata_mask = cv2.morphologyEx(nodata_mask, cv2.MORPH_OPEN, kernel)

    # Build alpha: 0 where NoData, 255 everywhere else
    alpha = cv2.bitwise_not(nodata_mask)

    img_bgra = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA)
    img_bgra[:, :, 3] = alpha

    transparent_pct = (nodata_mask > 0).mean() * 100
    print(f"    NoData masked: {transparent_pct:.1f}% of pixels made transparent")

    return img_bgra


# ------------------------------------------------------------------
# RIFE interpolation
# ------------------------------------------------------------------
def run_interpolation(frame_paths: list) -> list:
    sys.path.insert(0, BASE_DIR)
    from app.services.interpolation import generate_intermediate_frames

    all_generated = []
    for i in range(len(frame_paths) - 1):
        f1, f2 = frame_paths[i], frame_paths[i + 1]
        b1 = os.path.splitext(os.path.basename(f1))[0]
        b2 = os.path.splitext(os.path.basename(f2))[0]
        prefix = f"interp_{b1}_{b2}"

        print(f"\n  Interpolating: {os.path.basename(f1)} → {os.path.basename(f2)}")
        generated = generate_intermediate_frames(
            f1, f2, INTERP_DIR,
            num_frames=NUM_INTERP,
            file_prefix=prefix
        )
        for g in generated:
            kb = os.path.getsize(g) / 1024
            print(f"    Generated: {os.path.basename(g)} ({kb:.0f} KB)")
        all_generated.extend(generated)
    return all_generated


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    os.makedirs(RAW_DIR,   exist_ok=True)
    os.makedirs(INTERP_DIR, exist_ok=True)

    print("=" * 60)
    print("  WMS Satellite Data Fetcher (EPSG:3857)")
    print("=" * 60)
    print(f"  Extent (EPSG:3857): {EXTENT_3857}")
    print(f"  Resolution: {WIDTH}×{HEIGHT} px (aspect-ratio corrected)")
    print(f"  Layer: {LAYER}")
    print(f"  Dates: {DATES}")
    print()

    # Clean stale frames
    for d in [RAW_DIR, INTERP_DIR]:
        for f in os.listdir(d):
            if f.lower().endswith(('.png', '.jpg')):
                os.remove(os.path.join(d, f))
    print("  Cleaned old frames.\n")

    # Fetch
    frame_paths = []
    for i, date in enumerate(DATES):
        label = f"{10 + i * 15:02d}_00"
        out = os.path.join(RAW_DIR, f"frame_{label}.png")
        if fetch_frame(date, out):
            frame_paths.append(out)
        else:
            print(f"  [SKIP] {date}")

    print(f"\n  Fetched {len(frame_paths)}/{len(DATES)} frames.")
    if len(frame_paths) < 2:
        print("  Need ≥2 frames. Aborting.")
        sys.exit(1)

    # Interpolate
    print()
    generated = run_interpolation(frame_paths)

    print(f"\n{'='*60}")
    print(f"  Done. {len(frame_paths)} raw + {len(generated)} interpolated = "
          f"{len(frame_paths)+len(generated)} total frames.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
