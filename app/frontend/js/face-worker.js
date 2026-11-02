let anglesFromMatrix;

let model;
self.onmessage = async ({data}) => {
  try {
    if (data.type === "init") {
      const {FaceLandmarker, FilesetResolver} = await import("/vendor/mediapipe/vision_bundle.mjs");
      ({anglesFromMatrix} = await import("./face-capture-core.mjs"));
      const files = await FilesetResolver.forVisionTasks("/vendor/mediapipe/wasm");
      model = await FaceLandmarker.createFromOptions(files, {
        baseOptions: {modelAssetPath: "/api/face-assets/face_landmarker.task", delegate: "CPU"},
        runningMode: "VIDEO", numFaces: 2,
        outputFacialTransformationMatrixes: true,
        minFaceDetectionConfidence: 0.6, minFacePresenceConfidence: 0.6,
      });
      self.postMessage({type: "ready"});
    } else if (data.type === "frame") {
      try {
        const result = model.detectForVideo(data.image, data.timestamp);
        if (result.faceLandmarks.length !== 1) {
          self.postMessage({type: "frame", count: result.faceLandmarks.length});
          return;
        }
        const points = result.faceLandmarks[0];
        const xs = points.map(p => p.x), ys = points.map(p => p.y);
        self.postMessage({type: "frame", count: 1,
          angles: anglesFromMatrix(result.facialTransformationMatrixes[0].data),
          bbox: [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)],
        });
      } finally { data.image.close(); }
    }
  } catch (error) { self.postMessage({type: "error", message: error.message}); }
};
