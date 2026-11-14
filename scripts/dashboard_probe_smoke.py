"""Opt-in, real read-only subprocess checks; output is deliberately sanitized."""
import argparse
import datetime as dt
import json
import shutil
import sys
import lane_status
import utilization as u

def smoke():
    checks = {
        'openclaw_models':lambda: u.parse_openai(u.command_output('openclaw',['models','status'],20),dt.datetime.now(u.UTC)),
        'openclaw_cron':lane_status.collect_cron,
        'nvidia_smi':u.collect_gpu,
        'ollama_process':lambda: parse_ollama_cli(u.command_output('ollama',['ps'],5)),
        'ollama_api':u.collect_ollama,
    }
    results=[]
    for name,probe in checks.items():
        try:
            parsed=probe()
            results.append({'probe':name,'classification':'ok','parsed_count':len(parsed)})
        except Exception as exc:
            reason=exc.reason if isinstance(exc,u.CollectorError) else 'timeout' if isinstance(exc,(TimeoutError,u.subprocess.TimeoutExpired)) else 'parse_error' if isinstance(exc,(ValueError,TypeError,KeyError)) else 'unavailable'
            results.append({'probe':name,'classification':'missing_tool' if reason=='missing_tool' else 'failed','reason':reason})
    return results

def parse_ollama_cli(text):
    lines=text.strip().splitlines()
    if not lines or not all(x in lines[0].split() for x in ('NAME','ID','SIZE','PROCESSOR')):
        raise ValueError('unsupported ollama ps schema')
    return lines[1:]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--real',action='store_true'); args=ap.parse_args()
    if not args.real: ap.error('explicit --real required')
    results=smoke()
    print(json.dumps({'observed_at':u.stamp(dt.datetime.now(u.UTC)),'checks':results}))
    return int(any(r['classification']=='failed' for r in results))
if __name__=='__main__': sys.exit(main())
