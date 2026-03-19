import { SatelliteFrame } from "./types";

/**
 * EPSG:3857 extent for India [minX, minY, maxX, maxY] in metres.
 * Pre-computed from [68, 6, 98, 36] EPSG:4326.
 * Used directly as imageExtent in OpenLayers — no transformExtent needed.
 */
const INDIA_EXTENT_3857: [number, number, number, number] = [
  7569725.37, 669141.06, 10909310.10, 4300621.37,
];

export const MOCK_FRAMES: SatelliteFrame[] = [
  {
    timestamp: "2024-06-01",
    imageUrl: "/data/raw_frames/frame_10_00.png",
    isOriginal: true,
    confidence: 1.0,
    extent3857: INDIA_EXTENT_3857,
    wmsDate: "2024-06-01",
  },
  {
    timestamp: "2024-06-01 08:00",
    imageUrl: "/data/interpolated_frames/interp_frame_10_00_frame_25_00_25.png",
    isOriginal: false,
    confidence: 0.95,
    sourceFrames: ["2024-06-01", "2024-06-02"],
    extent3857: INDIA_EXTENT_3857,
  },
  {
    timestamp: "2024-06-01 16:00",
    imageUrl: "/data/interpolated_frames/interp_frame_10_00_frame_25_00_50.png",
    isOriginal: false,
    confidence: 0.91,
    sourceFrames: ["2024-06-01", "2024-06-02"],
    extent3857: INDIA_EXTENT_3857,
  },
  {
    timestamp: "2024-06-02",
    imageUrl: "/data/raw_frames/frame_25_00.png",
    isOriginal: true,
    confidence: 1.0,
    extent3857: INDIA_EXTENT_3857,
    wmsDate: "2024-06-02",
  },
  {
    timestamp: "2024-06-02 08:00",
    imageUrl: "/data/interpolated_frames/interp_frame_25_00_frame_40_00_25.png",
    isOriginal: false,
    confidence: 0.94,
    sourceFrames: ["2024-06-02", "2024-06-03"],
    extent3857: INDIA_EXTENT_3857,
  },
  {
    timestamp: "2024-06-02 16:00",
    imageUrl: "/data/interpolated_frames/interp_frame_25_00_frame_40_00_50.png",
    isOriginal: false,
    confidence: 0.90,
    sourceFrames: ["2024-06-02", "2024-06-03"],
    extent3857: INDIA_EXTENT_3857,
  },
  {
    timestamp: "2024-06-03",
    imageUrl: "/data/raw_frames/frame_40_00.png",
    isOriginal: true,
    confidence: 1.0,
    extent3857: INDIA_EXTENT_3857,
    wmsDate: "2024-06-03",
  },
];
