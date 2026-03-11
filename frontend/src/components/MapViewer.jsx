import { useEffect, useRef, useState } from 'react';
import 'ol/ol.css';
import Map from 'ol/Map';
import View from 'ol/View';
import TileLayer from 'ol/layer/Tile';
import OSM from 'ol/source/OSM';

const MapViewer = () => {
  const mapElement = useRef(null);
  const [map, setMap] = useState(null);

  useEffect(() => {
    if (!mapElement.current) return;

    const initialMap = new Map({
      target: mapElement.current,
      layers: [
        new TileLayer({
          source: new OSM()
        })
      ],
      view: new View({
        center: [0, 0],
        zoom: 2
      })
    });

    setMap(initialMap);

    return () => {
      initialMap.setTarget(null);
    };
  }, []);

  return (
    <div style={{ height: '500px', width: '100%', border: '1px solid #ccc' }} ref={mapElement} className="map-container">
    </div>
  );
};

export default MapViewer;
