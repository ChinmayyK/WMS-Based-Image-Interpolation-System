"""
Production interpolation engine with governed model loading and audit logging.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import cv2
import numpy as np
import torch
import torch.nn.functional as F
import yaml

from app.services.metadata import append_interpolation_log


logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
INTERPOLATED_MASKS_DIR = os.path.join(DATA_DIR, "interpolated_masks")
LATEST_EVALUATION_PATH = os.path.join(DATA_DIR, "evaluations", "latest_evaluation.json")

WEIGHTS_DIR = os.path.join(os.path.dirname(__file__), "..", "rife_model", "weights")
WEIGHTS_DIR = os.path.abspath(WEIGHTS_DIR)

DEFAULT_INTERPOLATION_CONFIG = {
    "preferred_model": "RIFE 4.6",
    "active_model": "RIFE HDv3",
    "active_version": "HDv3",
    "benchmark_compliant": False,
    "deviation_note": "PRD v2.0 prefers RIFE 4.6, but the current runtime uses RIFE HDv3.",
    "weights_file": "flownet.pkl",
    "expected_sha256": "fe854fc8996547c953f732aaa3b78cae76cc0a12833ae856ea0749c4c570d7d8",
    "fallback_method": "farneback_optical_flow",
    "tile_threshold_px": 1024,
    "tile_overlap_px": 64,
    "suspicious_runtime_ms": 5.0,
}


def _load_interpolation_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULT_INTERPOLATION_CONFIG)

    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    configured = payload.get("interpolation") or {}
    merged = dict(DEFAULT_INTERPOLATION_CONFIG)
    merged.update(configured)
    return merged


INTERPOLATION_CONFIG = _load_interpolation_config()
MODEL_NAME = INTERPOLATION_CONFIG["active_model"]
MODEL_VERSION = INTERPOLATION_CONFIG["active_version"]
PREFERRED_MODEL = INTERPOLATION_CONFIG["preferred_model"]
BENCHMARK_COMPLIANT = bool(INTERPOLATION_CONFIG["benchmark_compliant"])
MODEL_DEVIATION_NOTE = INTERPOLATION_CONFIG["deviation_note"]
WEIGHTS_FILENAME = INTERPOLATION_CONFIG["weights_file"]
EXPECTED_WEIGHTS_SHA256 = INTERPOLATION_CONFIG["expected_sha256"]
FALLBACK_METHOD = INTERPOLATION_CONFIG["fallback_method"]
TILE_THRESHOLD_PX = int(INTERPOLATION_CONFIG["tile_threshold_px"])
TILE_OVERLAP_PX = int(INTERPOLATION_CONFIG["tile_overlap_px"])
SUSPICIOUS_RUNTIME_MS = float(INTERPOLATION_CONFIG["suspicious_runtime_ms"])


class InterpolationGovernanceError(RuntimeError):
    """Raised when the interpolation model fails startup governance checks."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _performance_explanation(device: Optional[str], execution_mode: str) -> str:
    if execution_mode == FALLBACK_METHOD:
        return "Optical-flow fallback is active because neural inference raised a runtime error."
    if execution_mode == "phase0_governed_fallback":
        return "Optical-flow fallback is active because the latest Phase 0 benchmark gate did not qualify the neural model for production use."
    if execution_mode == "startup_blocked":
        return "Startup governance checks failed, so neural inference is blocked until weights are restored."
    if device == "cuda":
        return "CUDA acceleration active: fast GPU inference is expected."
    if device == "mps":
        return "Apple Metal (MPS) acceleration active: fast GPU-class inference is expected."
    return "CPU inference active: processing will be slower than GPU/MPS acceleration."


def _as_data_url(path: str) -> str:
    rel = os.path.relpath(path, DATA_DIR).replace(os.sep, "/")
    return f"/data/{rel}"


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


