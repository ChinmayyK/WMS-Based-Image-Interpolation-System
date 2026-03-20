"""
Generate mock Cloud Masks and Motion Vectors for the WebGIS Demo.
- Cloud Masks: Transparent blue overlays highlighting simulated cloud density.
- Motion Vectors: Grid of directional arrows showing optical flow.
"""
import os
import struct
import zlib
import json
import math

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CLOUD_DIR = os.path.join(DATA_DIR, "cloud_masks")
VECTOR_DIR = os.path.join(DATA_DIR, "motion_vectors")

WIDTH, HEIGHT = 256, 256

FRAMES = [
    ("frame_10_00", 0.0),
    ("frame_10_05", 0.2),
    ("frame_10_10", 0.4),
    ("frame_10_15", 0.6),
    ("frame_10_20", 0.8),
    ("frame_10_25", 1.0),
    ("frame_10_30", 1.2),
]


def create_cloud_png(width, height, phase):
    """Create a transparent blue/white cloud mask using sine waves."""
    def make_chunk(chunk_type, data):
        chunk = chunk_type + data
        return struct.pack('>I', len(data)) + chunk + struct.pack('>I', zlib.crc32(chunk) & 0xffffffff)

    raw_data = b''
    for y in range(height):
        raw_data += b'\x00'  # filter byte
        ny = y / height
        for x in range(width):
            nx = x / width
            
            # Simple noise/cloud simulation using overlapping sine waves
            v = math.sin(nx * 10 + phase) * math.cos(ny * 10 + phase)
            v += 0.5 * math.sin(nx * 20 - phase) * math.cos(ny * 20 - phase)
            
            # Normalize and threshold for clouds
            intensity = max(0.0, min(1.0, float((v + 1) / 2)))
            
            # Blue-white clouds
            r = int(200 + 55 * intensity)
            g = int(220 + 35 * intensity)
            b = 255
            
            # Cloud density controls alpha (transparency)
            a = int(180 * intensity) if intensity > 0.4 else 0
            
            raw_data += struct.pack('BBBB', r, g, b, a)

    compressed = zlib.compress(raw_data)

    png = b'\x89PNG\r\n\x1a\n'
    png += make_chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) # Type 6 = RGBA
    png += make_chunk(b'IDAT', compressed)
    png += make_chunk(b'IEND', b'')
    return png


def create_motion_vectors(phase):
    """Generate mock GeoJSON motion vectors across the default GOES-East demo region."""
    # Bounding box over the Gulf of Mexico / western Atlantic (EPSG:4326)
    MIN_LON, MIN_LAT = -95.0, 12.0
    MAX_LON, MAX_LAT = -60.0, 40.0
    
    features = []
    
    # Grid of vectors
    steps = 10
    lon_step = (MAX_LON - MIN_LON) / steps
    lat_step = (MAX_LAT - MIN_LAT) / steps
    
    for i in range(steps):
        for j in range(steps):
            lon = MIN_LON + (i + 0.5) * lon_step
            lat = MIN_LAT + (j + 0.5) * lat_step
            
            # Simulate swirling wind/motion pattern
            dx = math.sin(lat * 0.5 + phase) * 0.5
            dy = math.cos(lon * 0.5 + phase) * 0.5
            
            # Arrow head coordinates (simple line string for OpenLayers)
            end_lon = lon + dx
            end_lat = lat + dy
            
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon, lat], [end_lon, end_lat]]
                },
                "properties": {
                    "magnitude": math.sqrt(dx*dx + dy*dy)
                }
            })
            
    return {
        "type": "FeatureCollection",
        "features": features
    }


def main():
    os.makedirs(CLOUD_DIR, exist_ok=True)
    os.makedirs(VECTOR_DIR, exist_ok=True)

    for name, phase in FRAMES:
        # Create cloud PNG
        cloud_file = os.path.join(CLOUD_DIR, f"{name}_cloud.png")
        with open(cloud_file, 'wb') as f:
            f.write(create_cloud_png(WIDTH, HEIGHT, phase))
            
        # Create vectors JSON
        vector_file = os.path.join(VECTOR_DIR, f"{name}_vectors.json")
        with open(vector_file, 'w') as f:
            json.dump(create_motion_vectors(phase), f)
            
        print(f"Generated {name} analytics layers.")

    print("\nDone! Generated cloud masks and motion vectors.")


if __name__ == "__main__":
    main()
