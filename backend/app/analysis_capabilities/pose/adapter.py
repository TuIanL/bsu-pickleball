from app.analysis_runtime.hashing import AnalysisRuntimeError


class PoseSequenceAdapter:
    def __init__(self, node, inputs, counters):
        from app.vision.pose.rtmpose26_adapter import RTMPose26Adapter
        config = node.model.assets.get("config")
        if config is None:
            raise AnalysisRuntimeError("model_environment", "姿态配置尚未准备")
        self.model = RTMPose26Adapter(
            config.path, node.model.assets["weights"].path,
            device=node.model.configuration.get("device", "cpu"),
            conf_threshold=node.parameters["confidence"], conf_exit_threshold=node.parameters["exit_confidence"])
        self.counters = counters
        self.people = {(row["view_id"],row["source_frame_index"]):row.get("subjects",[])
                       for row in inputs["players"]["observations"]}

    def infer(self, source, row, frame):
        from app.schemas.tracking import FrameDetection
        boxes = self.people.get((source.view_id,row["source_frame_index"]),[])
        subjects = [FrameDetection(
            frame_index=row["source_frame_index"], timestamp_seconds=row["canonical_time_ms"]/1000,
            bbox=box["bbox"], confidence=box["confidence"], track_id=box["observation_id"],
            source_width=source.width,source_height=source.height) for box in boxes]
        self.model._visible_states.clear()
        if subjects:
            self.counters["model_executions"] += 1
        result = self.model.estimate_frame(frame,subjects,row["source_frame_index"],row["canonical_time_ms"]/1000)
        return {"subjects":[
            {"observation_id":subject.track_id,"subject_scope":"observation","bbox":subject.bbox,
             "confidence":subject.confidence,
             "keypoints":[point.model_dump(mode="json") for point in subject.keypoints]}
            for subject in result.subjects]}

    def close(self):
        self.model._visible_states.clear()
        self.model._model = None
