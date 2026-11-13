"""Isolated, stdlib-only utilization telemetry. Never exports portfolio state."""
from __future__ import annotations
import contextlib
import datetime as dt
import json
import math
import sqlite3

UTC = dt.timezone.utc
WINDOWS = ('5h', 'weekly')
KEYS = {'gpu': ('util_pct', 'vram_used_mib', 'vram_total_mib', 'temperature_c', 'power_w'),
        'ollama': ('loaded_count',), 'openai': tuple('remaining_pct.' + w for w in WINDOWS),
        'anthropic': tuple('remaining_pct.' + w for w in WINDOWS)}
REASONS = {'unavailable', 'missing_tool', 'timeout', 'parse_error', 'db_busy', 'invalid_field', 'oversized'}
SCHEMA = """CREATE TABLE IF NOT EXISTS metrics (
 ts TEXT NOT NULL, source TEXT NOT NULL, key TEXT NOT NULL, value REAL, meta TEXT);
CREATE INDEX IF NOT EXISTS idx_metrics_source_key_ts ON metrics(source,key,ts);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts);"""


def utc(value):
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, dt.datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timezone-aware ISO timestamp required')
    return value.astimezone(UTC).replace(microsecond=0)


def stamp(value):
    return utc(value).isoformat(timespec='seconds')


def number(value, maximum=None):
    if isinstance(value, bool):
        raise ValueError('numeric value required')
    value = float(value)
    if not math.isfinite(value) or value < 0 or (maximum is not None and value > maximum):
        raise ValueError('value outside allowed range')
    return value


def metadata(meta):
    """Construct a small whitelist, never retain arbitrary collector output."""
    result = {}
    for key in ('manual', 'reset_estimated'):
        if key in meta:
            result[key] = meta[key] is True
    if 'resets_at' in meta:
        result['resets_at'] = stamp(meta['resets_at']) if meta['resets_at'] else None
    if 'reason' in meta:
        result['reason'] = meta['reason'] if meta['reason'] in REASONS else 'unavailable'
    if 'device_count' in meta:
        result['device_count'] = min(128, int(number(meta['device_count'])))
    if 'models' in meta:
        result['models'] = []
        for model in meta['models'][:32]:
            item = {'name': str(model.get('name', ''))[:160]}
            for key in ('size_vram',):
                try:
                    item[key] = number(model[key])
                except (KeyError, ValueError, TypeError):
                    item[key] = None
            try:
                item['expires_at'] = stamp(model['expires_at']) if model.get('expires_at') else None
            except (ValueError, TypeError):
                item['expires_at'] = None
            result['models'].append(item)
    return result


class Store:
    def __init__(self, path, clock=None):
        self.path = str(path)
        self.clock = clock or (lambda: dt.datetime.now(UTC))

    @contextlib.contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=.25)
        con.row_factory = sqlite3.Row
        try:
            con.execute('PRAGMA busy_timeout=250')
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def initialize(self):
        with self.connect() as con:
            con.executescript(SCHEMA)

    def insert(self, source, rows, observed_at=None):
        if source not in KEYS:
            raise ValueError('unsupported source')
        ts = stamp(observed_at or self.clock())
        batch = []
        for row in rows:
            key = row['key']
            if key not in (*KEYS[source], 'error'):
                raise ValueError('unsupported metric')
            value = row.get('value')
            if value is not None:
                value = number(value, 100 if 'pct' in key else None)
            batch.append((ts, source, key, value, json.dumps(metadata(row.get('meta', {})), separators=(',', ':'))))
        if len({r[2] for r in batch}) != len(batch):
            raise ValueError('duplicate metric')
        with self.connect() as con:
            con.executemany('INSERT INTO metrics(ts,source,key,value,meta) VALUES (?,?,?,?,?)', batch)
        return ts

    def quota_snapshot(self, provider, windows, used, resets):
        if provider != 'anthropic' or not 1 <= len(windows) <= 2:
            raise ValueError('anthropic requires one or two windows')
        if len(windows) != len(used) or len(used) != len(resets) or len(set(windows)) != len(windows):
            raise ValueError('window/used-pct/resets-at must have equal lengths and unique windows')
        rows = []
        for window, value, reset in zip(windows, used, resets):
            if window not in WINDOWS:
                raise ValueError('unsupported window')
            rows.append({'key': 'remaining_pct.' + window, 'value': 100 - number(value, 100),
                         'meta': {'manual': True, 'resets_at': stamp(reset)}})
        observed = self.insert(provider, rows)
        return {'provider': provider, 'observed_at': observed,
                'windows': {w: {'remaining_pct': r['value'], **r['meta']} for w, r in zip(windows, rows)}}

    def prune(self):
        cutoff = stamp(utc(self.clock()) - dt.timedelta(days=14))
        with self.connect() as con:
            return con.execute('DELETE FROM metrics WHERE rowid IN '
                               '(SELECT rowid FROM metrics WHERE ts < ? LIMIT 5000)', (cutoff,)).rowcount


# Collectors use only fixed local endpoints/arguments. All parsers are pure.
import csv
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import uuid


def parse_gpu(text):
    devices = list(csv.reader(io.StringIO(text.strip())))
    if not devices or len(devices) > 128 or any(len(r) != 5 for r in devices):
        raise ValueError('invalid GPU CSV')
    rows = []
    for index, key in enumerate(KEYS['gpu']):
        values = []
        for device in devices:
            try:
                values.append(number(device[index].strip(), 100 if key == 'util_pct' else None))
            except (ValueError, TypeError):
                values.append(None)
        value = None if None in values else (max(values) if index in (0, 3) else sum(values))
        rows.append({'key': key, 'value': value, 'meta': {'device_count': len(devices),
                     **({'reason': 'invalid_field'} if value is None else {})}})
    return rows


