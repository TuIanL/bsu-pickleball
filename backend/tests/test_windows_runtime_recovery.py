import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('fail_ready',[False,True])
def test_frontend_recovery_preserves_existing_backend_and_long_running_worker(tmp_path,monkeypatch,fail_ready):
    spec=importlib.util.spec_from_file_location('runtime_recovery',
        Path(__file__).resolve().parents[2]/'scripts/windows_runtime.py')
    runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
    class Process:
        def __init__(self,pid):self.pid=pid;self.terminated=False
        def create_time(self):return 30.
        def children(self,recursive=True):return []
        def terminate(self):self.terminated=True
    processes={i:Process(i) for i in (1,2,3)}
    existing={'backend':{'pid':1,'created':10.},'analysis-worker':{'pid':2,'created':20.},
        'frontend':{'pid':99,'created':0.}}
    monkeypatch.setattr(runtime,'records',lambda:existing)
    monkeypatch.setattr(runtime,'owned_process',lambda record:processes.get(record['pid']))
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(runtime,'RUNTIME',tmp_path)
    monkeypatch.setattr(runtime,'STATE',tmp_path/'state.json')
    (tmp_path/'logs').mkdir()
    monkeypatch.setattr(runtime,'check_assets',lambda env:pytest.fail('Frontend recovery must not initialize model runtimes'))
    monkeypatch.setattr(runtime.shutil,'which',lambda name:'node.exe')
    launched=[];ports=[]
    def spawn(command,**kwargs):launched.append(command);return processes[3]
    monkeypatch.setattr(runtime.subprocess,'Popen',spawn)
    # Popen is a test double; provide distinct Windows-only flag sentinels on POSIX.
    for bit,name in enumerate(('DETACHED_PROCESS','CREATE_NEW_PROCESS_GROUP','CREATE_BREAKAWAY_FROM_JOB')):
        monkeypatch.setattr(runtime.subprocess,name,1 << bit,raising=False)
    monkeypatch.setattr(runtime.psutil,'Process',lambda pid:processes[pid])
    monkeypatch.setattr(runtime.psutil,'wait_procs',lambda children,timeout:(children,[]))
    class Socket:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def bind(self,address):ports.append(address[1])
    monkeypatch.setattr(runtime.socket,'socket',lambda:Socket())
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
    def opener(*args):
        if fail_ready:raise RuntimeError('Simulated frontend readiness failure')
        return SimpleNamespace(open=lambda *a,**k:Response())
    monkeypatch.setattr(runtime.urllib.request,'build_opener',opener)
    if fail_ready:
        with pytest.raises(RuntimeError,match='readiness failure'):
            runtime.start({'PICKLEBALL_FRONTEND_PORT':'5187'})
    else:runtime.start({'PICKLEBALL_FRONTEND_PORT':'5187'})
    assert len(launched)==1 and 'frontend_runtime.py' in launched[0][1]
    assert ports==[5187]
    assert not processes[1].terminated and not processes[2].terminated
    assert processes[3].terminated is fail_ready
    saved=json.loads(runtime.STATE.read_text())
    assert saved['backend']==existing['backend'] and saved['analysis-worker']==existing['analysis-worker']
    assert ('frontend' in saved) is not fail_ready
