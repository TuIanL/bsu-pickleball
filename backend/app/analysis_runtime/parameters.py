"""参数声明的 JSON Schema 子集验证，不引入视觉或额外工作流依赖。"""
from __future__ import annotations
import math
from app.analysis_runtime.hashing import AnalysisRuntimeError


def validate(value, schema: dict, path: str):
    kind = schema.get("type")
    kinds = kind if isinstance(kind, list) else [kind]
    checks = {
        "null": lambda v: v is None,
        "boolean": lambda v: isinstance(v, bool),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int,float)) and not isinstance(v,bool) and math.isfinite(v),
        "string": lambda v: isinstance(v,str),
        "array": lambda v: isinstance(v,(list,tuple)),
        "object": lambda v: isinstance(v,dict),
    }
    if kind is not None and not any(checks.get(k, lambda _v: False)(value) for k in kinds):
        raise AnalysisRuntimeError("invalid_parameter", path)
    if "enum" in schema and not any(value==item and isinstance(value,bool)==isinstance(item,bool) for item in schema["enum"]):
        raise AnalysisRuntimeError("invalid_parameter", path)
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        if not math.isfinite(value) or ("minimum" in schema and value<schema["minimum"]) or ("maximum" in schema and value>schema["maximum"]):
            raise AnalysisRuntimeError("invalid_parameter", path)
    if isinstance(value,dict):
        properties = schema.get("properties",{})
        if not set(schema.get("required",[])) <= set(value):
            raise AnalysisRuntimeError("parameter_required", path)
        if schema.get("additionalProperties",True) is False and set(value)-set(properties):
            raise AnalysisRuntimeError("unknown_parameter", path)
        for key,item in value.items():
            if key in properties:
                validate(item,properties[key],path+":"+key)
    if isinstance(value,(list,tuple)) and "items" in schema:
        for index,item in enumerate(value):
            validate(item,schema["items"],path+":"+str(index))


def parameters_for(implementation, extra: dict) -> dict:
    defaults = implementation.parameter_defaults
    declared = implementation.parameter_schema
    if declared.get("type") == "object":
        schema = declared
    else:
        properties = dict(declared)
        for key,value in defaults.items():
            if key not in properties:
                kind = ("boolean" if isinstance(value,bool) else "integer" if isinstance(value,int)
                        else "number" if isinstance(value,float) else "string" if isinstance(value,str)
                        else "object" if isinstance(value,dict) else "array" if isinstance(value,(list,tuple)) else "null")
                properties[key] = {"type":kind}
        schema = {"type":"object","properties":properties,"additionalProperties":False}
    result = {**defaults, **extra}
    validate(result,schema,implementation.capability_id)
    return result
