"""Portfolio dashboard: FastAPI over orch.py. Run with _orchestrator/dashboard/serve.cmd or:

    _orchestrator/.venv/Scripts/python -m uvicorn app:app --app-dir _orchestrator/dashboard --host 127.0.0.1 --port 8420
"""
from __future__ import annotations

import json
import html
from html.parser import HTMLParser
from urllib.parse import urlsplit
from contextlib import asynccontextmanager
import sys
from pathlib import Path

import markdown
from fastapi import FastAPI, HTTPException, Request
from typing import Literal
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import orch  # noqa: E402

import utilization
import steering
import overview
import dashboard_ops


@asynccontextmanager
async def lifespan(app):
    orch.init_all()
    factory = getattr(app.state, "sampler_factory", utilization.Sampler)
    sampler = factory(utilization.Store(orch.DB_PATH)) if factory else None
    if sampler:
        sampler.start()
    try:
        yield
    finally:
        if sampler:
            sampler.stop()


app = FastAPI(title="Portfolio Orchestrator", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.middleware("http")
async def guard(request: Request, call_next):
    # Custom header on every write forces a CORS preflight, which we never grant: other sites can't drive the board.
    if request.method == "POST" and request.headers.get("x-orchestrator") != "1":
        return JSONResponse({"error": "missing X-Orchestrator header"}, status_code=403)
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                               "img-src 'self' data:; object-src 'none'; base-uri 'none'")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


def render_md(text: str) -> str:
    md = markdown.Markdown(extensions=["fenced_code", "tables", "sane_lists"])
    # Agent-written markdown is untrusted: drop raw-HTML passthrough so it renders as text.
    md.preprocessors.deregister("html_block")
    md.inlinePatterns.deregister("html")
    class SafeLinks(HTMLParser):
        def __init__(self): super().__init__(convert_charrefs=False); self.parts=[]
        def handle_starttag(self,tag,attrs):
            cleaned=[]
            for key,value in attrs:
                if key.lower().startswith('on'): continue
                if key in ('href','src'):
                    compact=''.join(c for c in html.unescape(value or '') if ord(c)>32)
                    if urlsplit(compact).scheme.lower() not in ('','http','https','mailto'): continue
                cleaned.append(' '+key+'="'+html.escape(value or '',quote=True)+'"')
            self.parts.append('<'+tag+''.join(cleaned)+'>')
        def handle_endtag(self,tag): self.parts.append('</'+tag+'>')
        def handle_data(self,data): self.parts.append(data)
        def handle_entityref(self,name): self.parts.append('&'+name+';')
        def handle_charref(self,name): self.parts.append('&#'+name+';')
    clean=SafeLinks(); clean.feed(md.convert(text)); return ''.join(clean.parts)


def read_md(path: str | Path | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return render_md(p.read_text(encoding="utf-8", errors="replace"))


def state_version() -> str:
    paths = [orch.DB_PATH, orch.DB_PATH.with_name(orch.DB_PATH.name + "-wal"), orch.TASTE, orch.CONFIG]
    with orch.db() as con:
        generations = [con.execute("SELECT COALESCE(MAX(rowid),0) FROM metrics").fetchone()[0],
                       con.execute("SELECT COALESCE(SUM(generation),0) FROM lane_observations").fetchone()[0],
                       con.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]]
    return ":".join([*(str(p.stat().st_mtime_ns) if p.exists() else "0" for p in paths),*map(str,generations)])


@app.exception_handler(orch.OrchError)
async def orch_error(_: Request, exc: orch.OrchError):
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(steering.Conflict)
async def conflict_error(_: Request, exc: steering.Conflict):
    return JSONResponse({"error":str(exc)},status_code=409)


@app.exception_handler(utilization.CollectorError)
async def collector_error(_: Request, exc: utilization.CollectorError):
    return JSONResponse({"error":exc.reason,"outcome":"unknown"},status_code=503)


@app.get("/api/version")
def version():
    return {"version": state_version()}


@app.get("/api/utilization")
def utilization_api(range: Literal["24h", "7d", "14d"] = "24h"):
    try:
        return utilization.utilization_report(utilization.Store(orch.DB_PATH), range)
    except utilization.sqlite3.Error:
        return JSONResponse({"error": "db_busy"}, status_code=503)


