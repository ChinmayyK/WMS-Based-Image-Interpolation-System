import { useEffect, useRef, useCallback } from "react";
import Map from "ol/Map";
import View from "ol/View";
import TileLayer from "ol/layer/Tile";
import ImageLayer from "ol/layer/Image";
import VectorLayer from "ol/layer/Vector";
import OSM from "ol/source/OSM";
import Static from "ol/source/ImageStatic";
import ImageWMS from "ol/source/ImageWMS";
import RasterSource from "ol/source/Raster";
import VectorSource from "ol/source/Vector";
import GeoJSON from "ol/format/GeoJSON";
import { Style, Stroke } from "ol/style";
import { get as getProjection } from "ol/proj";
import { Layer } from "ol/layer";
import "ol/ol.css";
import MapControlsPanel from "./MapControlsPanel";
import LegendPanel from "./LegendPanel";
import { SatelliteFrame } from "@/lib/types";

interface MapViewerProps {
  opacity: number;
  showOverlay: boolean;
  onToggleOverlay: () => void;
  showConfidence: boolean;
  onToggleConfidence: () => void;
  showClouds: boolean;
  onToggleClouds: () => void;
  showVectors: boolean;
  onToggleVectors: () => void;
  currentFrame?: SatelliteFrame;
  comparisonMode?: "off" | "split" | "toggle";
}

/**
 * India EPSG:3857 extent [minX, minY, maxX, maxY] in metres.
 */
const INDIA_EXTENT_3857: [number, number, number, number] = [
  7569725.37, 669141.06, 10909310.10, 4300621.37,
];

const DEFAULT_CENTER: [number, number] = [
  (INDIA_EXTENT_3857[0] + INDIA_EXTENT_3857[2]) / 2,
  (INDIA_EXTENT_3857[1] + INDIA_EXTENT_3857[3]) / 2,
];
const DEFAULT_ZOOM = 5;

// Crossfade settings
const CROSSFADE_MS    = 350;
const CROSSFADE_STEPS = 18;

const PROJ_3857 = getProjection("EPSG:3857")!;
const NASA_GIBS_WMS_URL = "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi";

const vectorStyle = new Style({
  stroke: new Stroke({ color: "rgba(255,200,0,0.85)", width: 2 }),
});

// ─────────────────────────────────────────────────────────────────────────────

