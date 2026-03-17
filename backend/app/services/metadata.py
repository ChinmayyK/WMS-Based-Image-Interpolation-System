import json
import os
import time

def generate_metadata_for_frame(frame_path: str, source_frame1: str, source_frame2: str, timestamp_str: str, confidence: float):
    """
    Generates a metadata JSON file corresponding to an interpolated frame.
    """
    base_name = os.path.basename(frame_path)
    name_without_ext = os.path.splitext(base_name)[0]
    
    metadata = {
        "frame_id": name_without_ext,
        "time": timestamp_str,
        "generated": True,
        "confidence": round(confidence, 2),
        "source_frames": [os.path.basename(source_frame1), os.path.basename(source_frame2)],
        "generated_at": time.time()
    }
    
    # We save metadata alongside frames or in a dedicated directory
    # Assume data directory structure: data/metadata/
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
    meta_dir = os.path.join(data_dir, "metadata")
    os.makedirs(meta_dir, exist_ok=True)
    
    meta_path = os.path.join(meta_dir, f"{name_without_ext}.json")
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=4)
        
    return meta_path