@app.get("/api/state")
def state():
    with orch.db() as con:
        projects = orch.rows(con, "SELECT * FROM projects ORDER BY repo_name")
        inits = orch.rows(con, "SELECT * FROM initiatives ORDER BY updated_at DESC")
        events = orch.rows(con, "SELECT * FROM events ORDER BY id DESC LIMIT 60")
        latest = {r["project_name"]: r for r in orch.rows(
            con, "SELECT e.* FROM events e JOIN (SELECT project_name, MAX(id) mid FROM events "
                 "WHERE project_name IS NOT NULL AND actor != 'init' GROUP BY project_name) m ON e.id = m.mid")}
    for p in projects:
        p["focus"] = orch.active_focus(p)
        p["latest_activity"] = latest.get(p["repo_name"])
        p["has_dossier"] = (orch.DOSSIERS / p["repo_name"] / "DOSSIER.md").exists()
        p["has_audit"] = (orch.DOSSIERS / p["repo_name"] / "AUDIT_NOTES.md").exists()
    for i in inits:
        i["claim"] = orch.active_claim(i)
        plan = json.loads(i["execution_plan_json"]) if i["execution_plan_json"] else None
        i["plan_progress"] = None
        if plan:
            subs = plan.get("subtasks", [])
            i["plan_progress"] = {"done": sum(s.get("status") == "done" for s in subs), "total": len(subs),
                                  "review": plan.get("review", {}).get("status")}
        i.pop("execution_plan_json", None)
    cfg = orch.load_config()
    return {"version": state_version(), "projects": projects, "initiatives": inits, "events": events,
            "spotlight": orch.get_spotlight(), "aspects": sorted(orch.ASPECTS),
            "config": {"metrics": cfg["metrics"], "poll_seconds": cfg["dashboard"]["poll_seconds"],
                       "webhooks_enabled": cfg["webhooks"].get("enabled", False)},
            "enums": {"priorities": orch.PRIORITIES, "complexities": orch.COMPLEXITIES, "stages": orch.STAGES}}


@app.get("/api/projects/{name}")
def project(name: str):
    with orch.db() as con:
        p = orch.get_project(con, name)
        inits = orch.rows(con, "SELECT id, title, stage, category FROM initiatives WHERE project_name=? "
                               "ORDER BY id DESC", name)
        events = orch.rows(con, "SELECT * FROM events WHERE project_name=? ORDER BY id DESC LIMIT 25", name)
    d = orch.DOSSIERS / name
    scan = d / "SCAN.json"
    return {"project": p, "project_version":orch.project_version(p), "initiatives": inits, "events": events, "focus": orch.active_focus(p),
            "dossier_html": read_md(d / "DOSSIER.md"), "audit_html": read_md(d / "AUDIT_NOTES.md"),
            "scan": json.loads(scan.read_text(encoding="utf-8")) if scan.exists() else None}


class ProjectPatch(BaseModel):
    expected_version: str | None = None
    priority: str | None = None
    complexity: str | None = None


@app.post("/api/projects/{name}")
def patch_project(name: str, body: ProjectPatch):
    fields = {k: v for k, v in body.model_dump().items() if v is not None and k != "expected_version"}
    if not fields:
        raise HTTPException(400, "nothing to update")
    return orch.update_project(name, fields, "producer", body.expected_version)


@app.get("/api/initiatives/{iid}")
def initiative(iid: int):
    with orch.db() as con:
        i = orch.get_initiative(con, iid)
        events = orch.rows(con, "SELECT * FROM events WHERE initiative_id=? ORDER BY id DESC LIMIT 40", iid)
    d = orch.DESIGNS / f"{i['id']:04d}-{i['slug']}"
    plan = json.loads(i["execution_plan_json"]) if i["execution_plan_json"] else None
    return {
        "initiative": i, "events": events, "plan": plan, "version":steering.version(i), "plan_version":steering.version(i["execution_plan_json"]),
        "pitch_html": read_md(d / "PITCH.md") or render_md(i["pitch_summary"] or ""),
        "hld_html": read_md(i["hld_path"]), "lld_html": read_md(i["lld_path"]),
        "revisions_html": read_md(d / "REVISIONS.md"),
        "handoff_html": read_md(d / "IDE_HANDOFF.md"),
        "playtest_html": read_md(d / "PLAYTEST.md"),
        "handoff_notes_html": read_md(d / "HANDOFF_NOTES.md"),
        "diff": orch.diff_summary(i) if i["stage"] in ("building", "playtest", "done") else {},
        "next_stage": orch.ADVANCE.get(i["stage"]), "revise_to": orch.REVISE.get(i["stage"]),
        "claim": orch.active_claim(i),
    }


class Note(BaseModel):
    note: str = ""


