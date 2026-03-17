import { useEffect, useRef, useCallback } from "react";
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
}

// Bounding box for the satellite overlay (EPSG:3857) - Covers the Indian subcontinent more accurately
const OVERLAY_EXTENT = [7500000, 700000, 11000000, 4300000];
const DEFAULT_CENTER: [number, number] = [9250000, 2500000];
const DEFAULT_ZOOM = 4.5;

// Define a style for the optical flow motion vectors
const vectorStyle = new Style({
  stroke: new Stroke({
    color: "rgba(255, 255, 0, 0.8)", // Yellow arrows
    width: 2,
  }),
});

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
}: MapViewerProps) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<Map | null>(null);

  // Layer Refs
  const overlayLayerRef = useRef<ImageLayer<Static> | null>(null);
  const previousOverlayLayerRef = useRef<ImageLayer<Static> | null>(null);
  const cloudLayerRef = useRef<ImageLayer<Static> | null>(null);
  const vectorLayerRef = useRef<VectorLayer<VectorSource> | null>(null);

  // Initialize map with OSM base layer
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const map = new Map({
      target: mapRef.current,
      layers: [
        new TileLayer({
          source: new OSM(),
        }),
      ],
      view: new View({
        center: DEFAULT_CENTER,
        zoom: DEFAULT_ZOOM,
        projection: getProjection("EPSG:3857")!,
      }),
    });

    mapInstanceRef.current = map;

    return () => {
      map.setTarget(undefined);
      mapInstanceRef.current = null;
    };
  }, []);

  // Frame update logic with seamless cross-fading
  useEffect(() => {
    if (!mapInstanceRef.current || !currentFrame) return;
    const map = mapInstanceRef.current;

    // 1. Satellite Base Overlay handling (with cross-fade)
    if (showOverlay && currentFrame.imageUrl) {
      // Create new layer
      const newImageLayer = new ImageLayer({
        source: new Static({
          url: currentFrame.imageUrl,
          imageExtent: OVERLAY_EXTENT,
          projection: getProjection("EPSG:3857")!,
        }),
        opacity: 0, // Start invisible for fade-in
        className: "transition-opacity duration-300", // CSS transition
      });

      map.addLayer(newImageLayer);

      // Trigger fade in on next frame
      setTimeout(() => {
        newImageLayer.setOpacity(opacity);
      }, 50);

      // Fade out and remove the old layer
      if (overlayLayerRef.current) {
        const oldLayer = overlayLayerRef.current;
        oldLayer.setOpacity(0);
        setTimeout(() => {
          map.removeLayer(oldLayer);
        }, 300); // Remove after transition finishes
      }

      overlayLayerRef.current = newImageLayer;
    } else if (!showOverlay && overlayLayerRef.current) {
      map.removeLayer(overlayLayerRef.current);
      overlayLayerRef.current = null;
    }

    // 2. Cloud Mask Layer handling
    if (cloudLayerRef.current) {
      map.removeLayer(cloudLayerRef.current);
      cloudLayerRef.current = null;
    }
    if (showClouds && currentFrame.cloudMaskUrl) {
      const newCloudLayer = new ImageLayer({
        source: new Static({
          url: currentFrame.cloudMaskUrl,
          imageExtent: OVERLAY_EXTENT,
          projection: getProjection("EPSG:3857")!,
        }),
        opacity: 0.8,
      });
      map.addLayer(newCloudLayer);
      cloudLayerRef.current = newCloudLayer;
    }

    // 3. Motion Vectors Layer handling
    if (vectorLayerRef.current) {
      map.removeLayer(vectorLayerRef.current);
      vectorLayerRef.current = null;
    }
    if (showVectors && currentFrame.vectorsUrl) {
      const vectorSource = new VectorSource({
        url: currentFrame.vectorsUrl,
        format: new GeoJSON(),
      });
      const newVectorLayer = new VectorLayer({
        source: vectorSource,
        style: vectorStyle,
        opacity: 0.9,
      });
      map.addLayer(newVectorLayer);
      vectorLayerRef.current = newVectorLayer;
    }
  }, [currentFrame, showOverlay, showClouds, showVectors]);

  // Update overall opacity gracefully
  useEffect(() => {
    if (overlayLayerRef.current) {
      overlayLayerRef.current.setOpacity(opacity);
    }
  }, [opacity]);

  const handleResetView = useCallback(() => {
    if (!mapInstanceRef.current) return;
    const view = mapInstanceRef.current.getView();
    view.animate({
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      duration: 500,
    });
  }, []);

  return (
    <div className="relative w-full h-full bg-map-bg rounded overflow-hidden border">
      <div ref={mapRef} className="w-full h-full" />

      <div className="absolute top-3 left-3 z-10 flex flex-col gap-1">
        <div className="bg-card/85 border rounded px-3 py-1.5 text-xs font-mono text-muted-foreground">
          Base Layer: OpenStreetMap
        </div>
        {currentFrame && showOverlay && (
          <div className="flex flex-col gap-1">
            <div
              className={`border rounded px-3 py-1.5 text-xs font-mono transition-colors ${
                currentFrame.isOriginal
                  ? "bg-green-500/20 border-green-500/40 text-green-300"
                  : "bg-blue-500/20 border-blue-500/40 text-blue-300"
              }`}
            >
              Overlay: {currentFrame.timestamp} ({currentFrame.isOriginal ? "Original" : "Generated"})
            </div>
            {!currentFrame.isOriginal && showConfidence && (
              <div className="bg-blue-500/20 border border-blue-500/40 rounded px-3 py-1.5 text-xs font-mono text-blue-300 animate-pulse">
                Confidence: {Math.round(currentFrame.confidence * 100)}%
              </div>
            )}
          </div>
        )}
      </div>

      <MapControlsPanel
        onResetView={handleResetView}
        showOverlay={showOverlay}
        onToggleOverlay={onToggleOverlay}
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
