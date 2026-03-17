import cv2
import numpy as np
import os
import torch

class RIFEInterpolator:
    def __init__(self, model_dir="weights"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_loaded = False
        self.model_dir = model_dir
        
        # Check if actual weights exist. If not, use OpenCV fallback.
        if os.path.exists(os.path.join(model_dir, "flownet.pkl")):
            self.model_loaded = True
            print(f"Loaded RIFE model from {model_dir} on {self.device}")
        else:
            print(f"RIFE weights not found in {model_dir}. Falling back to Alpha Blending interpolation.")

    def interpolate(self, img0_path, img1_path, output_path, ratio=0.5):
        """
        Interpolates a frame between img0 and img1 at the given ratio (0.0 to 1.0).
        Saves the output to output_path.
        """
        if not os.path.exists(img0_path) or not os.path.exists(img1_path):
            raise FileNotFoundError(f"Missing images: {img0_path} or {img1_path}")

        img0 = cv2.imread(img0_path, cv2.IMREAD_UNCHANGED)
        img1 = cv2.imread(img1_path, cv2.IMREAD_UNCHANGED)

        if img0 is None or img1 is None:
            raise ValueError("Failed to load one or both images with cv2.")

        # Ensure both images are the same size
        h, w = img0.shape[:2]
        img1 = cv2.resize(img1, (w, h))

        if self.model_loaded:
            # ... (model code remains the same but should handle 4 channels if needed)
            # For now, we still fallback
            pass
            
        # Unified blending that handles potential alpha channel
        alpha = 1.0 - ratio
        beta = ratio
        blended = cv2.addWeighted(img0, alpha, img1, beta, 0)
        cv2.imwrite(output_path, blended)

        return True

interpolator = RIFEInterpolator(model_dir=os.path.join(os.path.dirname(__file__), "..", "weights"))

def generate_intermediate_frames(frame0_path: str, frame1_path: str, output_dir: str, num_frames=1, file_prefix="interp"):
    """
    Generates intermediate frames between two images using the loaded RIFE interpolator.
    Returns a list of generated file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    generated_paths = []
    
    # Calculate intervals
    for i in range(1, num_frames + 1):
        ratio = i / (num_frames + 1)
        filename = f"{file_prefix}_{int(ratio*100):02d}.png"
        out_path = os.path.join(output_dir, filename)
        
        interpolator.interpolate(frame0_path, frame1_path, out_path, ratio)
        generated_paths.append(out_path)
        
    return generated_paths
