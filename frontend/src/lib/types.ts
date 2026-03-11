export interface SatelliteFrame {
  timestamp: string;
  imageUrl: string;
  isOriginal: boolean;
  confidence: number;
  sourceFrames?: [string, string];
}

export type PlaybackSpeed = 0.5 | 1.0 | 1.5 | 2.0;

export type ComparisonMode = "off" | "split" | "toggle";

export type DataSource = "demo" | "api";

export interface AppState {
  isLoading: boolean;
  error: string | null;
  dataSource: DataSource;
}
