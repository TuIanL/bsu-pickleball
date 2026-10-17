#!/usr/bin/env python3
"""真实短窗口验收；输出隔离到指定根，禁止调用完整产品 Pipeline。"""
from __future__ import annotations

import argparse
import faulthandler
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--secondary-source",type=Path)
    parser.add_argument("--sync",type=Path)
    parser.add_argument("--reference-camera",default="174")
    parser.add_argument("--secondary-camera",default="175")
    parser.add_argument("--start-ms",type=int,default=60000)
    parser.add_argument("--duration-ms",type=int,default=30000)
    parser.add_argument("--stride",type=int,default=30)
    parser.add_argument("--output-root",type=Path,required=True)
    args=parser.parse_args()
    faulthandler.dump_traceback_later(90, repeat=True)

    from app.core.config import get_settings
    from app.services.storage_service import StorageService
    from app.services.job_orchestration import JobStore, AnalysisWorkerRuntime
    from app.schemas.analysis import AnalysisUploadMetadata
    from app.analysis_runtime.contracts import AnalysisRequest
    from app.analysis_runtime.service import artifact_store, inspect_run, submit
    from app.analysis_runtime.sources import prepare_models, prepare_source

    root=args.output_root.resolve()
    root.mkdir(parents=True,exist_ok=True)
    base=get_settings()
    updates={key:root/"data"/key.removesuffix("_dir") for key in [
        "data_dir","uploads_dir","outputs_dir","calibrations_dir","recordings_dir",
        "match_state_candidate_dir","cameras_dir","tmp_dir","static_test_frames_dir"]}
    updates.update(database_path=root/"app.sqlite3",analysis_control_database_path=root/"control.sqlite3",
                   modular_artifacts_dir=root/"artifacts",modular_analysis_enabled=True)
    settings=base.model_copy(update=updates)
    jobs=JobStore(StorageService(settings))
    artifacts=artifact_store(jobs)
    evidence={"evidence_type":"real_inference","requested_window":{"start_ms":args.start_ms,"end_ms":args.start_ms+args.duration_ms},
              "sampling_stride":args.stride,"cases":[],"status":"running"}
    output=root/"evidence.json"
    def save():
        output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n")
    def forbidden(*a,**kw):
        raise AssertionError("真实模块验证触发了 legacy Pipeline/报告")
    worker=AnalysisWorkerRuntime(jobs,pipeline_factory=forbidden,on_completed=forbidden,worker_id="modular-acceptance")
    worker.settings=settings
    metadata=AnalysisUploadMetadata(fileName=args.source.name,matchTitle="真实模块短窗口验收",venue="",
                                    matchDate="2026-10-17",matchFormat="doubles",cameraAngle="unknown",athleteLabel="",level="")
    try:
        started=time.monotonic()
        evidence["models"]=prepare_models(artifacts,settings)
        source=prepare_source(artifacts,args.source,view_id="cam_1",camera_id=args.reference_camera,
                              require_pts=bool(args.secondary_source))
        second=prepare_source(artifacts,args.secondary_source,view_id="cam_2",camera_id=args.secondary_camera,require_pts=True) if args.secondary_source else None
        evidence["preparation_seconds"]=round(time.monotonic()-started,3)
        evidence["sources"]=[{"source_id":s.source_id,"media_sha256":s.media_sha256,"timing_sha256":s.timing_sha256,
                              "timing_authority":s.timing_authority} for s in [source,second] if s]
        save()
        print("准备完成",flush=True)
        def run_case(name,request):
            started=time.monotonic()
            job=submit(jobs,request,metadata)
            result=worker.run_job(job.id)
            manifest=inspect_run(jobs,job.id)
            evidence["cases"].append({"name":name,"job_id":job.id,"plan_hash":job.planHash,
                                      "wall_seconds":round(time.monotonic()-started,3),"manifest":manifest})
            save()
            print(name,result.canonicalStatus,flush=True)
            if result.canonicalStatus!="succeeded":
                raise RuntimeError("真实推理未通过: "+name)
            return manifest

        raw={"source_ids":[source.source_id],"targets":["ball.detect","pose.sequence"],
             "window":evidence["requested_window"],"sampling":{"stride":args.stride},"new_version":True}
        first=run_case("single_three_capabilities",AnalysisRequest.model_validate(raw))
        if any(run["counters"].get("model_executions",0)==0 for run in first["nodes"]):
            raise RuntimeError("三能力至少有一个未真实执行模型")
        cached=run_case("single_cached",AnalysisRequest.model_validate(raw))
        if any(r["status"]!="cached" or r["counters"].get("capture_opens")!=0 or r["counters"].get("model_executions")!=0 for r in cached["nodes"]):
            raise RuntimeError("全缓存验证未通过")
        changed=run_case("pose_parameter_only",AnalysisRequest.model_validate({**raw,"parameters":{"pose.sequence":{"confidence":0.45}}}))
        if any(r["status"]!="cached" for r in changed["nodes"] if r["capability_id"]!="pose.sequence"):
            raise RuntimeError("姿态窄重算验证未通过")
        if second:
            if not args.sync:
                raise RuntimeError("双摄验证需要真实同步快照")
            dual={**raw,"source_ids":[source.source_id,second.source_id],"targets":["ball.detect"],
                  "sync":json.loads(args.sync.read_text()),"reference_view_id":"cam_1"}
            result=run_case("dual_raw_ball",AnalysisRequest.model_validate(dual))
            if len(result["nodes"])!=1:
                raise RuntimeError("双摄 raw ball 引入了无关能力")
            payload=artifacts.payload(artifacts.manifest(result["artifacts"][0]["artifact_id"]).ref)
            views={row["view_id"] for row in payload["observations"] if row["mapping_status"]=="available"}
            if views!={"cam_1","cam_2"}:
                raise RuntimeError("没有两路有效的真实观测")
            cached=run_case("dual_cached",AnalysisRequest.model_validate(dual))
            if cached["nodes"][0]["status"]!="cached":
                raise RuntimeError("双摄缓存验证未通过")
        evidence["status"]="passed"
        save()
        print(str(output),flush=True)
        return 0
    except BaseException as exc:
        evidence["status"]="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        evidence["failure"]={"type":type(exc).__name__,"message":str(exc)}
        save()
        print(str(output),flush=True)
        return 2
    finally:
        faulthandler.cancel_dump_traceback_later()


if __name__=="__main__":
    raise SystemExit(main())
