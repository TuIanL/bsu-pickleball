from app.analysis_runtime.hashing import digest


class PlayerDetectionAdapter:
    def __init__(self, node, inputs, counters):
        from app.vision.player_tracking_engine.person_detector import PersonDetector
        self.model = PersonDetector(node.model.assets["weights"].path,
                                    conf_threshold=node.parameters["confidence"],
                                    device=node.model.configuration.get("device", "cpu"))
        self.counters = counters

    def infer(self, source, row, frame):
        self.counters["model_executions"] += 1
        prefix = digest({"media": source.media_sha256, "view": source.view_id, "frame": row["source_frame_index"]})[:20]
        return {"subjects": [
            {"observation_id": prefix+":"+str(i), **value.model_dump(mode="json")}
            for i, value in enumerate(self.model.detect(frame))
        ]}

    def close(self):
        self.model._model = None
