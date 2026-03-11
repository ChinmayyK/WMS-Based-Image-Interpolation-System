export const fetchFrames = async (bbox, startTime, endTime) => {
  const response = await fetch('http://localhost:8000/api/frames/fetch', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      bbox,
      start_time: startTime,
      end_time: endTime,
      layers: 'satellite-imagery',
    }),
  });
  return response.json();
};

export const interpolateFrames = async (frame1Id, frame2Id, steps) => {
  const response = await fetch('http://localhost:8000/api/frames/interpolate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      frame1_id: frame1Id,
      frame2_id: frame2Id,
      steps,
    }),
  });
  return response.json();
};
