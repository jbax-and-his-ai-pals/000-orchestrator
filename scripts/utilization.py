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
