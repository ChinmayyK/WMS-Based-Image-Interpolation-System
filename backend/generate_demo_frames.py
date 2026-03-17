"""
Generate demo satellite-like PNG frames for testing.
Creates colorful gradient images that visually differ per timestamp
so animation changes are clearly visible.
"""
import os
import struct
import zlib
import math
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RAW_DIR = os.path.join(DATA_DIR, "raw_frames")
INTERP_DIR = os.path.join(DATA_DIR, "interpolated_frames")

WIDTH, HEIGHT = 256, 256

FRAMES = [
    ("frame_10_00.png", RAW_DIR,    (30, 80, 30),   (20, 60, 120),  True),
    ("frame_10_05.png", INTERP_DIR, (40, 90, 35),   (25, 70, 130),  False),
    ("frame_10_10.png", INTERP_DIR, (50, 100, 40),  (30, 80, 140),  False),
    ("frame_10_15.png", INTERP_DIR, (60, 110, 50),  (35, 90, 150),  False),
    ("frame_10_20.png", INTERP_DIR, (70, 120, 55),  (40, 100, 155), False),
    ("frame_10_25.png", INTERP_DIR, (80, 130, 60),  (45, 110, 160), False),
    ("frame_10_30.png", RAW_DIR,    (90, 140, 65),  (50, 120, 170), True),
]


def create_png(width: int, height: int, top_color: tuple, bottom_color: tuple) -> bytes:
    """Create a simple gradient PNG using pure Python (no PIL needed)."""
    def make_chunk(chunk_type, data):
        chunk = chunk_type + data
        return struct.pack('>I', len(data)) + chunk + struct.pack('>I', zlib.crc32(chunk) & 0xffffffff)

    raw_data = b''
    # Simple deterministic noise based on coordinates to represent "features"
    seed = (top_color[0] + bottom_color[1]) % 100
    for y in range(height):
        raw_data += b'\x00'  # filter byte
        t = float(y) / float(max(height - 1, 1))
        for x in range(width):
            tx = float(x) / float(max(width - 1, 1))
            
            # Base gradient
            r_base = float(top_color[0]) * (1.0 - t) + float(bottom_color[0]) * t
            g_base = float(top_color[1]) * (1.0 - t) + float(bottom_color[1]) * t
            b_base = float(top_color[2]) * (1.0 - t) + float(bottom_color[2]) * t
            
            # Add some "cloud" noise
            noise = (np.sin(x * 0.1 + seed) * np.cos(y * 0.1 - seed) * 30) + (np.sin((x+y) * 0.05) * 20)
            
            r = int(r_base + noise + 30.0 * tx)
            g = int(g_base + noise + 20.0 * (1.0 - tx))
            b = int(b_base + noise)
            
            r, g, b = max(0, min(r, 255)), max(0, min(g, 255)), max(0, min(b, 255))
            raw_data += struct.pack('BBB', r, g, b)

    compressed = zlib.compress(raw_data)

    png = b'\x89PNG\r\n\x1a\n'
    png += make_chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    png += make_chunk(b'IDAT', compressed)
    png += make_chunk(b'IEND', b'')
    return png


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(INTERP_DIR, exist_ok=True)

    for filename, directory, top_c, bot_c, is_original in FRAMES:
        filepath = os.path.join(directory, filename)
        png_data = create_png(WIDTH, HEIGHT, top_c, bot_c)
        with open(filepath, 'wb') as f:
            f.write(png_data)
        label = "original" if is_original else "interpolated"
        print(f"  Created {label}: {filepath}")

    print(f"\nDone! Generated {len(FRAMES)} demo frames.")


if __name__ == "__main__":
    main()
