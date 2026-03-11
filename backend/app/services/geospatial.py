import os
import cv2
import numpy as np

class PreprocessingError(Exception):
    pass

def preprocess_image(image_path: str, target_size=(512, 512)) -> np.ndarray:
    """
    Reads an image from disk, resizes it to target_size, and normalizes it.
    Returns the normalized numpy array (float32, 0.0 to 1.0)
    """
    if not os.path.exists(image_path):
        raise PreprocessingError(f"Image not found at path: {image_path}")
        
    img = cv2.imread(image_path, cv2.IMREAD_COLOR)
    
    if img is None:
        raise PreprocessingError(f"Failed to read image or invalid format: {image_path}")
        
    # Resize spatial resolution
    resized = cv2.resize(img, target_size, interpolation=cv2.INTER_LANCZOS4)
    
    # Normalize pixel values
    normalized = resized.astype(np.float32) / 255.0
    
    # Normally we might save this or pass it in memory.
    # The return format is an aligned, normalized array ready for AI pipeline.
    return normalized

def save_preprocessed_image(img_array: np.ndarray, output_path: str):
    """
    Utility to save the normalized array back to disk for manual inspection/caching.
    Expects float32 [0..1] array.
    """
    # Scale back to 0-255 uint8 for saving as PNG
    to_save = (img_array * 255.0).clip(0, 255).astype(np.uint8)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv2.imwrite(output_path, to_save)

def align_crs(source_crs: str, target_crs: str="EPSG:4326"):
    """
    In a full GIS context, this would use rasterio.warp to reproject.
    Since we are working with pre-projected WMS PNGs returned in EPSG:4326, 
    this just validates the assumption.
    """
    if source_crs != target_crs:
        # In actual implementation: use gdal/rasterio 
        raise PreprocessingError(f"CRS alignment needed but only {target_crs} is supported natively with current PNG approach.")
    return True
