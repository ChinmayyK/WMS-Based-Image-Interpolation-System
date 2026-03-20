"""Tests for the RIFE-based interpolation service."""
import os
import pytest
import numpy as np
import cv2


@pytest.fixture
def test_frames(tmpdir):
    """Create two synthetic test frames."""
    f1 = os.path.join(tmpdir, "frame1.png")
    f2 = os.path.join(tmpdir, "frame2.png")

    # Create two different colored images
    img1 = np.zeros((128, 128, 3), dtype=np.uint8)
    img1[:, :] = (255, 0, 0)  # Blue in BGR
    cv2.circle(img1, (32, 64), 20, (255, 255, 255), -1)

    img2 = np.zeros((128, 128, 3), dtype=np.uint8)
    img2[:, :] = (0, 0, 255)  # Red in BGR
    cv2.circle(img2, (96, 64), 20, (255, 255, 255), -1)

    cv2.imwrite(f1, img1)
    cv2.imwrite(f2, img2)

    return f1, f2, str(tmpdir)


def test_interpolator_initializes():
    """Test that the RIFEInterpolator initializes without crashing."""
    from app.services.interpolation import RIFEInterpolator
    interp = RIFEInterpolator(weights_dir="/nonexistent/path")
    assert not interp.model_loaded  # Should gracefully fall back


def test_interpolator_singleton():
    """Test that the module-level singleton is available."""
    from app.services.interpolation import interpolator
    assert interpolator is not None


def test_interpolate_creates_output(test_frames):
    """Test that interpolation produces a valid output file."""
    from app.services.interpolation import interpolator

    f1, f2, tmpdir = test_frames
    out = os.path.join(tmpdir, "output.png")
    result = interpolator.interpolate(f1, f2, out, ratio=0.5)
    
    assert result is True
    assert os.path.exists(out)
    
    img = cv2.imread(out)
    assert img is not None
    assert img.shape == (128, 128, 3)


def test_interpolate_dimensions_match(test_frames):
    """Test that output dimensions match input dimensions."""
    from app.services.interpolation import interpolator

    f1, f2, tmpdir = test_frames
    out = os.path.join(tmpdir, "output.png")
    interpolator.interpolate(f1, f2, out, ratio=0.5)
    
    img_in = cv2.imread(f1)
    img_out = cv2.imread(out)
    assert img_in.shape == img_out.shape


def test_generate_intermediate_frames(test_frames):
    """Test that recursive bisection produces the requested number of frames."""
    from app.services.interpolation import generate_intermediate_frames, interpolator

    f1, f2, tmpdir = test_frames
    out_dir = os.path.join(tmpdir, "interp_out")
    
    records = generate_intermediate_frames(f1, f2, out_dir, num_frames=3, file_prefix="test")
    
    assert len(records) == 3
    assert [record["ratio"] for record in records] == [0.25, 0.5, 0.75]
    assert interpolator.last_batch["strategy"] == "recursive_bisection"
    for record in records:
        assert os.path.exists(record["path"])
        img = cv2.imread(record["path"])
        assert img is not None


def test_interpolate_missing_file():
    """Test error handling for missing input files."""
    from app.services.interpolation import interpolator

    with pytest.raises(FileNotFoundError):
        interpolator.interpolate("nonexistent1.png", "nonexistent2.png", "/tmp/out.png")


def test_interpolate_with_alpha(tmpdir):
    """Test interpolation with RGBA images (satellite imagery with transparency)."""
    from app.services.interpolation import interpolator

    f1 = os.path.join(tmpdir, "alpha1.png")
    f2 = os.path.join(tmpdir, "alpha2.png")
    out = os.path.join(tmpdir, "alpha_out.png")

    # Create RGBA images
    img1 = np.zeros((128, 128, 4), dtype=np.uint8)
    img1[:, :, :3] = (100, 150, 200)
    img1[:, :, 3] = 255  # Full opacity
    img1[50:80, 50:80, 3] = 0  # Transparent patch

    img2 = np.zeros((128, 128, 4), dtype=np.uint8)
    img2[:, :, :3] = (200, 100, 50)
    img2[:, :, 3] = 255

    cv2.imwrite(f1, img1)
    cv2.imwrite(f2, img2)

    result = interpolator.interpolate(f1, f2, out, ratio=0.5)
    assert result is True

    img_out = cv2.imread(out, cv2.IMREAD_UNCHANGED)
    assert img_out is not None
    assert img_out.shape[2] == 4  # Should preserve alpha channel
    # Complementary coverage should remain opaque in the stitched output.
    assert np.all(img_out[:, :, 3] == 255)


def test_interpolator_exposes_runtime_diagnostics():
    """The service should report concrete model/fallback diagnostics."""
    from app.services.interpolation import interpolator

    diagnostics = interpolator.get_diagnostics()

    assert diagnostics["model"]["name"] == "RIFE HDv3"
    assert diagnostics["model"]["framework"].startswith("PyTorch")
    assert diagnostics["execution"]["fallbackBehavior"] == "OpenCV alpha blend when weights are missing or model load fails"