def parse_ollama(text):
    data = json.loads(text)
    models = data.get('models') if isinstance(data, dict) else None
    if not isinstance(models, list) or any(not isinstance(m, dict) or not isinstance(m.get('name'), str) for m in models):
        raise ValueError('invalid model list')
    return [{'key': 'loaded_count', 'value': len(models), 'meta': metadata({'models': models})}]


def parse_openai(text, observed_at):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    line = next((line for line in text.splitlines() if re.search(r'openai(?:-codex)?\s+usage:', line, re.I)), '')
    rows = []
    for window, label in (('5h', '5h'), ('weekly', 'Week(?:ly)?')):
        match = re.search(r'\b' + label + r'\s*:?\s*(\d+(?:\.\d+)?)%\s+left(?:\s*[⏱·|,-]?\s*resets?\s+(?P<duration>(?:\d+\s*[dhm]\s*)+))?', line, re.I)
        if not match:
            continue
        value = number(match.group(1), 100)
        seconds = sum(int(n) * {'d':86400,'h':3600,'m':60}[unit.lower()]
                      for n, unit in re.findall(r'(\d+)\s*([dhm])', match.group('duration') or '', re.I))
        rows.append({'key': 'remaining_pct.' + window, 'value': value,
                     'meta': {'reset_estimated': True, 'resets_at': stamp(utc(observed_at) + dt.timedelta(seconds=seconds)) if seconds else None}})
    if not rows:
        raise ValueError('usage line unavailable')
    return rows


class CollectorError(Exception):
    def __init__(self, reason):
        self.reason = reason


def command_output(name, args, timeout):
    executable = shutil.which(name)
    if not executable and name == 'nvidia-smi':
        fallback = Path('C:/Windows/System32/nvidia-smi.exe')
        executable = str(fallback) if fallback.is_file() else None
    if not executable:
        raise CollectorError('missing_tool')
    executable = str(Path(executable).resolve())
    argv = [executable, *args]
    if os.name == 'nt' and executable.lower().endswith(('.cmd', '.bat')):
        # Only fixed arguments and a resolved path; reject cmd metacharacters even in PATH entries.
        if any(c in executable for c in '&|<>^%!"\r\n'):
            raise CollectorError('missing_tool')
        comspec = str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32' / 'cmd.exe')
        argv = [comspec, '/d', '/s', '/c', '""' + executable + '" ' + ' '.join(args) + '"']
    result = subprocess.run(argv, shell=False, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise CollectorError('unavailable')
    return result.stdout


def collect_gpu():
    return parse_gpu(command_output('nvidia-smi', ['--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw', '--format=csv,noheader,nounits'], 5))


def collect_ollama():
    # Explicit no-proxy opener: even environment proxy settings must not redirect loopback telemetry.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:11434/api/ps', timeout=3) as response:
        body = response.read(1024*1024 + 1)
    if len(body) > 1024*1024:
        raise CollectorError('oversized')
    return parse_ollama(body)


class Sampler:
    LEASE = 'utilization_sampler_lease_v1'
    INTERVALS = {'gpu':60, 'ollama':60, 'openai':600, 'prune':3600}

    def __init__(self, store, collectors=None, monotonic=time.monotonic):
        self.store = store
        self.owner = uuid.uuid4().hex
        self.monotonic = monotonic
        self.collectors = collectors if collectors is not None else {
            'gpu':collect_gpu, 'ollama':collect_ollama,
            'openai':lambda: parse_openai(command_output('openclaw', ['models','status'], 20), store.clock())}
        self.stop_event = threading.Event()
        self.thread = None
        self.next_tick = 0

    def claim(self, source=None, release=False):
        now = utc(self.store.clock())
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT value FROM settings WHERE key=?', (self.LEASE,)).fetchone()
            data = json.loads(row[0]) if row else {'attempts':{}}
            if data.get('owner') not in (None, self.owner) and utc(data['expires_at']) > now:
                return False
            if release:
                if data.get('owner') != self.owner:
                    return False
                data['owner'] = None
            else:
                data['owner'] = self.owner
            data['expires_at'] = stamp(now + dt.timedelta(seconds=120))
            due = True
            if source:
                last = data['attempts'].get(source)
                due = not last or (now - utc(last)).total_seconds() >= self.INTERVALS[source]
                if due:
                    data['attempts'][source] = stamp(now)
            con.execute('INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)', (self.LEASE, json.dumps(data)))
            return due

    def tick(self):
        if self.monotonic() < self.next_tick:
            return
        self.next_tick = self.monotonic() + 10  # renew comfortably within 30 seconds
        try:
            if not self.claim():
                return
        except (sqlite3.Error, ValueError, KeyError):
            return
        for source in self.INTERVALS:
            if self.stop_event.is_set():
                break
            try:
                if not self.claim(source):
                    continue
                if source == 'prune':
                    self.store.prune()
                else:
                    observed = self.store.clock()
                    try:
                        rows = self.collectors[source]()
                        self.store.insert(source, rows, observed)
                    except Exception as exc:
                        reason = ('timeout' if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)) else
                                  exc.reason if isinstance(exc, CollectorError) else
                                  'parse_error' if isinstance(exc, (ValueError, TypeError, KeyError)) else 'unavailable')
                        self.store.insert(source, [{'key':'error','value':1,'meta':{'reason':reason}}], observed)
            except Exception:
                # Busy database/failed source never suppresses the other source's next attempt.
                continue

    def run(self):
        try:
            while not self.stop_event.is_set():
                self.tick()
                self.stop_event.wait(1)
        finally:
            try:
                self.claim(release=True)
            except (sqlite3.Error, ValueError, KeyError):
                pass

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, name='utilization-sampler', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)