def _load_phase0_gate() -> Optional[dict]:
    if not os.path.exists(LATEST_EVALUATION_PATH):
        return None
    try:
        with open(LATEST_EVALUATION_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        logger.exception("Failed to load latest evaluation report for benchmark governance")
        return None
    gate = payload.get("qualificationGate")
    if isinstance(gate, dict):
        return gate
    return None


class RIFEInterpolator:
    """Wraps governed RIFE inference with optical-flow fallback and audit metadata."""

    def __init__(
        self,
        weights_dir: str = WEIGHTS_DIR,
        *,
        expected_sha256: Optional[str] = EXPECTED_WEIGHTS_SHA256,
    ):
        self.weights_dir = weights_dir
        self.weights_path = os.path.join(weights_dir, WEIGHTS_FILENAME)
        self.expected_sha256 = expected_sha256

        self.model = None
        self.model_loaded = False
        self.device = None
        self.load_error = None
        self.loaded_at = None

        self.weights_sha256 = None
        self.weights_size_bytes = None
        self.startup_validated = False
        self.startup_errors: list[str] = []

        self.last_run = None
        self.last_batch = None

        self._initialize_model()

    def _initialize_model(self) -> None:
        self.startup_errors = []

        if not os.path.exists(self.weights_path):
            self.load_error = f"Weights file not found: {self.weights_path}"
            self.startup_errors.append(self.load_error)
            logger.error("Interpolation startup validation failed | error=%s", self.load_error)
            return

        self.weights_size_bytes = os.path.getsize(self.weights_path)
        self.weights_sha256 = self._compute_sha256(self.weights_path)
        if self.expected_sha256 and self.weights_sha256 != self.expected_sha256:
            self.load_error = (
                f"Weight integrity check failed for {self.weights_path}: "
                f"expected {self.expected_sha256}, got {self.weights_sha256}"
            )
            self.startup_errors.append(self.load_error)
            logger.error("Interpolation startup validation failed | error=%s", self.load_error)
            return

        try:
            from app.rife_model.RIFE import Model as RIFEModel

            self.model = RIFEModel()
            self.model.load_model(self.weights_dir)
            self.device = self.model._device
            self.model_loaded = True
            self.loaded_at = _utc_now()
            self.startup_validated = True

            logger.info(
                "Interpolation model ready | model_name=%s | version=%s | framework=PyTorch %s | "
                "weights_file=%s | weights_size_mb=%.2f | sha256=%s | device=%s | benchmark_compliant=%s",
                MODEL_NAME,
                MODEL_VERSION,
                torch.__version__,
                os.path.basename(self.weights_path),
                self.weights_size_bytes / (1024 * 1024),
                self.weights_sha256,
                self.device,
                BENCHMARK_COMPLIANT,
            )
        except Exception as exc:
            self.load_error = str(exc)
            self.startup_errors.append(self.load_error)
            logger.exception("Interpolation model load failed")

    @staticmethod
    def _compute_sha256(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _assert_startup_ready(self) -> None:
        if self.startup_validated and self.model_loaded and self.model is not None:
            return

        error = self.load_error or "Interpolation model failed startup governance validation."
        raise InterpolationGovernanceError(
            f"Interpolation startup validation failed. Neural inference is blocked: {error}"
        )

    def _model_snapshot(self) -> dict:
        weights_size_mb = (
            round(self.weights_size_bytes / (1024 * 1024), 2)
            if self.weights_size_bytes is not None
            else None
        )
        benchmark_gate = _load_phase0_gate()
        return {
            "name": MODEL_NAME,
            "version": MODEL_VERSION,
            "preferredModel": PREFERRED_MODEL,
            "benchmarkCompliant": BENCHMARK_COMPLIANT,
            "deviationNote": None if BENCHMARK_COMPLIANT else MODEL_DEVIATION_NOTE,
            "framework": f"PyTorch {torch.__version__}",
            "weightsFile": os.path.basename(self.weights_path),
            "weightsPath": self.weights_path,
            "weightsSizeBytes": self.weights_size_bytes,
            "weightsSizeMB": weights_size_mb,
            "weightsSha256": self.weights_sha256,
            "expectedWeightsSha256": self.expected_sha256,
            "integrityVerified": bool(
                self.expected_sha256 and self.weights_sha256 == self.expected_sha256
            ),
            "loaded": self.model_loaded,
            "startupValidated": self.startup_validated,
            "loadedAt": self.loaded_at,
            "device": str(self.device) if self.device is not None else None,
            "cudaAvailable": torch.cuda.is_available(),
            "mpsAvailable": bool(
                hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
            ),
            "loadError": self.load_error,
            "startupErrors": list(self.startup_errors),
            "benchmarkGate": benchmark_gate,
        }

    def get_diagnostics(self) -> dict:
        model_snapshot = self._model_snapshot()
        last_run = self.last_run
        last_batch = self.last_batch
        benchmark_gate = model_snapshot.get("benchmarkGate")
        execution_mode = "startup_blocked"
        if self.startup_validated:
            if last_run and last_run.get("fallbackReason") == "phase0_gate_failed":
                execution_mode = "phase0_governed_fallback"
            else:
                execution_mode = FALLBACK_METHOD if (last_run and last_run.get("fallbackUsed")) else "rife"

        return {
            "model": model_snapshot,
            "execution": {
                "activeMode": execution_mode,
                "fallbackActive": bool(last_run and last_run.get("fallbackUsed")),
                "fallbackBehavior": (
                    "Farneback optical flow is used only for runtime inference failures. "
                    "Startup validation failures block interpolation."
                ),
                "fallbackMethod": FALLBACK_METHOD,
                "benchmarkGate": benchmark_gate,
                "performanceExplanation": _performance_explanation(
                    model_snapshot.get("device"),
                    execution_mode,
                ),
                "lastRun": last_run,
                "lastBatch": last_batch,
            },
        }

    @staticmethod
    def _read_image(path: str) -> np.ndarray:
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise FileNotFoundError(path)
        return img

    @staticmethod
    def _separate_alpha(img: np.ndarray) -> tuple[np.ndarray, Optional[np.ndarray]]:
        if img.ndim == 2:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), None
        if img.shape[2] == 4:
            return img[:, :, :3], img[:, :, 3]
        return img, None

    @staticmethod
    def _merge_alpha(bgr: np.ndarray, alpha: Optional[np.ndarray]) -> np.ndarray:
        if alpha is None:
            return bgr
        return np.dstack([bgr, alpha])

    @staticmethod
    def _alpha_to_valid_mask(alpha: Optional[np.ndarray], shape: tuple[int, int]) -> np.ndarray:
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
        composed = result_bgr.copy()
        composed[valid0 & ~valid1] = img0_bgr[valid0 & ~valid1]
        composed[~valid0 & valid1] = img1_bgr[~valid0 & valid1]
        return composed

    def _img_to_tensor(self, img_bgr: np.ndarray) -> torch.Tensor:
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(img_rgb.astype(np.float32) / 255.0)
        return tensor.permute(2, 0, 1).unsqueeze(0).to(self.device)

    @staticmethod
    def _tensor_to_img(tensor: torch.Tensor) -> np.ndarray:
        img = tensor.squeeze(0).permute(1, 2, 0).cpu().numpy()
        img = np.clip(img * 255.0, 0, 255).astype(np.uint8)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    @staticmethod
    def _pad_to_multiple(tensor: torch.Tensor, multiple: int = 32):
        _, _, height, width = tensor.shape
        pad_h = (multiple - height % multiple) % multiple
        pad_w = (multiple - width % multiple) % multiple
        if pad_h > 0 or pad_w > 0:
            tensor = F.pad(tensor, (0, pad_w, 0, pad_h), mode="reflect")
        return tensor, (pad_h, pad_w)

    @staticmethod
    def _unpad(tensor: torch.Tensor, pad_h: int, pad_w: int):
        _, _, height, width = tensor.shape
        if pad_h > 0:
            tensor = tensor[:, :, : height - pad_h, :]
        if pad_w > 0:
            tensor = tensor[:, :, :, : width - pad_w]
        return tensor

    def _rife_interpolate_core(self, img0_bgr: np.ndarray, img1_bgr: np.ndarray, ratio: float) -> np.ndarray:
        with torch.no_grad():
            t0 = self._img_to_tensor(img0_bgr)
            t1 = self._img_to_tensor(img1_bgr)
            t0_padded, (pad_h, pad_w) = self._pad_to_multiple(t0)
            t1_padded, _ = self._pad_to_multiple(t1)
            result = self.model.inference(t0_padded, t1_padded, timestep=ratio)
            result = self._unpad(result, pad_h, pad_w)
            return self._tensor_to_img(result)

    @staticmethod
    def _tile_starts(length: int, tile_size: int, overlap: int) -> list[int]:
        if length <= tile_size:
            return [0]
        step = max(tile_size - overlap, 1)
        starts = list(range(0, length - tile_size + 1, step))
        final_start = length - tile_size
        if starts[-1] != final_start:
            starts.append(final_start)
        return sorted(set(starts))

    @staticmethod
    def _tile_weight(tile_h: int, tile_w: int, top: bool, bottom: bool, left: bool, right: bool) -> np.ndarray:
        overlap = min(TILE_OVERLAP_PX, tile_h // 2, tile_w // 2)
        weight_y = np.ones(tile_h, dtype=np.float32)
        weight_x = np.ones(tile_w, dtype=np.float32)

        if overlap > 0:
            ramp_up = np.linspace(0.0, 1.0, overlap, dtype=np.float32)
            ramp_down = np.linspace(1.0, 0.0, overlap, dtype=np.float32)
            if top:
                weight_y[:overlap] = ramp_up
            if bottom:
                weight_y[-overlap:] = np.minimum(weight_y[-overlap:], ramp_down)
            if left:
                weight_x[:overlap] = ramp_up
            if right:
                weight_x[-overlap:] = np.minimum(weight_x[-overlap:], ramp_down)

        return np.outer(weight_y, weight_x)

    def _interpolate_tiled(
        self,
        img0_bgr: np.ndarray,
        img1_bgr: np.ndarray,
        ratio: float,
        backend: Callable[[np.ndarray, np.ndarray, float], np.ndarray],
    ) -> tuple[np.ndarray, dict]:
        height, width = img0_bgr.shape[:2]
        tile_h = min(TILE_THRESHOLD_PX, height)
        tile_w = min(TILE_THRESHOLD_PX, width)

        y_starts = self._tile_starts(height, tile_h, TILE_OVERLAP_PX)
        x_starts = self._tile_starts(width, tile_w, TILE_OVERLAP_PX)
        accum = np.zeros((height, width, 3), dtype=np.float32)
        weights = np.zeros((height, width), dtype=np.float32)

        for y in y_starts:
            for x in x_starts:
                y_end = min(y + tile_h, height)
                x_end = min(x + tile_w, width)
                tile0 = img0_bgr[y:y_end, x:x_end]
                tile1 = img1_bgr[y:y_end, x:x_end]
                interpolated_tile = backend(tile0, tile1, ratio).astype(np.float32)
                tile_weight = self._tile_weight(
                    y_end - y,
                    x_end - x,
                    top=(y > 0),
                    bottom=(y_end < height),
                    left=(x > 0),
                    right=(x_end < width),
                )
                accum[y:y_end, x:x_end] += interpolated_tile * tile_weight[:, :, None]
                weights[y:y_end, x:x_end] += tile_weight

        stitched = accum / np.maximum(weights[:, :, None], 1e-6)
        tile_info = {
            "used": True,
            "tileSize": [tile_w, tile_h],
            "overlapPx": TILE_OVERLAP_PX,
            "tileCount": len(x_starts) * len(y_starts),
        }
        return np.clip(stitched, 0, 255).astype(np.uint8), tile_info

    @staticmethod
    def _compute_farneback_flow(img0_bgr: np.ndarray, img1_bgr: np.ndarray) -> np.ndarray:
        gray0 = cv2.cvtColor(img0_bgr, cv2.COLOR_BGR2GRAY)
        gray1 = cv2.cvtColor(img1_bgr, cv2.COLOR_BGR2GRAY)
        return cv2.calcOpticalFlowFarneback(
            gray0,
            gray1,
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=25,
            iterations=5,
            poly_n=7,
            poly_sigma=1.5,
            flags=0,
        )

    @staticmethod
    def _warp_with_flow(img_bgr: np.ndarray, flow: np.ndarray, ratio: float) -> np.ndarray:
        height, width = img_bgr.shape[:2]
        grid_x, grid_y = np.meshgrid(
            np.arange(width, dtype=np.float32),
            np.arange(height, dtype=np.float32),
        )
        map_x = grid_x - flow[:, :, 0] * ratio
        map_y = grid_y - flow[:, :, 1] * ratio
        return cv2.remap(
            img_bgr,
            map_x,
            map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )

    def _optical_flow_interpolate_core(self, img0_bgr: np.ndarray, img1_bgr: np.ndarray, ratio: float) -> np.ndarray:
        flow01 = self._compute_farneback_flow(img0_bgr, img1_bgr)
        flow10 = self._compute_farneback_flow(img1_bgr, img0_bgr)
        warped0 = self._warp_with_flow(img0_bgr, flow01, ratio)
        warped1 = self._warp_with_flow(img1_bgr, flow10, 1.0 - ratio)
        return cv2.addWeighted(warped0, 1.0 - ratio, warped1, ratio, 0)

    def _run_backend(
        self,
        img0_bgr: np.ndarray,
        img1_bgr: np.ndarray,
        ratio: float,
        backend: Callable[[np.ndarray, np.ndarray, float], np.ndarray],
    ) -> tuple[np.ndarray, dict]:
        height, width = img0_bgr.shape[:2]
        if height > TILE_THRESHOLD_PX or width > TILE_THRESHOLD_PX:
            return self._interpolate_tiled(img0_bgr, img1_bgr, ratio, backend)

        return backend(img0_bgr, img1_bgr, ratio), {
            "used": False,
            "tileSize": None,
            "overlapPx": 0,
            "tileCount": 1,
        }

    @staticmethod
    def _load_mask(path: Optional[str], shape: tuple[int, int]) -> np.ndarray:
        if not path or not os.path.exists(path):
            return np.zeros(shape, dtype=bool)

        mask = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            return np.zeros(shape, dtype=bool)
        if mask.shape[:2] != shape:
            mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
        return mask >= 127

    def _build_mask_bundle(
        self,
        mask_context: Optional[dict],
        shape: tuple[int, int],
        alpha0: Optional[np.ndarray],
        alpha1: Optional[np.ndarray],
    ) -> dict:
        derived0 = alpha0 is not None and np.any(alpha0 < 64)
        derived1 = alpha1 is not None and np.any(alpha1 < 64)
        frame0 = (mask_context or {}).get("frame0") or {}
        frame1 = (mask_context or {}).get("frame1") or {}

        return {
            "frame0": {
                "nodata": self._load_mask(frame0.get("nodataMaskPath"), shape)
                if frame0.get("nodataMaskPath")
                else ((alpha0 < 64) if alpha0 is not None else np.zeros(shape, dtype=bool)),
                "limb": self._load_mask(frame0.get("limbMaskPath"), shape),
                "terminator": self._load_mask(frame0.get("terminatorMaskPath"), shape),
                "derivedFromAlpha": bool(derived0),
            },
            "frame1": {
                "nodata": self._load_mask(frame1.get("nodataMaskPath"), shape)
                if frame1.get("nodataMaskPath")
                else ((alpha1 < 64) if alpha1 is not None else np.zeros(shape, dtype=bool)),
                "limb": self._load_mask(frame1.get("limbMaskPath"), shape),
                "terminator": self._load_mask(frame1.get("terminatorMaskPath"), shape),
                "derivedFromAlpha": bool(derived1),
            },
        }

    @staticmethod
    def _mask_summary(mask: np.ndarray) -> dict:
        return {
            "coveragePct": round(float(mask.mean() * 100.0), 4),
            "pixelCount": int(mask.sum()),
        }

    def _summarize_input_masks(self, mask_bundle: dict) -> dict:
        return {
            "frame0": {
                "nodata": self._mask_summary(mask_bundle["frame0"]["nodata"]),
                "limb": self._mask_summary(mask_bundle["frame0"]["limb"]),
                "terminator": self._mask_summary(mask_bundle["frame0"]["terminator"]),
            },
            "frame1": {
                "nodata": self._mask_summary(mask_bundle["frame1"]["nodata"]),
                "limb": self._mask_summary(mask_bundle["frame1"]["limb"]),
                "terminator": self._mask_summary(mask_bundle["frame1"]["terminator"]),
            },
        }

    def _build_output_masks(self, mask_bundle: dict, result_alpha: Optional[np.ndarray]) -> dict:
        nodata_mask = (
            result_alpha < 64
            if result_alpha is not None
            else (mask_bundle["frame0"]["nodata"] & mask_bundle["frame1"]["nodata"])
        )
        limb_mask = mask_bundle["frame0"]["limb"] | mask_bundle["frame1"]["limb"]
        terminator_mask = (
            mask_bundle["frame0"]["terminator"] | mask_bundle["frame1"]["terminator"]
        )
        return {
            "nodata": nodata_mask.astype(bool),
            "limb": limb_mask.astype(bool),
            "terminator": terminator_mask.astype(bool),
        }

    def _persist_output_masks(self, output_path: str, masks: dict) -> dict:
        os.makedirs(INTERPOLATED_MASKS_DIR, exist_ok=True)
        stem = os.path.splitext(os.path.basename(output_path))[0]
        persisted = {}

        for name, mask in masks.items():
            mask_path = os.path.join(INTERPOLATED_MASKS_DIR, f"{stem}_{name}.png")
            self._write_output_image_atomic(mask_path, mask.astype(np.uint8) * 255)
            persisted[name] = {
                "path": mask_path,
                "url": _as_data_url(mask_path),
                "coveragePct": round(float(mask.mean() * 100.0), 4),
            }

        return persisted

    def _compute_motion_summary(
        self,
        img0_bgr: np.ndarray,
        img1_bgr: np.ndarray,
        valid_mask: np.ndarray,
    ) -> dict:
        flow = self._compute_farneback_flow(img0_bgr, img1_bgr)
        magnitude, angle = cv2.cartToPolar(flow[:, :, 0], flow[:, :, 1], angleInDegrees=True)
        sampled = magnitude[valid_mask] if np.any(valid_mask) else magnitude.reshape(-1)
        if sampled.size == 0:
            sampled = magnitude.reshape(-1)

        return {
            "available": True,
            "method": "farneback_dense_flow",
            "meanMagnitudePx": round(float(sampled.mean()), 6),
            "maxMagnitudePx": round(float(sampled.max()), 6),
            "p95MagnitudePx": round(float(np.percentile(sampled, 95)), 6),
            "meanDirectionDeg": round(float(angle[valid_mask].mean()) if np.any(valid_mask) else float(angle.mean()), 6),
            "validCoveragePct": round(float(valid_mask.mean() * 100.0), 4),
        }

    @staticmethod
    def _write_output_image_atomic(path: str, image: np.ndarray) -> None:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        root, ext = os.path.splitext(path)
        temp_path = f"{root}.tmp{ext}"
        if not cv2.imwrite(temp_path, image):
            raise RuntimeError(f"Failed to write image to {temp_path}")
        os.replace(temp_path, path)

    def interpolate(
        self,
        img0_path: str,
        img1_path: str,
        output_path: str,
        ratio: float = 0.5,
        *,
        mask_context: Optional[dict] = None,
    ) -> bool:
        if not os.path.exists(img0_path) or not os.path.exists(img1_path):
            raise FileNotFoundError(f"Missing images: {img0_path} or {img1_path}")

        self._assert_startup_ready()

        started_at = _utc_now()
        started_perf = time.perf_counter()
        errors: list[str] = []
        fallback_used = False
        fallback_reason = None
        execution_mode = "rife"
        benchmark_gate = _load_phase0_gate()

        img0_raw = self._read_image(img0_path)
        img1_raw = self._read_image(img1_path)

        height, width = img0_raw.shape[:2]
        if img1_raw.shape[:2] != (height, width):
            img1_raw = cv2.resize(img1_raw, (width, height), interpolation=cv2.INTER_LINEAR)

        img0_bgr, alpha0 = self._separate_alpha(img0_raw)
        img1_bgr, alpha1 = self._separate_alpha(img1_raw)
        valid0 = self._alpha_to_valid_mask(alpha0, (height, width))
        valid1 = self._alpha_to_valid_mask(alpha1, (height, width))

        img0_for_model = self._prefill_missing_regions(img0_bgr, valid0, img1_bgr, valid1)
        img1_for_model = self._prefill_missing_regions(img1_bgr, valid1, img0_bgr, valid0)

        mask_bundle = self._build_mask_bundle(mask_context, (height, width), alpha0, alpha1)
        mask_summary = self._summarize_input_masks(mask_bundle)
        motion_info = self._compute_motion_summary(img0_for_model, img1_for_model, valid0 & valid1)

        try:
            if benchmark_gate and not benchmark_gate.get("productionAllowed", False):
                fallback_used = True
                fallback_reason = "phase0_gate_failed"
                execution_mode = FALLBACK_METHOD
                result_bgr, tile_info = self._run_backend(
                    img0_for_model,
                    img1_for_model,
                    ratio,
                    self._optical_flow_interpolate_core,
                )
            else:
                result_bgr, tile_info = self._run_backend(
                    img0_for_model,
                    img1_for_model,
                    ratio,
                    self._rife_interpolate_core,
                )
        except Exception as exc:
            errors.append(str(exc))
            fallback_used = True
            fallback_reason = "model_runtime_error"
            execution_mode = FALLBACK_METHOD
            logger.exception("Neural interpolation failed; switching to optical-flow fallback")
            result_bgr, tile_info = self._run_backend(
                img0_for_model,
                img1_for_model,
                ratio,
                self._optical_flow_interpolate_core,
            )

        result_bgr = self._compose_full_frame(result_bgr, img0_bgr, img1_bgr, valid0, valid1)

        if alpha0 is not None or alpha1 is not None:
            a0 = alpha0 if alpha0 is not None else np.full((height, width), 255, dtype=np.uint8)
            a1 = alpha1 if alpha1 is not None else np.full((height, width), 255, dtype=np.uint8)
            result_alpha = np.maximum(a0, a1)
        else:
            result_alpha = None

        result = self._merge_alpha(result_bgr, result_alpha)
        output_masks = self._build_output_masks(mask_bundle, result_alpha)
        output_mask_artifacts = self._persist_output_masks(output_path, output_masks)
        self._write_output_image_atomic(output_path, result)

        duration_ms = round((time.perf_counter() - started_perf) * 1000.0, 2)
        suspicious_runtime = execution_mode == "rife" and duration_ms < SUSPICIOUS_RUNTIME_MS
        warnings = []
        if suspicious_runtime:
            warnings.append(
                f"Neural inference completed in {duration_ms:.2f} ms, below the suspicious threshold of {SUSPICIOUS_RUNTIME_MS:.2f} ms."
            )

        self.last_run = {
            "startedAt": started_at,
            "completedAt": _utc_now(),
            "durationMs": duration_ms,
            "input0": img0_path,
            "input1": img1_path,
            "output": output_path,
            "ratio": ratio,
            "executionMode": execution_mode,
            "device": str(self.device) if self.device is not None else None,
            "outputShape": list(result.shape),
            "opaqueCoveragePct": round(
                float(((result_alpha >= 64).mean() if result_alpha is not None else 1.0) * 100.0),
                4,
            ),
            "usedModelWeights": execution_mode == "rife",
            "fallbackUsed": fallback_used,
            "fallbackMethod": FALLBACK_METHOD if fallback_used else None,
            "fallbackReason": fallback_reason,
            "tileInfo": tile_info,
            "maskSummary": mask_summary,
            "outputMasks": output_mask_artifacts,
            "motionInfo": motion_info,
            "performanceExplanation": _performance_explanation(
                str(self.device) if self.device is not None else None,
                execution_mode,
            ),
            "suspiciousRuntime": suspicious_runtime,
            "warnings": warnings,
            "errors": errors,
            "model": self._model_snapshot(),
            "benchmarkGate": benchmark_gate,
        }

        logger.info(
            "Interpolation completed | model=%s | version=%s | mode=%s | fallback=%s | duration_ms=%.2f | output=%s",
            MODEL_NAME,
            MODEL_VERSION,
            execution_mode,
            fallback_used,
            duration_ms,
            output_path,
        )
        return True


interpolator = RIFEInterpolator()


def _remove_path(path: Optional[str]) -> None:
    if path and os.path.exists(path):
        os.remove(path)


def _context_from_run(run: dict) -> dict:
    output_masks = run.get("outputMasks") or {}
    return {
        "nodataMaskPath": ((output_masks.get("nodata") or {}).get("path")),
        "limbMaskPath": ((output_masks.get("limb") or {}).get("path")),
        "terminatorMaskPath": ((output_masks.get("terminator") or {}).get("path")),
    }


def generate_intermediate_frames(
    frame0_path: str,
    frame1_path: str,
    output_dir: str,
    num_frames: int = 1,
    file_prefix: str = "interp",
    *,
    frame0_context: Optional[dict] = None,
    frame1_context: Optional[dict] = None,
) -> list[dict]:
    """
    Generate intermediate frames via recursive midpoint subdivision.
    """
    os.makedirs(output_dir, exist_ok=True)
    if num_frames <= 0:
        return []

    # Rule OI-04 — Gap Size Hard Limit (30 min)
    left_ts = (frame0_context or {}).get("timestamp")
    right_ts = (frame1_context or {}).get("timestamp")
    if left_ts and right_ts:
        from app.services.confidence import gap_minutes_between
        gap = gap_minutes_between(left_ts, right_ts)
        if gap is not None and gap > 30.0:
            logger.warning("Aborting interpolation: temporal gap %.1f min exceeds 30m limit (Rule OI-04)", gap)
            return []

    generated_records: list[dict] = []
    duration_ms: list[float] = []
    batch_started_at = _utc_now()
    batch_started_perf = time.perf_counter()
    job_id = f"{file_prefix}_{uuid.uuid4().hex[:10]}"
    batch_errors: list[str] = []
    max_depth = 0

    def recurse(
        left_path: str,
        right_path: str,
        left_ratio: float,
        right_ratio: float,
        remaining_frames: int,
        depth: int,
        left_context: Optional[dict],
        right_context: Optional[dict],
    ) -> None:
        nonlocal max_depth
        if remaining_frames <= 0:
            return

        max_depth = max(max_depth, depth)
        mid_ratio = (left_ratio + right_ratio) / 2.0
        filename = f"{file_prefix}_{int(round(mid_ratio * 100)):02d}.png"
        out_path = os.path.join(output_dir, filename)

        interpolator.interpolate(
            left_path,
            right_path,
            out_path,
            0.5,
            mask_context={"frame0": left_context or {}, "frame1": right_context or {}},
        )

        run = copy.deepcopy(interpolator.last_run or {})
        record = {
            "path": out_path,
            "ratio": round(mid_ratio, 4),
            "recursionDepth": depth,
            "interpolation": run,
            "maskInfo": run.get("outputMasks") or {},
            "motion": run.get("motionInfo") or {},
        }
        generated_records.append(record)
        duration_ms.append(run.get("durationMs", 0.0))
        batch_errors.extend(run.get("errors") or [])

        generated_context = _context_from_run(run)
        child_frames = remaining_frames - 1
        left_count = int(math.ceil(child_frames / 2.0))
        right_count = child_frames - left_count

        recurse(left_path, out_path, left_ratio, mid_ratio, left_count, depth + 1, left_context, generated_context)
        recurse(out_path, right_path, mid_ratio, right_ratio, right_count, depth + 1, generated_context, right_context)

    try:
        recurse(frame0_path, frame1_path, 0.0, 1.0, num_frames, 1, frame0_context, frame1_context)
    except Exception:
        for record in generated_records:
            _remove_path(record.get("path"))
            mask_info = record.get("maskInfo") or {}
            for payload in mask_info.values():
                _remove_path((payload or {}).get("path"))
        raise

    generated_records.sort(key=lambda item: item["ratio"])
    output_frames = [record["path"] for record in generated_records]
    fallback_used = any(record["interpolation"].get("fallbackUsed") for record in generated_records)
    suspicious_frames = [
        os.path.basename(record["path"])
        for record in generated_records
        if record["interpolation"].get("suspiciousRuntime")
    ]
    motion_samples = [
        record["motion"]
        for record in generated_records
        if record.get("motion", {}).get("available")
    ]

    motion_summary = None
    if motion_samples:
        motion_summary = {
            "available": True,
            "method": "farneback_dense_flow",
            "meanMagnitudePx": round(float(np.mean([item["meanMagnitudePx"] for item in motion_samples])), 6),
            "maxMagnitudePx": round(float(np.max([item["maxMagnitudePx"] for item in motion_samples])), 6),
            "p95MagnitudePx": round(float(np.mean([item["p95MagnitudePx"] for item in motion_samples])), 6),
        }

    total_inference_time_ms = round(float(sum(duration_ms)), 2)
    batch_duration_ms = round((time.perf_counter() - batch_started_perf) * 1000.0, 2)
    audit_job = {
        "job_id": job_id,
        "generated_at": _utc_now(),
        "input_frames": [frame0_path, frame1_path],
        "output_frames": output_frames,
        "model_used": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "benchmark_compliant": BENCHMARK_COMPLIANT,
        "fallback": fallback_used,
        "fallback_method": FALLBACK_METHOD if fallback_used else None,
        "inference_time_ms": total_inference_time_ms,
        "wall_time_ms": batch_duration_ms,
        "time_per_frame_ms": duration_ms,
        "recursion_depth": max_depth,
        "device": str(interpolator.device) if interpolator.device is not None else None,
        "errors": batch_errors,
        "tile_used": any(record["interpolation"].get("tileInfo", {}).get("used") for record in generated_records),
        "motion": motion_summary,
        "suspicious_frames": suspicious_frames,
        "model": interpolator._model_snapshot(),
    }
    audit_log_path = append_interpolation_log(audit_job)

    interpolator.last_batch = {
        "jobId": job_id,
        "startedAt": batch_started_at,
        "completedAt": _utc_now(),
        "input0": frame0_path,
        "input1": frame1_path,
        "requestedFrames": num_frames,
        "generatedFrames": len(generated_records),
        "outputDir": output_dir,
        "filePrefix": file_prefix,
        "strategy": "recursive_bisection",
        "ratios": [record["ratio"] for record in generated_records],
        "frameDurationsMs": duration_ms,
        "totalInferenceTimeMs": total_inference_time_ms,
        "wallTimeMs": batch_duration_ms,
        "executionMode": "rife" if not fallback_used else FALLBACK_METHOD,
        "fallbackUsed": fallback_used,
        "fallbackMethod": FALLBACK_METHOD if fallback_used else None,
        "outputs": output_frames,
        "recursionDepth": max_depth,
        "motionInfo": motion_summary,
        "errors": batch_errors,
        "suspiciousFrames": suspicious_frames,
        "auditLogPath": audit_log_path,
        "auditLogUrl": _as_data_url(audit_log_path),
        "model": interpolator._model_snapshot(),
        "performanceExplanation": _performance_explanation(
            str(interpolator.device) if interpolator.device is not None else None,
            FALLBACK_METHOD if fallback_used else "rife",
        ),
    }

    logger.info(
        "Interpolation batch completed | job_id=%s | generated_frames=%d | fallback=%s | total_inference_ms=%.2f",
        job_id,
        len(generated_records),
        fallback_used,
        total_inference_time_ms,
    )
    return generated_records
