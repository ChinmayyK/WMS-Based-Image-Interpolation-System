import { SatelliteFrame } from "./types";

export const MOCK_FRAMES: SatelliteFrame[] = [
  {
    timestamp: "10:00",
    imageUrl: "/data/raw_frames/frame_10_00.png",
    isOriginal: true,
    confidence: 1.0,
  },
  {
    timestamp: "10:05",
    imageUrl: "/data/interpolated_frames/frame_10_05.png",
    isOriginal: false,
    confidence: 0.94,
    sourceFrames: ["10:00", "10:30"],
  },
  {
    timestamp: "10:10",
    imageUrl: "/data/interpolated_frames/frame_10_10.png",
    isOriginal: false,
    confidence: 0.87,
    sourceFrames: ["10:00", "10:30"],
  },
  {
    timestamp: "10:15",
    imageUrl: "/data/interpolated_frames/frame_10_15.png",
    isOriginal: false,
    confidence: 0.82,
    sourceFrames: ["10:00", "10:30"],
  },
  {
    timestamp: "10:20",
    imageUrl: "/data/interpolated_frames/frame_10_20.png",
    isOriginal: false,
    confidence: 0.89,
    sourceFrames: ["10:00", "10:30"],
  },
  {
    timestamp: "10:25",
    imageUrl: "/data/interpolated_frames/frame_10_25.png",
    isOriginal: false,
    confidence: 0.91,
    sourceFrames: ["10:00", "10:30"],
  },
  {
    timestamp: "10:30",
    imageUrl: "/data/raw_frames/frame_10_30.png",
    isOriginal: true,
    confidence: 1.0,
  },
];
