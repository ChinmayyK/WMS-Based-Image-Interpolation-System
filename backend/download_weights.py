#!/usr/bin/env python3
"""
Downloads pretrained RIFE model weights from the official Google Drive link.
Weights are stored at backend/app/rife_model/weights/flownet.pkl

Usage:
    cd backend
    python download_weights.py
"""
import os
import sys


def download_weights():
    weights_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "app", "rife_model", "weights"
    )
    os.makedirs(weights_dir, exist_ok=True)
    weights_path = os.path.join(weights_dir, "flownet.pkl")

    if os.path.exists(weights_path):
        size_mb = os.path.getsize(weights_path) / (1024 * 1024)
        print(f"[✓] Weights already exist at {weights_path} ({size_mb:.1f} MB)")
        return weights_path

    print("[*] Downloading RIFE pretrained weights from Google Drive...")
    print("[*] Source: https://drive.google.com/file/d/1APIzVeI-4ZZCEuIRE1m6WYfSCaOsi_7_")

    try:
        import gdown
    except ImportError:
        print("[!] gdown not installed. Installing...")
        os.system(f"{sys.executable} -m pip install gdown")
        import gdown

    # Official RIFE HD model weights (Google Drive file ID)
    file_id = "1APIzVeI-4ZZCEuIRE1m6WYfSCaOsi_7_"
    zip_path = os.path.join(weights_dir, "rife_weights.zip")

    try:
        gdown.download(id=file_id, output=zip_path, quiet=False)
    except Exception as e:
        print(f"[!] gdown download failed: {e}")
        print("[*] Trying alternative download method...")
        # Fallback: direct URL
        url = f"https://drive.google.com/uc?id={file_id}"
        gdown.download(url, zip_path, quiet=False)

    # Extract the zip
    import zipfile
    print(f"[*] Extracting weights from {zip_path}...")
    with zipfile.ZipFile(zip_path, 'r') as z:
        # List contents to find flownet.pkl
        names = z.namelist()
        print(f"[*] Archive contents: {names}")
        for name in names:
            if name.endswith("flownet.pkl"):
                # Extract to weights directory
                data = z.read(name)
                with open(weights_path, 'wb') as f:
                    f.write(data)
                print(f"[✓] Extracted flownet.pkl to {weights_path}")
                break
        else:
            # If no flownet.pkl found, extract everything
            z.extractall(weights_dir)
            print(f"[*] Extracted all files to {weights_dir}")
            # Look for the pkl file
            for root, dirs, files in os.walk(weights_dir):
                for f in files:
                    if f == "flownet.pkl":
                        src = os.path.join(root, f)
                        if src != weights_path:
                            os.rename(src, weights_path)
                        print(f"[✓] Found flownet.pkl at {weights_path}")
                        break

    # Clean up zip
    if os.path.exists(zip_path):
        os.remove(zip_path)

    if os.path.exists(weights_path):
        size_mb = os.path.getsize(weights_path) / (1024 * 1024)
        print(f"[✓] Download complete! Weights: {weights_path} ({size_mb:.1f} MB)")
    else:
        print("[✗] ERROR: flownet.pkl not found after extraction.")
        print(f"[*] Check contents of {weights_dir}")
        sys.exit(1)

    return weights_path


if __name__ == "__main__":
    download_weights()
