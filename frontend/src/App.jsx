import { useState } from 'react';
import MapViewer from './components/MapViewer';
import { fetchFrames, interpolateFrames } from './api/apiClient';
import './App.css';

function App() {
  const [status, setStatus] = useState('Idle');
  const [frames, setFrames] = useState([]);

  const handleFetch = async () => {
    setStatus('Fetching frames...');
    try {
      const res = await fetchFrames([0,0,10,10], '2023-01-01', '2023-01-02');
      if (res.status === 'success') {
        setFrames(res.fetched_frames);
        setStatus('Frames fetched successfully.');
      }
    } catch (e) {
      setStatus('Error fetching frames.');
    }
  };

  const handleInterpolate = async () => {
    if (frames.length < 2) {
      setStatus('Need at least 2 frames to interpolate.');
      return;
    }
    setStatus('Interpolating...');
    try {
      const res = await interpolateFrames(frames[0].id, frames[frames.length-1].id, 3);
      if (res.status === 'success') {
        setStatus(`Interpolated ${res.generated_frames.length} frames.`);
      }
    } catch (e) {
      setStatus('Error interpolating.');
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>WMS-Based Image Interpolation System</h1>
        <div className="controls">
          <button onClick={handleFetch}>Fetch WMS Frames</button>
          <button onClick={handleInterpolate}>Run Interpolation</button>
        </div>
        <div className="status-bar">
          <p>Status: {status}</p>
        </div>
      </header>
      <main>
        <MapViewer />
      </main>
    </div>
  );
}

export default App;
