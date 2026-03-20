export interface SatelliteFrame {
  timestamp: string;
  imageUrl: string;
  rawImageUrl?: string | null;
  cleanImageUrl?: string | null;
  type?: "OBSERVED" | "INTERPOLATED" | "GAP";
  source?: string | null;
  cloudMaskUrl?: string;
  vectorsUrl?: string;
  gapMaskUrl?: string | null;
  nodataMaskUrl?: string | null;
  limbMaskUrl?: string | null;
  terminatorMaskUrl?: string | null;
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
    version?: string;
    framework?: string;
    weightsFile?: string;
    weightsSizeMB?: number | null;
    device?: string | null;
    benchmarkCompliant?: boolean;
    deviationNote?: string | null;
  };
  fallbackUsed?: boolean;
  fallbackMethod?: string | null;
  inferenceTimeMs?: number | null;
  motionInfo?: {
    available?: boolean;
    method?: string;
    meanMagnitudePx?: number;
    maxMagnitudePx?: number;
    p95MagnitudePx?: number;
  };
  audit?: {
    jobId?: string;
    logUrl?: string;
  };
  bbox?: [number, number, number, number];
  /**
   * EPSG:3857 image extent [minX, minY, maxX, maxY] in metres.
   * Used as imageExtent in OpenLayers for local static images (AI interpolated frames).
   */
  extent3857?: [number, number, number, number];
  /**
   * Full WMS TIME value used for the observed GOES frame.
   */
  wmsTime?: string;
  /**
   * WMS layer name override for the observed GOES frame.
   */
  wmsLayer?: string;
  /**
   * Fully qualified WMS GetMap base URL used for GOES retrieval.
   */
  wmsUrl?: string;
  /**
   * CRS used for the GOES WMS source.
   */
  wmsCrs?: string;
}

export type PlaybackSpeed = 0.5 | 1.0 | 1.5 | 2.0;

export type ComparisonMode = "off" | "split" | "toggle";

export type DataSource = "demo" | "api";

export type ConfidenceCategory = "OBSERVED" | "HIGH" | "MEDIUM" | "LOW" | "REJECTED" | "GAP";

export interface WmsRequestDiagnostics {
  requestType?: string;
  attempt?: number;
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
    gapPlaceholdersDir?: string;
    source: string;
    sessionMetadataPath?: string;
    interpolationLogPath?: string;
  };
  session?: {
    sessionId: string;
    source: string;
    layer: string;
    title?: string;
    bbox: number[];
    extent3857?: number[];
    crs: string;
    wmsUrl: string;
    requestedStartTime: string;
    requestedEndTime: string;
    availableStartTime?: string;
    availableEndTime?: string;
    availableFrameCount: number;
    downloadedFrameCount: number;
    failedFrameCount: number;
    failedTimestamps: Array<{
      timestamp: string;
      wmsTime: string;
      error: string;
    }>;
    cadenceMinutes: {
      minGapMinutes?: number | null;
      medianGapMinutes?: number | null;
      maxGapMinutes?: number | null;
    };
    validation?: {
      continuousFrames?: boolean;
      observedFrameCount?: number;
      failedFrameCount?: number;
      minGapMinutes?: number | null;
      medianGapMinutes?: number | null;
      maxGapMinutes?: number | null;
    };
    metadataUrl?: string;
  } | null;
  wms?: {
    defaultEndpoints: Record<string, string>;
    overrideEndpoint: string | null;
    defaultLayer?: string;
    lastCapabilitiesFetch?: {
      endpoint: string;
      requestedUrl: string;
      fetchedAt: string;
      layerCount: number;
    } | null;
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
      version?: string;
      preferredModel?: string;
      benchmarkCompliant?: boolean;
      deviationNote?: string | null;
      framework: string;
      weightsFile: string;
      weightsPath: string;
      weightsSizeBytes: number | null;
      weightsSizeMB: number | null;
      weightsSha256?: string | null;
      expectedWeightsSha256?: string | null;
      integrityVerified?: boolean;
      loaded: boolean;
      startupValidated?: boolean;
      loadedAt: string | null;
      device: string | null;
      cudaAvailable: boolean;
      mpsAvailable: boolean;
      loadError: string | null;
      startupErrors?: string[];
    };
    execution: {
      activeMode: string;
      fallbackActive?: boolean;
      fallbackBehavior: string;
      fallbackMethod?: string;
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
        fallbackUsed?: boolean;
        fallbackMethod?: string | null;
        suspiciousRuntime?: boolean;
        performanceExplanation?: string;
      } | null;
      lastBatch?: {
        jobId?: string;
        startedAt: string;
        completedAt: string;
        requestedFrames: number;
        generatedFrames: number;
        outputDir: string;
        strategy?: string;
        ratios?: number[];
        frameDurationsMs?: number[];
        totalInferenceTimeMs?: number;
        wallTimeMs?: number;
        executionMode: string;
        fallbackUsed?: boolean;
        fallbackMethod?: string | null;
        recursionDepth?: number;
        outputs: string[];
        auditLogUrl?: string;
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
    version: string;
    generatedAt: string;
    datasetCount: number;
    sampleCount: number;
    results: Array<{
      jobId: string;
      name: string;
      type: string;
      regime: string;
      inputFrames: string[];
      targetFrame: string;
      psnr: number;
      ssim: number;
      lpips?: number | null;
      tof: number;
      baseline: string;
      baselineMetrics: {
        psnr: number;
        ssim: number;
        lpips?: number | null;
        tof: number;
      };
      comparison: {
        psnrDelta: number;
        ssimDelta: number;
        lpipsDelta?: number | null;
        tofDelta: number;
        winner: string;
      };
    }>;
    averages: {
      psnr: number;
      ssim: number;
      lpips?: number | null;
      tof: number;
    };
    baselineAverages: {
      psnr: number;
      ssim: number;
      lpips?: number | null;
      tof: number;
    };
    thresholds: {
      psnr: number;
      ssim: number;
    };
    targetValidation: {
      meetsPSNR: boolean;
      meetsSSIM: boolean;
      meetsAll: boolean;
      warning?: string | null;
    };
    confidenceValidation: {
      confidence_accuracy: number;
      overall_label_accuracy?: number;
      rejection_rate: number;
      misclassification: number;
    };
    confidenceCalibration?: {
      expectedCalibrationError: number;
      bins: Array<{
        range: [number, number];
        count: number;
        meanScore?: number | null;
        observedAccuracy?: number | null;
      }>;
    };
    distributions?: Record<string, {
      mean: number;
      median: number;
      std: number;
      min: number;
      max: number;
    } | null>;
    baselineDistributions?: Record<string, {
      mean: number;
      median: number;
      std: number;
      min: number;
      max: number;
    } | null>;
    qualificationGate?: {
      sampleCount?: number;
      passed: boolean;
      productionAllowed: boolean;
      fallbackMode?: string | null;
      checks: Record<string, boolean>;
    };
    reportPaths: {
      jsonUrl: string;
      htmlUrl: string;
    };
  } | null;
}

export interface AppState {
  isLoading: boolean;
  error: string | null;
  dataSource: DataSource;
}