@app.post("/api/initiatives/{iid}/advance")
def do_advance(iid: int, body: Note):
    out = orch.advance(iid, "producer", body.note)
    if orch._restart_after_ship:  # an orchestrator feature was merged: reload this server with the new code
        orch._restart_after_ship.clear()
        orch.restart_dashboard()
    return out


@app.post("/api/initiatives/{iid}/revise")
def do_revise(iid: int, body: Note):
    return orch.revise(iid, body.note, "producer")


@app.post("/api/initiatives/{iid}/reject")
def do_reject(iid: int, body: Note):
    return orch.reject(iid, body.note, "producer")


class SpotlightBody(BaseModel):
    aspect: str = "any"
    hours: float = 0
    note: str = ""
    mode: str = "graceful"


@app.post("/api/projects/{name}/spotlight")
def do_spotlight(name: str, body: SpotlightBody):
    return orch.spotlight(name, "producer", body.aspect, body.hours, body.note, body.mode)


@app.post("/api/spotlight/end")
def do_end_spotlight():
    return orch.end_spotlight("producer")


class FocusBody(BaseModel):
    hours: float = 0
    note: str = ""


@app.post("/api/projects/{name}/focus")
def do_focus(name: str, body: FocusBody):
    return orch.focus(name, "producer-chat", body.hours, body.note or "frontier focus session")


@app.post("/api/projects/{name}/unfocus")
def do_unfocus(name: str):
    return orch.unfocus(name, "producer")


class ClaimBody(BaseModel):
    note: str = ""
    hours: float = 24


@app.post("/api/initiatives/{iid}/claim")
def do_claim(iid: int, body: ClaimBody):
    return orch.claim(iid, "producer-chat", body.hours, body.note or "claimed from dashboard for a chat session")


@app.post("/api/initiatives/{iid}/release")
def do_release(iid: int, body: Note):
    return orch.release(iid, "producer", body.note)


@app.get("/api/taste")
def taste():
    return {"html": read_md(orch.TASTE)}


@app.get("/")
def index():
    return FileResponse(HERE / "static" / "index.html")


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.get('/api/overview')
def overview_api(project:str="",collection:str|None=None,offset:int=0,limit:int=200):
    if offset<0 or not 1<=limit<=200: raise HTTPException(422,"invalid page bounds")
    try:
        result=overview.paged(overview.snapshot(orch),project,collection,offset,limit)
        result['portfolio_version']=state_version()
        return result
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    except utilization.sqlite3.Error:
        return JSONResponse({'error':'db_busy'},status_code=503)

@app.get('/api/forecast/what-if')
def what_if_api(kind:Literal['initiative','project'],target:str):
    if len(target)>160: raise HTTPException(422,'invalid target')
    result=overview.snapshot(orch,bump=(kind,target))
    collection=result['forecast']['initiatives' if kind=='initiative' else 'projects']
    if target not in collection: raise HTTPException(404,'forecast target not found')
    return result['what_if']

class PriorityBody(BaseModel):
    priority: Literal['high','medium','low']
    expected_version: str

class ReorderBody(BaseModel):
    order: list[int]
    expected_plan_version: str

class LaneBody(BaseModel):
    enabled: bool
    expected_generation: int

class IdeaBody(BaseModel):
    title: str
    pitch: str
    category: Literal['fun_gameplay','visual_craft','optimization','tech_audacity','new_game']
    idempotency_key: str

@app.post('/api/initiatives/{iid}/priority')
def priority_api(iid:int,body:PriorityBody):
    return orch.set_initiative(iid,body.priority,body.expected_version,'producer')

@app.post('/api/initiatives/{iid}/subtasks/reorder')
def reorder_api(iid:int,body:ReorderBody):
    return orch.reorder_subtasks(iid,body.order,body.expected_plan_version,'producer')

@app.post('/api/lanes/{declaration}/control')
def lane_api(declaration:str,body:LaneBody):
    return orch.lane_control(declaration,body.enabled,body.expected_generation,'producer')

@app.post('/api/suggestions')
def idea_api(body:IdeaBody):
    title=body.title.strip(); pitch=body.pitch.strip()
    if not 1<=len(title)<=160 or not 1<=len(pitch)<=4000:
        raise HTTPException(422,'title 1..160 and pitch 1..4000 characters required')
    return orch.add_spark('000-orchestrator',body.category,title,pitch,'producer',idempotency=body.idempotency_key)

@app.get('/api/initiatives/{iid}/subtasks/{sid}')
def subtask_api(iid:int,sid:int,before:int|None=None):
    if before is not None and before<=0: raise HTTPException(422,'invalid cursor')
    return dashboard_ops.subtask_detail(orch,iid,sid,before)