const MapViewer = ({
  opacity,
  showOverlay,
  onToggleOverlay,
  showConfidence,
  onToggleConfidence,
  showClouds,
  onToggleClouds,
  showVectors,
  onToggleVectors,
  currentFrame,
  comparisonMode = "off",
}: MapViewerProps) => {
  const mapRef         = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<Map | null>(null);

  const activeLayerRef = useRef<Layer | null>(null);
  const prevLayerRef   = useRef<Layer | null>(null);
  const fadeTimerRef   = useRef<number | null>(null);

  const cloudLayerRef  = useRef<Layer | null>(null);
  const vectorLayerRef = useRef<Layer | null>(null);

  const hasAutoFit = useRef(false);

  // ── Initialize map once ────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const map = new Map({
      target: mapRef.current,
      layers: [
        new TileLayer({ 
          source: new OSM(),
          zIndex: 0 
        })
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

    // Fit to India on first load
    map.getView().fit(INDIA_EXTENT_3857, { padding: [60, 60, 60, 60] });

    return () => {
      map.setTarget(undefined);
      mapInstanceRef.current = null;
    };
  }, []);

  // ── Update satellite overlay on frame change ───────────────────────────────
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    // Remove overlay when toggled off
    if (!showOverlay) {
      [activeLayerRef, prevLayerRef].forEach((ref) => {
        if (ref.current) { map.removeLayer(ref.current); ref.current = null; }
      });
      return;
    }

    if (!currentFrame) return;

    // ── Stop any ongoing fade ─────────────────────────────────────────────────
    if (fadeTimerRef.current) {
      clearInterval(fadeTimerRef.current);
      fadeTimerRef.current = null;
    }

    // Move current → previous
    if (prevLayerRef.current) {
      map.removeLayer(prevLayerRef.current);
      prevLayerRef.current = null;
    }
    const oldLayer = activeLayerRef.current;
    if (oldLayer) prevLayerRef.current = oldLayer;

    // ── Create new layer based on frame type ──────────────────────────────────
    let newLayer: Layer;

    if (currentFrame.isOriginal && currentFrame.wmsDate) {
      // 1. Raw WMS Source
      const wmsSource = new ImageWMS({
        url: NASA_GIBS_WMS_URL,
        params: {
          'LAYERS': currentFrame.wmsLayer || 'MODIS_Terra_CorrectedReflectance_TrueColor',
          'FORMAT': 'image/png',
          'TRANSPARENT': 'TRUE',
          'VERSION': '1.3.0',
          'TIME': currentFrame.wmsDate,
        },
        ratio: 1,
        crossOrigin: 'anonymous',
        projection: PROJ_3857,
      });

      // 2. Raster Source Filter to make black swath gaps transparent
      const rasterSource = new RasterSource({
        sources: [wmsSource],
        operation: (pixels) => {
          const pixel = pixels[0] as unknown as number[];
          // NASA GIBS uses pure black (0,0,0) for NoData in TrueColor WMS
          if (pixel[0] === 0 && pixel[1] === 0 && pixel[2] === 0) {
            pixel[3] = 0; // Set alpha to 0 (transparent)
          }
          return pixel;
        },
      });

      newLayer = new ImageLayer({
        source: rasterSource,
        opacity: 0,
        zIndex: 1,
      });
    } else {
      // Use ImageStatic for AI-interpolated local frames
      const extent: [number, number, number, number] =
        currentFrame.extent3857 ?? INDIA_EXTENT_3857;

      newLayer = new ImageLayer({
        source: new Static({
          url: currentFrame.imageUrl,
          imageExtent: extent,
          projection: PROJ_3857,
          crossOrigin: 'anonymous',
        }),
        opacity: 0,
        zIndex: 1,
      });

      // Auto-fit once only if using static frame (WMS is global)
      if (!hasAutoFit.current) {
        map.getView().fit(extent, { padding: [60, 60, 60, 60], duration: 800 });
        hasAutoFit.current = true;
      }
    }

    map.addLayer(newLayer);
    activeLayerRef.current = newLayer;

    // ── Smooth cross-fade ────────────────────────────────────────────────────
    let step = 0;
    const interval = CROSSFADE_MS / CROSSFADE_STEPS;

    fadeTimerRef.current = window.setInterval(() => {
      step++;
      const t = Math.min(step / CROSSFADE_STEPS, 1);
      const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      newLayer.setOpacity(eased * opacity);
      if (oldLayer) oldLayer.setOpacity((1 - eased) * opacity);

      if (step >= CROSSFADE_STEPS) {
        clearInterval(fadeTimerRef.current!);
        fadeTimerRef.current = null;
        newLayer.setOpacity(opacity);
        if (oldLayer) { map.removeLayer(oldLayer); prevLayerRef.current = null; }
      }
    }, interval);

    // ── Cloud mask ────────────────────────────────────────────────────────────
    if (cloudLayerRef.current) { map.removeLayer(cloudLayerRef.current); cloudLayerRef.current = null; }
    if (showClouds && currentFrame.cloudMaskUrl) {
      const extent: [number, number, number, number] = currentFrame.extent3857 ?? INDIA_EXTENT_3857;
      const cl = new ImageLayer({
        source: new Static({ url: currentFrame.cloudMaskUrl, imageExtent: extent, projection: PROJ_3857, crossOrigin: 'anonymous' }),
        opacity: 0.55,
        zIndex: 2,
      });
      map.addLayer(cl);
      cloudLayerRef.current = cl;
    }

    // ── Vector overlay ────────────────────────────────────────────────────────
    if (vectorLayerRef.current) { map.removeLayer(vectorLayerRef.current); vectorLayerRef.current = null; }
    if (showVectors && currentFrame.vectorsUrl) {
      const vl = new VectorLayer({
        source: new VectorSource({ url: currentFrame.vectorsUrl, format: new GeoJSON() }),
        style: vectorStyle,
        zIndex: 3,
      });
      map.addLayer(vl);
      vectorLayerRef.current = vl;
    }

    return () => {
      if (fadeTimerRef.current) { clearInterval(fadeTimerRef.current); fadeTimerRef.current = null; }
    };
  }, [currentFrame, showOverlay, showClouds, showVectors, opacity]);

  // ── Reset view ────────────────────────────────────────────────────────────
  const handleResetView = useCallback(() => {
    mapInstanceRef.current?.getView().animate({ center: DEFAULT_CENTER, zoom: DEFAULT_ZOOM, duration: 500 });
  }, []);

  return (
    <div className="relative w-full h-full bg-map-bg rounded overflow-hidden border">
      <div ref={mapRef} className="w-full h-full" />

      {/* HUD: current frame info */}
      <div className="absolute top-4 left-4 z-10 flex flex-col gap-2 pointer-events-none">
        <div className="bg-background/90 backdrop-blur-md border border-primary/20 rounded-lg p-4 shadow-xl min-w-[200px]">
          <div className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground mb-1">
            Satellite Sequence
          </div>
          <div className="text-base font-mono font-bold text-primary flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse flex-shrink-0" />
            {currentFrame?.timestamp}
          </div>
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${currentFrame?.isOriginal ? "bg-green-500/20 text-green-400" : "bg-blue-500/20 text-blue-400"}`}>
              {currentFrame?.isOriginal ? "NASA GIBS LIVE" : "AI INTERPOLATED"}
            </span>
            {!currentFrame?.isOriginal && showConfidence && (
              <span className="text-[10px] bg-primary/20 text-primary-foreground px-1.5 py-0.5 rounded font-bold">
                CONF: {Math.round((currentFrame?.confidence ?? 0) * 100)}%
              </span>
            )}
          </div>
        </div>
      </div>

      <MapControlsPanel
        onResetView={handleResetView}
        showOverlay={showOverlay} onToggleOverlay={onToggleOverlay}
        showConfidence={showConfidence} onToggleConfidence={onToggleConfidence}
        showClouds={showClouds} onToggleClouds={onToggleClouds}
        showVectors={showVectors} onToggleVectors={onToggleVectors}
      />
      <LegendPanel />
    </div>
  );
};

export default MapViewer;
