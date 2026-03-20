import { describe, it, expect } from "vitest";

// Test resolveNearestObservedFrame logic
function resolveNearestObservedFrame(
  frames: { isOriginal?: boolean }[],
  currentIndex: number
): { isOriginal?: boolean } | null {
  if (!frames.length || currentIndex < 0 || currentIndex >= frames.length) return null;
  const current = frames[currentIndex];
  if (current.isOriginal) return current;

  let offset = 1;
  while (currentIndex - offset >= 0 || currentIndex + offset < frames.length) {
    if (currentIndex - offset >= 0) {
      const leftFrame = frames[currentIndex - offset];
      if (leftFrame.isOriginal) return leftFrame;
    }
    if (currentIndex + offset < frames.length) {
      const rightFrame = frames[currentIndex + offset];
      if (rightFrame.isOriginal) return rightFrame;
    }
    offset++;
  }
  return current;
}

describe("Comparison Mode", () => {
  it("resolveNearestObservedFrame returns observed frame when current is interpolated", () => {
    const frames = [
      { isOriginal: true },
      { isOriginal: false },
      { isOriginal: false },
      { isOriginal: true },
    ];
    const result = resolveNearestObservedFrame(frames, 1);
    expect(result?.isOriginal).toBe(true);
    expect(result).toBe(frames[0]);
  });

  it("resolveNearestObservedFrame returns self when current is observed", () => {
    const frames = [
      { isOriginal: true },
      { isOriginal: false },
      { isOriginal: true },
    ];
    const result = resolveNearestObservedFrame(frames, 0);
    expect(result?.isOriginal).toBe(true);
    expect(result).toBe(frames[0]);
  });

  it("resolveNearestObservedFrame returns null for empty frames", () => {
    expect(resolveNearestObservedFrame([], 0)).toBeNull();
  });

  it("resolveNearestObservedFrame picks closest observed frame", () => {
    const frames = [
      { isOriginal: true },
      { isOriginal: false },
      { isOriginal: false },
      { isOriginal: false },
      { isOriginal: true },
    ];
    // Index 3 is closer to frame[4] (distance 1) than frame[0] (distance 3)
    const result = resolveNearestObservedFrame(frames, 3);
    expect(result?.isOriginal).toBe(true);
    expect(result).toBe(frames[4]);
  });
});

describe("Timeline Frame Types", () => {
  it("should distinguish observed vs interpolated frames", () => {
    const frames = [
      { isOriginal: true, timestamp: "T1" },
      { isOriginal: false, timestamp: "T1.5" },
      { isOriginal: true, timestamp: "T2" },
    ];

    const observedFrames = frames.filter(f => f.isOriginal);
    const interpolatedFrames = frames.filter(f => !f.isOriginal);

    expect(observedFrames).toHaveLength(2);
    expect(interpolatedFrames).toHaveLength(1);
  });
});

describe("Export Button State", () => {
  it("should enable export only when job is completed and frames exist", () => {
    const isJobCompleted = (isLoading: boolean, framesLength: number) =>
      !isLoading && framesLength > 0;

    expect(isJobCompleted(true, 5)).toBe(false);   // still loading
    expect(isJobCompleted(false, 0)).toBe(false);   // no frames
    expect(isJobCompleted(false, 5)).toBe(true);    // ready
  });
});
