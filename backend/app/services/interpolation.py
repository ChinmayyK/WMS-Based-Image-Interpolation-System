"""
Frame interpolation service using the RIFE (Real-Time Intermediate Flow Estimation) model.
Falls back to alpha blending if RIFE weights are not available.
"""
import cv2
import numpy as np
import os
import logging
import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weight path resolution
# ---------------------------------------------------------------------------
WEIGHTS_DIR = os.path.join(os.path.dirname(__file__), "..", "rife_model", "weights")
WEIGHTS_DIR = os.path.abspath(WEIGHTS_DIR)


class RIFEInterpolator:
    """Wraps the RIFE neural network for single-pair frame interpolation."""

    def __init__(self, weights_dir: str = WEIGHTS_DIR):
        self.weights_dir = weights_dir
        self.model = None
        self.model_loaded = False
        self.device = None

        weight_path = os.path.join(weights_dir, "flownet.pkl")
        if os.path.exists(weight_path):
            try:
                from app.rife_model.RIFE import Model as RIFEModel
                self.model = RIFEModel()
                self.model.load_model(weights_dir)
                self.device = self.model._device
                self.model_loaded = True
                logger.info(f"RIFE model loaded from {weights_dir} on {self.device}")
            except Exception as e:
                logger.error(f"Failed to load RIFE model: {e}")
                self.model_loaded = False
        else:
            logger.warning(
                f"RIFE weights not found at {weight_path}. "
                "Falling back to alpha blending. "
                "Run 'python download_weights.py' to download weights."
            )

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
        2. After interpolation, pixels that were transparent in EITHER source
           are set transparent in the output (NoData union mask).
        """
        if not os.path.exists(img0_path) or not os.path.exists(img1_path):
            raise FileNotFoundError(f"Missing images: {img0_path} or {img1_path}")

        img0_raw = self._read_image(img0_path)
        img1_raw = self._read_image(img1_path)

        # Ensure both images same size
        h, w = img0_raw.shape[:2]
        img1_raw = cv2.resize(img1_raw, (w, h))

        # Separate alpha channels
        img0_bgr, alpha0 = self._separate_alpha(img0_raw)
        img1_bgr, alpha1 = self._separate_alpha(img1_raw)

        # ── Fill NoData regions with neutral gray before RIFE ──────────────
        # Transparent pixels would otherwise appear as pure black to the network,
        # causing dark gradient artifacts near swath boundaries.
        NODATA_FILL = 128  # neutral gray — will be masked out afterwards
        if alpha0 is not None:
            nodata0 = alpha0 < 64                         # True where transparent
            img0_bgr = img0_bgr.copy()
            img0_bgr[nodata0] = NODATA_FILL
        if alpha1 is not None:
            nodata1 = alpha1 < 64
            img1_bgr = img1_bgr.copy()
            img1_bgr[nodata1] = NODATA_FILL

        # ── Run RIFE (or alpha-blend fallback) on the clean BGRs ──────────
        if self.model_loaded and self.model is not None:
            result_bgr = self._rife_interpolate(img0_bgr, img1_bgr, ratio)
        else:
            result_bgr = self._alpha_blend(img0_bgr, img1_bgr, ratio)

        # ── Build output alpha: transparent where EITHER source was transparent ─
        # This removes the NoData swath gap from the interpolated frame too.
        if alpha0 is not None or alpha1 is not None:
            a0 = alpha0 if alpha0 is not None else np.full((h, w), 255, dtype=np.uint8)
            a1 = alpha1 if alpha1 is not None else np.full((h, w), 255, dtype=np.uint8)
            # Union of transparent regions: pixel is transparent if EITHER source was
            result_alpha = np.minimum(a0, a1)
        else:
            result_alpha = None

        result = self._merge_alpha(result_bgr, result_alpha)

        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
        cv2.imwrite(output_path, result)
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
    Generate intermediate frames between two images using RIFE.
    Returns a list of generated file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    generated_paths = []

    for i in range(1, num_frames + 1):
        ratio = i / (num_frames + 1)
        filename = f"{file_prefix}_{int(ratio * 100):02d}.png"
        out_path = os.path.join(output_dir, filename)

        logger.info(f"Generating frame {i}/{num_frames} at ratio {ratio:.3f} → {filename}")
        interpolator.interpolate(frame0_path, frame1_path, out_path, ratio)
        generated_paths.append(out_path)

    return generated_paths
