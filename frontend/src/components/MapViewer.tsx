import { useCallback, useEffect, useRef } from "react";
import Map from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import ImageLayer from "ol/layer/Image";
import VectorLayer from "ol/layer/Vector";
import OSM from "ol/source/OSM";
import Static from "ol/source/ImageStatic";
import VectorSource from "ol/source/Vector";
import GeoJSON from "ol/format/GeoJSON";
import { Style, Stroke } from "ol/style";
import { get as getProjection } from "ol/proj";
import { Layer } from "ol/layer";
import "ol/ol.css";
import MapControlsPanel from "./MapControlsPanel";
import LegendPanel from "./LegendPanel";
import {
  CATEGORY_STYLES,
  formatConfidenceValue,
  getConfidenceBreakdown,
  getConfidenceCategory,
  getDisplayFrameType,
  getGapCategory,
  getGapFillDescription,
  isInterpolationFrame,
} from "@/lib/frame-status";
import { RuntimeDiagnostics, SatelliteFrame } from "@/lib/types";

interface MapViewerProps {
  opacity: number;
  showOverlay: boolean;
  onToggleOverlay: () => void;
  showRawSensorGaps: boolean;
  onToggleRawSensorGaps: () => void;
  showConfidence: boolean;
  onToggleConfidence: () => void;
  showClouds: boolean;
  onToggleClouds: () => void;
  showVectors: boolean;
  onToggleVectors: () => void;
  currentFrame?: SatelliteFrame;
  comparisonMode?: "off" | "split" | "toggle";
  runtimeDiagnostics?: RuntimeDiagnostics | null;
}

const DEFAULT_EXTENT_3857: [number, number, number, number] = [
  -10575351.63, 1345708.41, -6679169.45, 4865942.28,
];
const DEFAULT_CENTER: [number, number] = [
  (DEFAULT_EXTENT_3857[0] + DEFAULT_EXTENT_3857[2]) / 2,
  (DEFAULT_EXTENT_3857[1] + DEFAULT_EXTENT_3857[3]) / 2,
];
const DEFAULT_ZOOM = 5;
const CROSSFADE_MS = 350;
const CROSSFADE_STEPS = 18;

const PROJ_3857 = getProjection("EPSG:3857")!;

const vectorStyle = new Style({
  stroke: new Stroke({ color: "rgba(255,200,0,0.85)", width: 2 }),
});

