from dataclasses import asdict
from app.analysis_runtime.hashing import digest


class BallDetectionAdapter:
    def __init__(self, node, inputs, counters):
        from app.vision.detectors.ball_adapter import YoloBallDetectorAdapter
        self.model = YoloBallDetectorAdapter(node.model.assets["weights"].path,
                                            confidence_threshold=node.parameters["confidence"],
                                            device=node.model.configuration.get("device", "cpu"))
        self.threshold = node.parameters["confidence"]
        self.counters = counters

    def infer(self, source, row, frame):
        self.counters["model_executions"] += 1
        prefix = digest({"media": source.media_sha256, "view": source.view_id, "frame": row["source_frame_index"]})[:20]
        return {"candidates": [
            {"observation_id": prefix+":"+str(i), **asdict(value)}
            for i, value in enumerate(self.model.detect(frame, conf=self.threshold))
        ]}

    def close(self):
        self.model._model = None
