"""
Frame interpolation service using the RIFE (Real-Time Intermediate Flow Estimation) model.
Falls back to alpha blending if RIFE weights are not available.
"""
import cv2
import numpy as np
import os
import logging
import time
import math
from datetime import datetime, timezone
from typing import Optional
import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weight path resolution
# ---------------------------------------------------------------------------
WEIGHTS_DIR = os.path.join(os.path.dirname(__file__), "..", "rife_model", "weights")
WEIGHTS_DIR = os.path.abspath(WEIGHTS_DIR)
MODEL_NAME = "RIFE HDv3"
FALLBACK_MODE = "OpenCV alpha blend"


def _utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _performance_explanation(device: Optional[str], fallback_active: bool) -> str:
    """Explain expected inference speed/behavior for logs and UI."""
    if fallback_active:
        return "Fallback interpolation active: OpenCV alpha blending is being used instead of RIFE inference."
    if device == "cuda":
        return "CUDA acceleration active: fast GPU inference is expected."
    if device == "mps":
        return "Apple Metal (MPS) acceleration active: fast GPU-class inference is expected."
    return "CPU inference active: processing will be slower than GPU/MPS acceleration."


class RIFEInterpolator:
    """Wraps the RIFE neural network for single-pair frame interpolation."""

    def __init__(self, weights_dir: str = WEIGHTS_DIR):
        self.weights_dir = weights_dir
        self.weights_path = os.path.join(weights_dir, "flownet.pkl")
        self.model = None
        self.model_loaded = False
        self.device = None
        self.load_error = None
        self.loaded_at = None
        self.last_run = None
        self.last_batch = None

        if os.path.exists(self.weights_path):
            try:
                from app.rife_model.RIFE import Model as RIFEModel
                self.model = RIFEModel()
                self.model.load_model(weights_dir)
                self.device = self.model._device
                self.model_loaded = True
                self.loaded_at = _utc_now()
                weights_size_mb = os.path.getsize(self.weights_path) / (1024 * 1024)
                logger.info(
                    "Interpolation model loaded | model=%s | framework=PyTorch %s | "
                    "weights=%s | size_mb=%.2f | device=%s",
                    MODEL_NAME,
                    torch.__version__,
                    self.weights_path,
                    weights_size_mb,
                    self.device,
                )
            except Exception as e:
                self.load_error = str(e)
                logger.exception("Failed to load %s model", MODEL_NAME)
                self.model_loaded = False
        else:
            self.load_error = f"Weights not found at {self.weights_path}"
            logger.warning(
                f"RIFE weights not found at {self.weights_path}. "
                "Falling back to alpha blending. "
                "Run 'python download_weights.py' to download weights."
            )

    def get_diagnostics(self) -> dict:
        """Return model/runtime diagnostics for API visibility and verification."""
        fallback_active = not (self.model_loaded and self.model is not None)
        device_name = str(self.device) if self.device is not None else None
        weights_size_bytes = (
            os.path.getsize(self.weights_path) if os.path.exists(self.weights_path) else None
        )
        return {
            "model": {
                "name": MODEL_NAME,
                "framework": f"PyTorch {torch.__version__}",
                "weightsFile": os.path.basename(self.weights_path),
                "weightsPath": self.weights_path,
                "weightsSizeBytes": weights_size_bytes,
                "weightsSizeMB": round(weights_size_bytes / (1024 * 1024), 2)
                if weights_size_bytes is not None else None,
                "loaded": self.model_loaded,
                "loadedAt": self.loaded_at,
                "device": device_name,
                "cudaAvailable": torch.cuda.is_available(),
                "mpsAvailable": bool(
                    hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
                ),
                "loadError": self.load_error,
            },
            "execution": {
                "activeMode": "rife" if not fallback_active else "opencv_alpha_blend",
                "fallbackActive": fallback_active,
                "fallbackBehavior": f"{FALLBACK_MODE} when weights are missing or model load fails",
                "performanceExplanation": _performance_explanation(device_name, fallback_active),
                "lastRun": self.last_run,
                "lastBatch": self.last_batch,
            },
        }

    # ------------------------------------------------------------------
    # Image I/O helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _read_image(path: str):
        """Read an image with OpenCV, supporting both RGB and RGBA."""
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"Failed to load image: {path}")
        return img

    @staticmethod
    def _separate_alpha(img: np.ndarray):
        """Split an image into BGR + optional alpha channel."""
        if img.ndim == 2:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), None
        if img.shape[2] == 4:
            return img[:, :, :3], img[:, :, 3]
        return img, None

    @staticmethod
    def _merge_alpha(bgr: np.ndarray, alpha: np.ndarray):
        """Recombine BGR image with an alpha channel."""
        if alpha is None:
            return bgr
        return np.dstack([bgr, alpha])

    @staticmethod
    def _alpha_to_valid_mask(alpha: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
        """Convert an alpha channel to a boolean validity mask."""
        if alpha is None:
            return np.ones(shape, dtype=bool)
        return alpha >= 64

    @staticmethod
    def _prefill_missing_regions(
        img_bgr: np.ndarray,
        valid_self: np.ndarray,
        other_bgr: np.ndarray,
        valid_other: np.ndarray,
        fill_value: int = 128,
    ) -> np.ndarray:
        """
        Fill missing regions in one image with complementary coverage from the other.

        This gives RIFE a full stitched raster instead of feeding large neutral bands,
        which substantially reduces swath-strip artifacts in the generated frame.
        """
        filled = img_bgr.copy()
        filled[~valid_self & valid_other] = other_bgr[~valid_self & valid_other]
        filled[~valid_self & ~valid_other] = fill_value
        return filled

    @staticmethod
    def _compose_full_frame(
        result_bgr: np.ndarray,
        img0_bgr: np.ndarray,
        img1_bgr: np.ndarray,
        valid0: np.ndarray,
        valid1: np.ndarray,
    ) -> np.ndarray:
        """
        Build a continuous output image from RIFE output plus real source coverage.

        Where only one source has valid pixels, prefer that real source data instead of
        leaving transparent gaps or neutral-gray placeholder stripes in the final frame.
        """
        composed = result_bgr.copy()
        composed[valid0 & ~valid1] = img0_bgr[valid0 & ~valid1]
        composed[~valid0 & valid1] = img1_bgr[~valid0 & valid1]
        return composed

    # ------------------------------------------------------------------
    # Tensor conversion
    # ------------------------------------------------------------------
    def _img_to_tensor(self, img_bgr: np.ndarray) -> torch.Tensor:
        """
        Convert BGR uint8 image → [1, 3, H, W] float32 tensor in [0, 1].
        Also converts BGR → RGB for the model.
        """
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        t = torch.from_numpy(img_rgb.astype(np.float32) / 255.0)
        t = t.permute(2, 0, 1).unsqueeze(0)  # HWC → CHW → BCHW
        return t.to(self.device)

    @staticmethod
    def _tensor_to_img(tensor: torch.Tensor) -> np.ndarray:
        """
        Convert [1, 3, H, W] float32 tensor in [0, 1] → BGR uint8 image.
        """
        img = tensor.squeeze(0).permute(1, 2, 0).cpu().numpy()  # BCHW → HWC
        img = np.clip(img * 255.0, 0, 255).astype(np.uint8)
        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        return img_bgr

    # ------------------------------------------------------------------
    # Padding (RIFE needs dimensions divisible by 32)
    # ------------------------------------------------------------------
    @staticmethod
    def _pad_to_multiple(tensor: torch.Tensor, multiple: int = 32):
        """
        Pad a [1, C, H, W] tensor so H and W are multiples of `multiple`.
        Returns (padded_tensor, (pad_h, pad_w)).
        """
        _, _, h, w = tensor.shape
        pad_h = (multiple - h % multiple) % multiple
        pad_w = (multiple - w % multiple) % multiple
        if pad_h > 0 or pad_w > 0:
            tensor = F.pad(tensor, (0, pad_w, 0, pad_h), mode='reflect')
        return tensor, (pad_h, pad_w)

    @staticmethod
    def _unpad(tensor: torch.Tensor, pad_h: int, pad_w: int):
        """Remove padding added by _pad_to_multiple."""
        _, _, h, w = tensor.shape
        if pad_h > 0:
            tensor = tensor[:, :, :h - pad_h, :]
        if pad_w > 0:
            tensor = tensor[:, :, :, :w - pad_w]
        return tensor

    # ------------------------------------------------------------------
    # Core interpolation
    # ------------------------------------------------------------------
    def interpolate(self, img0_path: str, img1_path: str, output_path: str, ratio: float = 0.5) -> bool:
        """
        Interpolate a single frame between img0 and img1 at given ratio.
        ratio=0.0 → img0, ratio=1.0 → img1, ratio=0.5 → midpoint.

        Correctly handles satellite imagery with NoData transparency:
        1. Transparent (NoData) pixels are filled with neutral gray before RIFE
           so they don't introduce dark artifacts.
        2. Complementary valid coverage from the other source is stitched in before
           inference so the model sees a continuous raster instead of vertical swaths.
        3. The final output stays opaque anywhere EITHER source contains real data,
           preventing the basemap from showing through gap regions.
        """
        if not os.path.exists(img0_path) or not os.path.exists(img1_path):
            raise FileNotFoundError(f"Missing images: {img0_path} or {img1_path}")

        started_at = _utc_now()
        started_perf = time.perf_counter()
        logger.info(
            "Interpolation started | input0=%s | input1=%s | output=%s | ratio=%.3f | mode=%s",
            img0_path,
            img1_path,
            output_path,
            ratio,
            "rife" if self.model_loaded and self.model is not None else "opencv_alpha_blend",
        )

        img0_raw = self._read_image(img0_path)
        img1_raw = self._read_image(img1_path)

        # Ensure both images same size
        h, w = img0_raw.shape[:2]
        img1_raw = cv2.resize(img1_raw, (w, h))

        # Separate alpha channels
        img0_bgr, alpha0 = self._separate_alpha(img0_raw)
        img1_bgr, alpha1 = self._separate_alpha(img1_raw)
        valid0 = self._alpha_to_valid_mask(alpha0, (h, w))
        valid1 = self._alpha_to_valid_mask(alpha1, (h, w))

        # ── Stitch complementary coverage before RIFE ─────────────────────
        # This turns partially missing swaths into a single continuous raster.
        img0_for_model = self._prefill_missing_regions(img0_bgr, valid0, img1_bgr, valid1)
        img1_for_model = self._prefill_missing_regions(img1_bgr, valid1, img0_bgr, valid0)

        # ── Run RIFE (or alpha-blend fallback) on the clean BGRs ──────────
        if self.model_loaded and self.model is not None:
            logger.info(
                "Running neural interpolation | model=%s | device=%s | ratio=%.3f | note=%s",
                MODEL_NAME,
                self.device,
                ratio,
                _performance_explanation(str(self.device), False),
            )
            result_bgr = self._rife_interpolate(img0_for_model, img1_for_model, ratio)
            execution_mode = "rife"
        else:
            logger.warning(
                "Falling back to %s | reason=%s | note=%s",
                FALLBACK_MODE,
                self.load_error or "model not available",
                _performance_explanation(None, True),
            )
            result_bgr = self._alpha_blend(img0_for_model, img1_for_model, ratio)
            execution_mode = "opencv_alpha_blend"

        # Keep a single, full stitched image instead of partial swath slices.
        result_bgr = self._compose_full_frame(result_bgr, img0_bgr, img1_bgr, valid0, valid1)

        # Opaque anywhere either source has valid coverage.
        if alpha0 is not None or alpha1 is not None:
            a0 = alpha0 if alpha0 is not None else np.full((h, w), 255, dtype=np.uint8)
            a1 = alpha1 if alpha1 is not None else np.full((h, w), 255, dtype=np.uint8)
            result_alpha = np.maximum(a0, a1)
        else:
            result_alpha = None

        result = self._merge_alpha(result_bgr, result_alpha)

        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
        cv2.imwrite(output_path, result)

        completed_at = _utc_now()
        duration_ms = round((time.perf_counter() - started_perf) * 1000, 2)
        opaque_coverage_pct = (
            round(float((result_alpha >= 255).mean() * 100), 3)
            if result_alpha is not None else 100.0
        )
        self.last_run = {
            "startedAt": started_at,
            "completedAt": completed_at,
            "durationMs": duration_ms,
            "input0": img0_path,
            "input1": img1_path,
            "output": output_path,
            "ratio": ratio,
            "executionMode": execution_mode,
            "device": str(self.device) if self.device is not None else None,
            "outputShape": list(result.shape),
            "opaqueCoveragePct": opaque_coverage_pct,
            "usedModelWeights": self.model_loaded,
            "performanceExplanation": _performance_explanation(
                str(self.device) if self.device is not None else None,
                execution_mode != "rife",
            ),
        }
        logger.info(
            "Interpolation completed | mode=%s | duration_ms=%.2f | output=%s | shape=%s | opaque_coverage_pct=%.3f",
            execution_mode,
            duration_ms,
            output_path,
            result.shape,
            opaque_coverage_pct,
        )
        return True


    def _rife_interpolate(self, img0_bgr: np.ndarray, img1_bgr: np.ndarray, ratio: float) -> np.ndarray:
        """Run RIFE neural network inference."""
        with torch.no_grad():
            t0 = self._img_to_tensor(img0_bgr)
            t1 = self._img_to_tensor(img1_bgr)

            # Pad to multiple of 32
            t0_padded, (ph, pw) = self._pad_to_multiple(t0)
            t1_padded, _ = self._pad_to_multiple(t1)

            # Run RIFE inference
            result = self.model.inference(t0_padded, t1_padded, timestep=ratio)

            # Remove padding
            result = self._unpad(result, ph, pw)

            return self._tensor_to_img(result)

    @staticmethod
    def _alpha_blend(img0_bgr: np.ndarray, img1_bgr: np.ndarray, ratio: float) -> np.ndarray:
        """Simple alpha-blending fallback."""
        alpha = 1.0 - ratio
        beta = ratio
        return cv2.addWeighted(img0_bgr, alpha, img1_bgr, beta, 0)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
interpolator = RIFEInterpolator()


def generate_intermediate_frames(
    frame0_path: str,
    frame1_path: str,
    output_dir: str,
    num_frames: int = 1,
    file_prefix: str = "interp"
) -> list:
    """
    Generate intermediate frames using recursive bisection.

    The midpoint is always generated first, then each half-interval is subdivided
    recursively. This is more stable than repeatedly interpolating fixed linear
    ratios from the original pair.
    """
    os.makedirs(output_dir, exist_ok=True)
    generated_records = []
    duration_ms = []
    batch_started_at = _utc_now()
    logger.info(
        "Interpolation batch started | input0=%s | input1=%s | requested_frames=%d | output_dir=%s | mode=%s",
        frame0_path,
        frame1_path,
        num_frames,
        output_dir,
        "rife" if interpolator.model_loaded and interpolator.model is not None else "opencv_alpha_blend",
    )

    if num_frames <= 0:
        return []

    def recurse(
        left_path: str,
        right_path: str,
        left_ratio: float,
        right_ratio: float,
        remaining_frames: int,
    ) -> None:
        if remaining_frames <= 0:
            return

        mid_ratio = (left_ratio + right_ratio) / 2.0
        filename = f"{file_prefix}_{int(round(mid_ratio * 100)):02d}.png"
        out_path = os.path.join(output_dir, filename)

        logger.info(
            "Recursive bisection step | global_ratio=%.3f | remaining=%d | output=%s",
            mid_ratio,
            remaining_frames,
            filename,
        )
        interpolator.interpolate(left_path, right_path, out_path, 0.5)
        generated_records.append({
            "path": out_path,
            "ratio": round(mid_ratio, 4),
        })
        if interpolator.last_run is not None:
            duration_ms.append(interpolator.last_run["durationMs"])

        child_frames = remaining_frames - 1
        left_count = int(math.ceil(child_frames / 2.0))
        right_count = child_frames - left_count
        recurse(left_path, out_path, left_ratio, mid_ratio, left_count)
        recurse(out_path, right_path, mid_ratio, right_ratio, right_count)

    recurse(frame0_path, frame1_path, 0.0, 1.0, num_frames)
    generated_records.sort(key=lambda item: item["ratio"])
    generated_paths = [record["path"] for record in generated_records]
    ratios = [record["ratio"] for record in generated_records]

    interpolator.last_batch = {
        "startedAt": batch_started_at,
        "completedAt": _utc_now(),
        "input0": frame0_path,
        "input1": frame1_path,
        "requestedFrames": num_frames,
        "generatedFrames": len(generated_records),
        "outputDir": output_dir,
        "filePrefix": file_prefix,
        "strategy": "recursive_bisection",
        "ratios": ratios,
        "frameDurationsMs": duration_ms,
        "executionMode": "rife" if interpolator.model_loaded and interpolator.model is not None else "opencv_alpha_blend",
        "outputs": generated_paths,
        "performanceExplanation": _performance_explanation(
            str(interpolator.device) if interpolator.device is not None else None,
            not (interpolator.model_loaded and interpolator.model is not None),
        ),
    }
    logger.info(
        "Interpolation batch completed | generated_frames=%d | output_dir=%s",
        len(generated_records),
        output_dir,
    )
    return generated_records
