export interface SatelliteFrame {
  timestamp: string;
  imageUrl: string;
  cloudMaskUrl?: string;
  vectorsUrl?: string;
  isOriginal: boolean;
  confidence: number;
  sourceFrames?: [string, string];
  bbox?: [number, number, number, number];
  /**
   * EPSG:3857 image extent [minX, minY, maxX, maxY] in metres.
   * Used as imageExtent in OpenLayers for local static images (AI interpolated frames).
   */
  extent3857?: [number, number, number, number];
  /**
   * WMS DATE string (YYYY-MM-DD) for sensor (original) frames.
   * When present, MapViewer uses live ImageWMS against NASA GIBS instead
   * of ImageStatic — providing seamless, properly tiled satellite imagery.
   */
  wmsDate?: string;
  /**
   * WMS layer name override (defaults to MODIS_Terra_CorrectedReflectance_TrueColor).
   */
  wmsLayer?: string;
}

export type PlaybackSpeed = 0.5 | 1.0 | 1.5 | 2.0;

export type ComparisonMode = "off" | "split" | "toggle";

export type DataSource = "demo" | "api";

export interface AppState {
  isLoading: boolean;
  error: string | null;
  dataSource: DataSource;
}
