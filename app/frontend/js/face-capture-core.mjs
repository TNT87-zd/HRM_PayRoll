// Shared pure functions: no camera, DOM, or model dependencies.
export const POSES = ["front", "left", "right", "up", "down"];
export const LABELS = {front: "Nhìn thẳng", left: "Quay sang trái", right: "Quay sang phải", up: "Ngước nhẹ", down: "Cúi nhẹ"};

export function anglesFromMatrix(data) {
  // MediaPipe Web serializes the matrix in column-major order.
  const r = (row, column) => data[column * 4 + row];
  const degrees = 180 / Math.PI;
  return {
    yaw: Math.atan2(-r(2, 0), Math.hypot(r(0, 0), r(1, 0))) * degrees,
    pitch: Math.atan2(r(2, 1), r(2, 2)) * degrees,
    roll: Math.atan2(r(1, 0), r(0, 0)) * degrees,
  };
}

export function relativePose(pose, baseline) {
  return Object.fromEntries(["yaw", "pitch", "roll"].map(key => [key, pose[key] - (baseline?.[key] || 0)]));
}

export function classifyPose(pose) {
  if (Math.abs(pose.roll) > 12) return null;
  if (Math.abs(pose.yaw) <= 10 && Math.abs(pose.pitch) <= 10) return "front";
  if (Math.abs(pose.pitch) <= 12 && Math.abs(pose.yaw) >= 15 && Math.abs(pose.yaw) <= 32) return pose.yaw > 0 ? "left" : "right";
  if (Math.abs(pose.yaw) <= 12 && Math.abs(pose.pitch) >= 10 && Math.abs(pose.pitch) <= 22) return pose.pitch > 0 ? "down" : "up";
  return null;
}

export function diverse(a, b) {
  if (Math.abs(a.captured_at - b.captured_at) < 0.3) return false;
  let difference = 0;
  for (let i = 0; i < a.fingerprint.length; i++) difference += Math.abs(a.fingerprint[i] - b.fingerprint[i]);
  difference /= a.fingerprint.length;
  const delta = Math.abs(a.angles.yaw - b.angles.yaw) + Math.abs(a.angles.pitch - b.angles.pitch);
  return difference >= 1.5 || delta >= 3;
}

export function bestPair(candidates, pose, locked = []) {
  const ranked = candidates.filter(c => !locked.some(s => s.sample_id === c.sample_id)).sort((a, b) => b.score - a.score);
  const pool = [...locked, ...ranked];
  for (let i = 0; i < pool.length; i++) for (let j = i + 1; j < pool.length; j++) {
    const pair = [pool[i], pool[j]];
    if (!locked.every(s => pair.includes(s)) || !diverse(...pair)) continue;
    if (pose === "front" && classifyPose(relativePose(pair[1].absolute, pair[0].absolute)) !== "front") continue;
    return pair;
  }
  return null;
}

export function faceQuality(canvas, bbox) {
  const [x, y, width, height] = bbox;
  if (Math.min(width, height) < 100) return {valid: false, reason: "Đến gần camera hơn"};
  if (x < 2 || y < 2 || x + width > canvas.width - 2 || y + height > canvas.height - 2) return {valid: false, reason: "Đưa trọn khuôn mặt vào khung"};
  const sample = new OffscreenCanvas(128, 128);
  const context = sample.getContext("2d", {willReadFrequently: true});
  context.drawImage(canvas, x, y, width, height, 0, 0, 128, 128);
  const pixels = context.getImageData(0, 0, 128, 128).data;
  const gray = new Float32Array(128 * 128);
  let brightness = 0, dark = 0, bright = 0;
  for (let i = 0; i < gray.length; i++) {
    gray[i] = 0.299 * pixels[i * 4] + 0.587 * pixels[i * 4 + 1] + 0.114 * pixels[i * 4 + 2];
    brightness += gray[i]; dark += gray[i] < 15; bright += gray[i] > 245;
  }
  brightness /= gray.length;
  if (brightness < 40 || dark / gray.length > 0.45) return {valid: false, reason: "Cần thêm ánh sáng phía trước mặt"};
  if (brightness > 225 || bright / gray.length > 0.45) return {valid: false, reason: "Tránh ánh sáng quá mạnh"};
  let sum = 0, squares = 0, count = 0;
  for (let row = 1; row < 127; row++) for (let column = 1; column < 127; column++) {
    const i = row * 128 + column;
    const lap = gray[i - 1] + gray[i + 1] + gray[i - 128] + gray[i + 128] - 4 * gray[i];
    sum += lap; squares += lap * lap; count++;
  }
  const blur = squares / count - (sum / count) ** 2;
  if (blur < 20) return {valid: false, reason: "Giữ yên để ảnh rõ nét"};
  const fingerprintCanvas = new OffscreenCanvas(32, 32);
  const fp = fingerprintCanvas.getContext("2d", {willReadFrequently: true});
  fp.drawImage(sample, 0, 0, 32, 32);
  const data = fp.getImageData(0, 0, 32, 32).data;
  const fingerprint = Array.from({length: 1024}, (_, i) => Math.round(0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2]));
  return {valid: true, fingerprint, score: 0.6 * Math.min(blur / 150, 1) + 0.4 * (1 - Math.abs(brightness - 128) / 128)};
}