const MapViewer = ({
  opacity,
  showOverlay,
  onToggleOverlay,
  showRawSensorGaps,
  onToggleRawSensorGaps,
  showConfidence,
  onToggleConfidence,
  showClouds,
  onToggleClouds,
  showVectors,
  onToggleVectors,
  currentFrame,
  comparisonMode = "off",
  runtimeDiagnostics,
}: MapViewerProps) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<Map | null>(null);

  const activeLayerRef = useRef<Layer | null>(null);
  const prevLayerRef = useRef<Layer | null>(null);
  const fadeTimerRef = useRef<number | null>(null);

  const cloudLayerRef = useRef<Layer | null>(null);
  const gapLayerRef = useRef<Layer | null>(null);
  const vectorLayerRef = useRef<Layer | null>(null);
  const lastExtentKeyRef = useRef<string>("");

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const map = new Map({
      target: mapRef.current,
      layers: [
        new TileLayer({
          source: new OSM(),
          zIndex: 0,
        }),
      ],
      view: new View({
        center: DEFAULT_CENTER,
        zoom: DEFAULT_ZOOM,
        projection: PROJ_3857,
        minZoom: 2,
        maxZoom: 18,
      }),
    });

    mapInstanceRef.current = map;
    map.getView().fit(DEFAULT_EXTENT_3857, { padding: [60, 60, 60, 60] });

    return () => {
      map.setTarget(undefined);
      mapInstanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (!showOverlay) {
      [activeLayerRef, prevLayerRef].forEach((ref) => {
        if (ref.current) {
          map.removeLayer(ref.current);
          ref.current = null;
        }
      });
      return;
    }

    if (!currentFrame) return;

    if (fadeTimerRef.current) {
      clearInterval(fadeTimerRef.current);
      fadeTimerRef.current = null;
    }

    if (prevLayerRef.current) {
      map.removeLayer(prevLayerRef.current);
      prevLayerRef.current = null;
    }
    const oldLayer = activeLayerRef.current;
    if (oldLayer) prevLayerRef.current = oldLayer;

    const imageUrl =
      showRawSensorGaps && currentFrame.isOriginal
        ? currentFrame.rawImageUrl ?? currentFrame.imageUrl
        : currentFrame.cleanImageUrl ?? currentFrame.imageUrl;
    const extent = currentFrame.extent3857 ?? DEFAULT_EXTENT_3857;

    const newLayer = new ImageLayer({
      source: new Static({
        url: imageUrl,
        imageExtent: extent,
        projection: PROJ_3857,
        crossOrigin: "anonymous",
      }),
      opacity: 0,
      zIndex: 1,
    });

    map.addLayer(newLayer);
    activeLayerRef.current = newLayer;

    const extentKey = extent.join(",");
    if (lastExtentKeyRef.current !== extentKey) {
      map.getView().fit(extent, { padding: [60, 60, 60, 60], duration: 800 });
      lastExtentKeyRef.current = extentKey;
    }

    let step = 0;
    const interval = CROSSFADE_MS / CROSSFADE_STEPS;
    fadeTimerRef.current = window.setInterval(() => {
      step += 1;
      const t = Math.min(step / CROSSFADE_STEPS, 1);
      const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      newLayer.setOpacity(eased * opacity);
      if (oldLayer) oldLayer.setOpacity((1 - eased) * opacity);

      if (step >= CROSSFADE_STEPS) {
        clearInterval(fadeTimerRef.current!);
        fadeTimerRef.current = null;
        newLayer.setOpacity(opacity);
        if (oldLayer) {
          map.removeLayer(oldLayer);
          prevLayerRef.current = null;
        }
      }
    }, interval);

    if (gapLayerRef.current) {
      map.removeLayer(gapLayerRef.current);
      gapLayerRef.current = null;
    }
    if (showConfidence && currentFrame.gapMaskUrl) {
      const gapLayer = new ImageLayer({
        source: new Static({
          url: currentFrame.gapMaskUrl,
          imageExtent: extent,
          projection: PROJ_3857,
          crossOrigin: "anonymous",
        }),
        opacity: showRawSensorGaps ? 0.24 : 0.34,
        zIndex: 2,
      });
      map.addLayer(gapLayer);
      gapLayerRef.current = gapLayer;
    }

    if (cloudLayerRef.current) {
      map.removeLayer(cloudLayerRef.current);
      cloudLayerRef.current = null;
    }
    if (showClouds && currentFrame.cloudMaskUrl) {
      const cloudLayer = new ImageLayer({
        source: new Static({
          url: currentFrame.cloudMaskUrl,
          imageExtent: extent,
          projection: PROJ_3857,
          crossOrigin: "anonymous",
        }),
        opacity: 0.55,
        zIndex: 2,
      });
      map.addLayer(cloudLayer);
      cloudLayerRef.current = cloudLayer;
    }

    if (vectorLayerRef.current) {
      map.removeLayer(vectorLayerRef.current);
      vectorLayerRef.current = null;
    }
    if (showVectors && currentFrame.vectorsUrl) {
      const vectorLayer = new VectorLayer({
        source: new VectorSource({ url: currentFrame.vectorsUrl, format: new GeoJSON() }),
        style: vectorStyle,
        zIndex: 3,
      });
      map.addLayer(vectorLayer);
      vectorLayerRef.current = vectorLayer;
    }

    return () => {
      if (fadeTimerRef.current) {
        clearInterval(fadeTimerRef.current);
        fadeTimerRef.current = null;
      }
    };
  }, [currentFrame, showOverlay, showRawSensorGaps, showConfidence, showClouds, showVectors, opacity]);

  const confidenceCategory = getConfidenceCategory(currentFrame);
  const confidenceStyle = CATEGORY_STYLES[confidenceCategory];
  const gapCategory = getGapCategory(currentFrame, showRawSensorGaps);
  const gapStyle = gapCategory ? CATEGORY_STYLES[gapCategory] : null;
  const performanceExplanation = runtimeDiagnostics?.interpolation?.execution.performanceExplanation;
  const frameType = getDisplayFrameType(currentFrame);
  const confidenceValue = formatConfidenceValue(currentFrame);
  const confidenceBreakdown = getConfidenceBreakdown(currentFrame);
  const gapFillDescription = getGapFillDescription(currentFrame, showRawSensorGaps);
  const isInterpolatedFrame = isInterpolationFrame(currentFrame);

  const handleResetView = useCallback(() => {
    const extent = currentFrame?.extent3857 ?? DEFAULT_EXTENT_3857;
    mapInstanceRef.current?.getView().fit(extent, { padding: [60, 60, 60, 60], duration: 500 });
  }, [currentFrame]);

  return (
    <div className="relative w-full h-full bg-map-bg rounded overflow-hidden border">
      <div ref={mapRef} className="w-full h-full" />

      <div className="absolute top-4 left-4 z-10 flex flex-col gap-2 pointer-events-none">
        <div className="bg-background/90 backdrop-blur-md border border-primary/20 rounded-lg p-4 shadow-xl min-w-[200px]">
          <div className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground mb-1">
            {frameType}
          </div>
          <div className="text-base font-mono font-bold text-primary flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse flex-shrink-0" />
            {currentFrame?.timestamp}
          </div>
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <span className={`text-[10px] px-1.5 py-0.5 rounded border font-bold ${confidenceStyle.bg} ${confidenceStyle.text} ${confidenceStyle.border}`}>
              {confidenceCategory}
            </span>
            {gapStyle && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded border font-bold ${gapStyle.bg} ${gapStyle.text} ${gapStyle.border}`}>
                GAP — NO DATA
              </span>
            )}
            {isInterpolatedFrame && (
              <span className="text-[10px] px-1.5 py-0.5 rounded border font-bold bg-primary/15 text-primary border-primary/20">
                AI-GENERATED
              </span>
            )}
            {showConfidence && (
              <span className="text-[10px] bg-primary/20 text-primary-foreground px-1.5 py-0.5 rounded font-bold">
                {confidenceCategory}: {confidenceValue}
              </span>
            )}
          </div>
          {gapFillDescription && (
            <div className="mt-2 text-[10px] font-mono text-muted-foreground">
              {gapFillDescription}
            </div>
          )}
          {confidenceBreakdown && (
            <div className="mt-2 text-[10px] font-mono text-muted-foreground">
              {confidenceBreakdown}
            </div>
          )}
          {currentFrame?.isGapPlaceholder && currentFrame?.placeholderReason && (
            <div className="mt-2 rounded-md border border-gap/25 bg-gap/12 px-2 py-1 text-[10px] font-mono text-gap">
              {currentFrame.placeholderReason}
            </div>
          )}
          {isInterpolatedFrame && (
            <div className="mt-2 rounded-md border border-confidence-low/35 bg-confidence-low/18 px-2 py-1 text-[10px] font-mono text-white">
              AI-GENERATED — NOT OBSERVED DATA
            </div>
          )}
          {performanceExplanation && (
            <div className="mt-2 text-[10px] font-mono text-muted-foreground">
              {performanceExplanation}
            </div>
          )}
        </div>
      </div>

      <MapControlsPanel
        onResetView={handleResetView}
        showOverlay={showOverlay}
        onToggleOverlay={onToggleOverlay}
        showRawSensorGaps={showRawSensorGaps}
        onToggleRawSensorGaps={onToggleRawSensorGaps}
        showConfidence={showConfidence}
        onToggleConfidence={onToggleConfidence}
        showClouds={showClouds}
        onToggleClouds={onToggleClouds}
        showVectors={showVectors}
        onToggleVectors={onToggleVectors}
      />
      <LegendPanel />
    </div>
  );
};

export default MapViewer;
