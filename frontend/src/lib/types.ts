export interface SatelliteFrame {
  timestamp: string;
  imageUrl: string;
  rawImageUrl?: string | null;
  cleanImageUrl?: string | null;
  cloudMaskUrl?: string;
  vectorsUrl?: string;
  gapMaskUrl?: string | null;
  hasSensorGap?: boolean;
  gapCoveragePct?: number;
  gapFillMethod?: string | null;
  isOriginal: boolean;
  confidence: number;
  confidenceLabel?: ConfidenceCategory;
  confidenceMethod?: string | null;
  metrics?: {
    avgSSIM?: number;
    avgMAD?: number;
    normalizedSSIM?: number;
    normalizedMAD?: number;
    ssimToFrame0?: number;
    ssimToFrame1?: number;
    madToFrame0?: number;
    madToFrame1?: number;
  };
  sourceFrames?: [string, string];
  gapMinutes?: number | null;
  isGapPlaceholder?: boolean;
  placeholderReason?: string | null;
  modelInfo?: {
    name?: string;
    framework?: string;
    weightsFile?: string;
    weightsSizeMB?: number | null;
    device?: string | null;
  };
  bbox?: [number, number, number, number];
  /**
   * EPSG:3857 image extent [minX, minY, maxX, maxY] in metres.
   * Used as imageExtent in OpenLayers for local static images (AI interpolated frames).
   */
  extent3857?: [number, number, number, number];
  /**
   * WMS DATE string (YYYY-MM-DD) for sensor (original) frames.
   * When present, MapViewer can use live TileWMS against NASA GIBS for
   * scientifically raw observed imagery.
   */
  wmsDate?: string;
  /**
   * WMS layer name override (defaults to MODIS_Terra_CorrectedReflectance_TrueColor).
   */
  wmsLayer?: string;
  /**
   * Fully qualified WMS GetMap base URL used for live sensor rendering.
   */
  wmsUrl?: string;
  /**
   * CRS used for the live WMS source.
   */
  wmsCrs?: string;
}

export type PlaybackSpeed = 0.5 | 1.0 | 1.5 | 2.0;

export type ComparisonMode = "off" | "split" | "toggle";

export type DataSource = "demo" | "api";

export type ConfidenceCategory = "OBSERVED" | "HIGH" | "MEDIUM" | "LOW" | "REJECTED" | "GAP";

export interface WmsRequestDiagnostics {
  time: string;
  endpoint: string;
  requestedUrl: string;
  statusCode: number | null;
  contentType?: string | null;
  bbox: number[];
  crs: string;
  layers: string;
  width: number;
  height: number;
  savedPath?: string | null;
  savedBytes?: number;
  error?: string;
}

export interface RuntimeDiagnostics {
  catalog?: {
    frameCount: number;
    rawFramesDir: string;
    interpolatedFramesDir: string;
    cleanFramesDir?: string;
    sensorGapMasksDir?: string;
    gapPlaceholdersDir?: string;
    source: string;
  };
  wms?: {
    defaultEndpoints: Record<string, string>;
    overrideEndpoint: string | null;
    lastRequests: WmsRequestDiagnostics[];
  };
  confidence?: {
    generatedAt?: string;
    sampleCount: number;
    baselinePairs: number;
    usedFallbackDefaults: boolean;
    weights: {
      ssim: number;
      mad: number;
    };
    ssimFloor: number;
    ssimCeiling: number;
    madFloor: number;
    madCeiling: number;
    meanBaselineSSIM?: number | null;
    meanBaselineMAD?: number | null;
    labelThresholds: Record<string, number>;
  };
  interpolation?: {
    model: {
      name: string;
      framework: string;
      weightsFile: string;
      weightsPath: string;
      weightsSizeBytes: number | null;
      weightsSizeMB: number | null;
      loaded: boolean;
      loadedAt: string | null;
      device: string | null;
      cudaAvailable: boolean;
      mpsAvailable: boolean;
      loadError: string | null;
    };
    execution: {
      activeMode: string;
      fallbackActive?: boolean;
      fallbackBehavior: string;
      performanceExplanation?: string;
      lastRun?: {
        startedAt: string;
        completedAt: string;
        durationMs: number;
        input0: string;
        input1: string;
        output: string;
        ratio: number;
        executionMode: string;
        device: string | null;
        outputShape: number[];
        opaqueCoveragePct: number;
        usedModelWeights: boolean;
        performanceExplanation?: string;
      } | null;
      lastBatch?: {
        startedAt: string;
        completedAt: string;
        requestedFrames: number;
        generatedFrames: number;
        outputDir: string;
        strategy?: string;
        ratios?: number[];
        frameDurationsMs?: number[];
        executionMode: string;
        outputs: string[];
        performanceExplanation?: string;
      } | null;
    };
  };
  export?: {
    jobId: string;
    ffmpegExecutable: string;
    fps: number;
    rawMode: boolean;
    frameCount: number;
    mp4Url: string;
    webmUrl: string;
    metadataUrl: string;
  } | null;
  evaluation?: {
    generatedAt: string;
    datasetCount: number;
    results: Array<{
      name: string;
      type: string;
      inputFrames: string[];
      targetFrame: string;
      psnr: number;
      ssim: number;
      lpips?: number | null;
    }>;
    averages: {
      psnr: number;
      ssim: number;
      lpips?: number | null;
    };
  } | null;
}

export interface AppState {
  isLoading: boolean;
  error: string | null;
  dataSource: DataSource;
}
