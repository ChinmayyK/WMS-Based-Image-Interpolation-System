import os
import pytest
import numpy as np
import cv2
from app.services.geospatial import preprocess_image, save_preprocessed_image, align_crs, PreprocessingError

@pytest.fixture
def dummy_image(tmpdir):
    path = os.path.join(tmpdir, "test_in.png")
    # Create a dummy green image
    img = np.zeros((256, 256, 3), dtype=np.uint8)
    img[:, :] = (0, 255, 0)
    cv2.imwrite(path, img)
    return path

def test_preprocess_image(dummy_image):
    processed = preprocess_image(dummy_image, target_size=(512, 512))
    
    assert processed.shape == (512, 512, 3)
    assert processed.dtype == np.float32
    # Check max green
    assert np.allclose(processed[0, 0], [0.0, 1.0, 0.0])

def test_preprocess_image_not_found():
    with pytest.raises(PreprocessingError):
        preprocess_image("non_existent.png")

def test_save_preprocessed_image(tmpdir):
    out_path = os.path.join(tmpdir, "test_out.png")
    # Create a red float array
    arr = np.zeros((128, 128, 3), dtype=np.float32)
    arr[:, :] = [0.0, 0.0, 1.0] # BGR format: Red
    
    save_preprocessed_image(arr, out_path)
    
    assert os.path.exists(out_path)
    saved = cv2.imread(out_path)
    assert saved.shape == (128, 128, 3)
    assert np.array_equal(saved[0, 0], [0, 0, 255])

def test_align_crs():
    assert align_crs("EPSG:3857") is True
    
    with pytest.raises(PreprocessingError):
        align_crs("EPSG:4326")
