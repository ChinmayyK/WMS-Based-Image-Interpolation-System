import { ConfidenceCategory, RuntimeDiagnostics, SatelliteFrame } from "./types";

export const CATEGORY_STYLES: Record<
  ConfidenceCategory,
  { bg: string; text: string; border: string; dot: string }
> = {
  OBSERVED: {
    bg: "bg-observed/18",
    text: "text-observed",
    border: "border-observed/30",
    dot: "bg-observed",
  },
  HIGH: {
    bg: "bg-confidence-high/18",
    text: "text-confidence-high",
    border: "border-confidence-high/30",
    dot: "bg-confidence-high",
  },
  MEDIUM: {
    bg: "bg-confidence-medium/18",
    text: "text-confidence-medium",
    border: "border-confidence-medium/30",
    dot: "bg-confidence-medium",
  },
  LOW: {
    bg: "bg-confidence-low/18",
    text: "text-confidence-low",
    border: "border-confidence-low/30",
    dot: "bg-confidence-low",
  },
  REJECTED: {
    bg: "bg-gap/18",
    text: "text-gap",
    border: "border-gap/30",
    dot: "bg-gap",
  },
  GAP: {
    bg: "bg-gap/18",
    text: "text-gap",
    border: "border-gap/30",
    dot: "bg-gap",
  },
};

export function getConfidenceCategory(frame?: SatelliteFrame): ConfidenceCategory {
  if (!frame) {
    return "LOW";
  }
  if (frame.isGapPlaceholder) {
    return frame.confidenceLabel === "REJECTED" ? "REJECTED" : "GAP";
  }
  if (frame.confidenceLabel) {
    return frame.confidenceLabel;
  }
  if (frame.isOriginal) {
    return "OBSERVED";
  }
  if (frame.confidence >= 0.85) {
    return "HIGH";
  }
  if (frame.confidence >= 0.65) {
    return "MEDIUM";
  }
  if (frame.confidence >= 0.45) {
    return "LOW";
  }
  return "REJECTED";
}

export function getGapCategory(frame?: SatelliteFrame, showRawSensorGaps?: boolean): ConfidenceCategory | null {
  if (frame?.isGapPlaceholder) {
    return frame.confidenceLabel === "REJECTED" ? "REJECTED" : "GAP";
  }
  if (!frame?.hasSensorGap || !showRawSensorGaps) {
    return null;
  }
  return "GAP";
}

export function getTimelineCategory(frame?: SatelliteFrame): ConfidenceCategory {
  if (!frame) {
    return "LOW";
  }
  if (frame.isGapPlaceholder) {
    return frame.confidenceLabel === "REJECTED" ? "REJECTED" : "GAP";
  }
  if (frame.isOriginal) {
    return "OBSERVED";
  }
  return getConfidenceCategory(frame);
}

export function getRuntimeSummary(runtimeDiagnostics?: RuntimeDiagnostics | null): string {
  const execution = runtimeDiagnostics?.interpolation?.execution;
  if (!execution) {
    return "Runtime diagnostics are available in API mode.";
  }
  if (execution.fallbackActive) {
    return "Optical-flow fallback active";
  }
  const device = runtimeDiagnostics?.interpolation?.model.device;
  if (device === "mps") {
    return "MPS acceleration active";
  }
  if (device === "cuda") {
    return "CUDA acceleration active";
  }
  return "CPU inference active";
}

export function formatConfidenceValue(frame?: SatelliteFrame): string {
  if (!frame) {
    return "0.0%";
  }
  if (frame.isOriginal) {
    return "Observed";
  }
  return `${((frame.confidence ?? 0) * 100).toFixed(1)}%`;
}

export function getInterpolationGuardrailMessage(frame?: SatelliteFrame): string | null {
  if (!frame?.sourceFrames || frame.sourceFrames.length !== 2) {
    return null;
  }
  if (typeof frame.gapMinutes === "number" && frame.gapMinutes > 30) {
    return "Interpolation disabled: gap exceeds 30 minutes";
  }
  return null;
}

export function getWmsSummary(runtimeDiagnostics?: RuntimeDiagnostics | null): string {
  const requests = runtimeDiagnostics?.wms?.lastRequests;
  const lastRequest = requests && requests.length > 0 ? requests[requests.length - 1] : undefined;
  if (!lastRequest) {
    return "WMS request history appears after a live API fetch.";
  }
  return `${lastRequest.layers} • ${lastRequest.crs} • ${lastRequest.statusCode ?? "?"}`;
}

export function isInterpolationFrame(frame?: SatelliteFrame): boolean {
  return Boolean(frame && !frame.isOriginal && !frame.isGapPlaceholder);
}

export function getDisplayFrameType(frame?: SatelliteFrame): string {
  if (!frame) {
    return "UNKNOWN";
  }
  if (frame.isGapPlaceholder) {
    return frame.confidenceLabel === "REJECTED" ? "REJECTED PLACEHOLDER" : "GAP PLACEHOLDER";
  }
  return frame.isOriginal ? "OBSERVED" : "INTERPOLATED";
}

export function getGapFillDescription(frame?: SatelliteFrame, showRawSensorGaps?: boolean): string | null {
  if (!frame?.hasSensorGap) {
    return null;
  }
  if (showRawSensorGaps) {
    return "GAP — No Data";
  }
  return `Gap-filled display (${frame.gapFillMethod ?? "temporal borrowing"})`;
}

export function getConfidenceBreakdown(frame?: SatelliteFrame): string | null {
  if (!frame?.metrics) {
    return null;
  }
  const avgSSIM = frame.metrics.avgSSIM;
  const avgMAD = frame.metrics.avgMAD;
  if (typeof avgSSIM !== "number" || typeof avgMAD !== "number") {
    return null;
  }
  return `SSIM ${avgSSIM.toFixed(3)} • MAD ${avgMAD.toFixed(2)}`;
}

export function getMetricValue(value?: number | null, digits = 3): string {
  if (typeof value !== "number") {
    return "N/A";
  }
  return value.toFixed(digits);
}

export function getPairGapLabel(frame?: SatelliteFrame): string | null {
  if (typeof frame?.gapMinutes !== "number") {
    return null;
  }
  return `${frame.gapMinutes.toFixed(1)} min`;
}
