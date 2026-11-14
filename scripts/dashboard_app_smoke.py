"""Opt-in loopback app smoke. Starts and stops only its owned :8422 server."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

def listening():
    with socket.socket() as sock:
        sock.settimeout(.1)
        return sock.connect_ex(('127.0.0.1',8422))==0

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--home',required=True);args=ap.parse_args()
    if listening(): raise RuntimeError('port 8422 occupied; not touching the existing process')
    root=Path(__file__).resolve().parents[1]; logs=root/'logs'; logs.mkdir(exist_ok=True)
    curl=shutil.which('curl')
    if not curl: raise RuntimeError('curl missing')
    urls=['/','/static/overview.js','/static/navigation.js','/static/app.js','/api/state','/api/overview','/api/version','/api/projects/000-orchestrator','/api/initiatives/8','/api/initiatives/8/subtasks/3','/api/utilization']
    def get(path,timeout=10):
        return subprocess.run([curl,'--noproxy','*','-fsS','--max-time',str(timeout),'-o',os.devnull,'-w','%{http_code} %{size_download}','http://127.0.0.1:8422'+path],capture_output=True,text=True,timeout=timeout+2)
    report=[]
    with (logs/'build-8422.log').open('w') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--app-dir','dashboard','--host','127.0.0.1','--port','8422'],cwd=root,env={**os.environ,'ORCH_HOME':str(Path(args.home).resolve())},stdin=subprocess.DEVNULL,stdout=log,stderr=log)
        try:
            deadline=time.monotonic()+30
            while True:
                response=get('/api/version',1)
                if response.returncode==0: break
                if server.poll() is not None or time.monotonic()>deadline: raise RuntimeError('server startup failed; inspect owned build log')
                time.sleep(.2)
            for path in urls:
                response=get(path)
                if response.returncode: raise RuntimeError('GET failed: '+path)
                status,size=response.stdout.split()
                if status!='200': raise RuntimeError('unexpected status: '+path)
                report.append({'path':path,'status':int(status),'bytes':int(size)})
        finally:
            if os.name=='nt' and server.poll() is None:
                subprocess.run([str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32'/'taskkill.exe'),'/PID',str(server.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
            if server.poll() is None: server.terminate()
            server.wait(timeout=5)
    deadline=time.monotonic()+5
    while listening() and time.monotonic()<deadline: time.sleep(.1)
    if listening(): raise RuntimeError('test server listener did not close')
    print(json.dumps({'checks':report,'owned_server_stopped':True,'port_8422_closed':True,'browser':'blocked by browser navigation policy; visual/keyboard checks unverified'}))
    return 0
if __name__=='__main__': sys.exit(main())
