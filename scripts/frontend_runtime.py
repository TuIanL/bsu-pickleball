"""Keep the frontend's parent process and log its actual exit code."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True,type=int)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    node=shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is not on PATH')
    env={**os.environ,'CI':'true'}
    child=subprocess.Popen([node,str(root/'node_modules/vite/bin/vite.js'),
        '--host','127.0.0.1','--port',str(args.port),'--strictPort'],cwd=root,env=env,
        stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    print(datetime.now().isoformat(),'frontend child started',child.pid,flush=True)
    code=child.wait()
    print(datetime.now().isoformat(),'frontend child exited',child.pid,'code',code,flush=True)
    raise SystemExit(code)


if __name__=='__main__':
    main()
