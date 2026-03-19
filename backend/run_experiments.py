"""
Experiment script to compare RIFE interpolation vs Alpha Blending baseline.
Measures PSNR and SSIM against a ground-truth intermediate frame.

Usage:
    cd backend
    python run_experiments.py
"""
import os
import cv2
import numpy as np
from skimage.metrics import peak_signal_noise_ratio as psnr
from skimage.metrics import structural_similarity as ssim


def alpha_blend(img1_path, img2_path, ratio=0.5):
    """Simple alpha-blending baseline."""
    img1 = cv2.imread(img1_path)
    img2 = cv2.imread(img2_path)
    if img1 is None or img2 is None:
        raise ValueError("Could not read images")

    img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
    alpha = 1.0 - ratio
    beta = ratio
    blended = cv2.addWeighted(img1, alpha, img2, beta, 0)
    return blended


def compute_metrics(target_img_path, generated_img):
    """Compute PSNR and SSIM between a ground-truth image and a generated image."""
    target = cv2.imread(target_img_path)
    if target is None:
        raise ValueError(f"Could not read target {target_img_path}")

    target = cv2.resize(target, (generated_img.shape[1], generated_img.shape[0]))

    # Calculate PSNR
    calc_psnr = psnr(target, generated_img)

    # Calculate SSIM
    min_dim = min(target.shape[0], target.shape[1])
    win_size = min(7, min_dim)
    if win_size % 2 == 0:
        win_size -= 1

    calc_ssim = ssim(target, generated_img, channel_axis=2, data_range=255, win_size=win_size)

    return calc_psnr, calc_ssim


def run_experiment(frame1, frame3, target_frame2, output_dir_base="results"):
    print(f"\n--- Running Experiment: {os.path.basename(frame1)} -> {os.path.basename(frame3)} "
          f"(Target: {os.path.basename(target_frame2)}) ---")

    os.makedirs(output_dir_base, exist_ok=True)

    # 1. Generate via Alpha Blending (Baseline)
    print("  [1/3] Running Alpha Blending baseline...")
    baseline_img = alpha_blend(frame1, frame3, ratio=0.5)
    baseline_path = os.path.join(output_dir_base, "alpha_blend_result.png")
    cv2.imwrite(baseline_path, baseline_img)

    # 2. Generate via RIFE
    print("  [2/3] Running RIFE interpolation...")
    rife_path = os.path.join(output_dir_base, "rife_result.png")
    try:
        from app.services.interpolation import interpolator
        if interpolator.model_loaded:
            interpolator.interpolate(frame1, frame3, rife_path, ratio=0.5)
            rife_img = cv2.imread(rife_path)
            rife_label = "RIFE (Neural Net)"
        else:
            print("  [!] RIFE weights not loaded. Using alpha blend as comparison.")
            rife_img = baseline_img.copy()
            cv2.imwrite(rife_path, rife_img)
            rife_label = "RIFE (Fallback=AlphaBlend)"
    except Exception as e:
        print(f"  [!] RIFE interpolation failed: {e}")
        rife_img = baseline_img.copy()
        cv2.imwrite(rife_path, rife_img)
        rife_label = "RIFE (Error=AlphaBlend)"

    # 3. Compute Metrics
    print("  [3/3] Computing metrics against ground truth...")
    base_psnr, base_ssim = compute_metrics(target_frame2, baseline_img)
    rife_psnr, rife_ssim = compute_metrics(target_frame2, rife_img)

    print(f"\n  Results:")
    print(f"  | {'Method':<30} | {'PSNR':>8} | {'SSIM':>8} |")
    print(f"  |{'-'*32}|{'-'*10}|{'-'*10}|")
    print(f"  | {'Alpha Blending':<30} | {base_psnr:>8.2f} | {base_ssim:>8.4f} |")
    print(f"  | {rife_label:<30} | {rife_psnr:>8.2f} | {rife_ssim:>8.4f} |")

    # Write to a markdown report
    report_path = os.path.join(output_dir_base, "experiment_report.md")
    with open(report_path, "w") as f:
        f.write(f"# Experiment Results\n\n")
        f.write(f"**Input Frames:** `{os.path.basename(frame1)}` and `{os.path.basename(frame3)}`\n")
        f.write(f"**Ground Truth:** `{os.path.basename(target_frame2)}`\n\n")
        f.write(f"| Method | PSNR | SSIM |\n")
        f.write(f"|---|---|---|\n")
        f.write(f"| Alpha Blending | {base_psnr:.2f} | {base_ssim:.4f} |\n")
        f.write(f"| {rife_label} | {rife_psnr:.2f} | {rife_ssim:.4f} |\n")

    print(f"\n  Experiment completed. Report saved to {report_path}")
    return report_path


if __name__ == "__main__":
    # Create synthetic test frames with a moving circle
    base_dir = os.path.dirname(os.path.abspath(__file__))
    test_data_dir = os.path.join(base_dir, "data", "experiment_data")
    os.makedirs(test_data_dir, exist_ok=True)

    f1 = os.path.join(test_data_dir, "10_00.png")
    f2 = os.path.join(test_data_dir, "10_15.png")  # Ground truth (midpoint)
    f3 = os.path.join(test_data_dir, "10_30.png")

    # Generate moving shapes to test interpolation quality
    img1 = np.zeros((512, 512, 3), np.uint8)
    cv2.circle(img1, (100, 256), 50, (255, 255, 255), -1)

    img2 = np.zeros((512, 512, 3), np.uint8)
    cv2.circle(img2, (256, 256), 50, (255, 255, 255), -1)  # Middle state

    img3 = np.zeros((512, 512, 3), np.uint8)
    cv2.circle(img3, (412, 256), 50, (255, 255, 255), -1)

    cv2.imwrite(f1, img1)
    cv2.imwrite(f2, img2)
    cv2.imwrite(f3, img3)

    print("=" * 60)
    print("  WMS Image Interpolation – RIFE vs Alpha Blend Experiment")
    print("=" * 60)

    run_experiment(f1, f3, f2, os.path.join(base_dir, "results", "case1"))

    print("\n" + "=" * 60)
    print("  All experiments complete.")
    print("=" * 60)
