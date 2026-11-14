"""Producer-selected task permissions for each scheduled model. No scheduler side effects."""
import json
import steering

TASKS = {
    'passive': ('Background maintenance', 'Scans, safe smoke tests and dossier refreshes.'),
    'planning': ('Planning', 'HLDs for Claude; LLDs and execution plans for Codex.'),
    'coding': ('Coding', 'Assigned implementation subtasks; Gemma capability limits still apply.'),
    'review': ('Reviews', 'Finished-branch review for Codex; read-only deep reads for Gemini.'),
    'ideas': ('Ideas', 'New sparks, pitch revisions and optimization proposals.'),
    'issues': ('Issue investigation', 'Investigate bottlenecks and propose fixes; also requires issue autosolve.'),
}
MODELS = {
    'orch:scout-gemma': ('Gemma', 'scout', ('passive', 'coding')),
    'orch:architect-claude': ('Claude Sonnet', 'architect', ('planning', 'coding', 'ideas', 'issues')),
    'orch:architect-claude-opus': ('Claude Opus', 'architect_high', ('planning',)),
    'orch:planner-codex': ('Codex', 'planner', ('planning', 'coding', 'review', 'ideas', 'issues')),
    'orch:reviewer-gemini': ('Gemini', 'reviewer', ('review',)),
}
QUEUES = {'scout': 'orch:scout-gemma', 'architect': 'orch:architect-claude',
          'architect-high': 'orch:architect-claude-opus', 'planner': 'orch:planner-codex',
          'reviewer': 'orch:reviewer-gemini'}
ACTORS = {'scout-gemma': 'scout', 'gemma': 'scout', 'scout': 'scout',
          'planner-codex': 'planner', 'planner': 'planner',
          'architect-claude': 'architect', 'architect': 'architect', 'reviewer-gemini': 'reviewer'}


def defaults(declaration):
    # Preserve the producer's passive-only Gemma mode on first use.
    return {task: task != 'coding' if declaration == 'orch:scout-gemma' else True
            for task in MODELS[declaration][2]}


def read(con):
    row = con.execute("SELECT value FROM settings WHERE key='model_task_permissions'").fetchone()
    saved = json.loads(row['value']) if row else {}
    return {key: {**defaults(key), **saved.get(key, {})} for key in MODELS}


def version(tasks):
    return steering.version(tasks)


def update(orch, declaration, changes, expected, actor):
    if actor in orch.AGENT_ACTORS:
        raise orch.OrchError('only the producer or an interactive session may change model tasks')
    if declaration not in MODELS or not isinstance(changes, dict) or not changes:
        raise orch.OrchError('unknown model or empty task changes')
    if any(k not in MODELS[declaration][2] or type(v) is not bool for k, v in changes.items()):
        raise orch.OrchError('unsupported task or non-boolean permission')
    if not isinstance(expected, str) or not expected:
        raise orch.OrchError('expected task version is required')
    with orch.db(write=True) as con:
        policies = read(con)
        steering.expect(version(policies[declaration]), expected)
        policies[declaration].update(changes)
        con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES ('model_task_permissions',?)",
                    (json.dumps(policies),))
        orch.log_event(con, actor, 'model_tasks', declaration + ': ' + json.dumps(changes),
                       details={'declaration': declaration, 'tasks': policies[declaration]})
    return {'declaration': declaration, 'tasks': policies[declaration],
            'version': version(policies[declaration]), 'affects': 'next task pickup'}


def allowed(policies, agent, task):
    return policies[QUEUES[agent]].get(task, False)


def require(orch, actor, task, high=False):
    agent = ACTORS.get(actor)
    if not agent:
        return  # Interactive producer work remains available even with schedules off.
    if agent == 'architect' and high:
        agent = 'architect-high'
    with orch.db() as con:
        policies = read(con)
    if not allowed(policies, agent, task):
        raise orch.OrchError(f'{TASKS[task][0]} is disabled for {MODELS[QUEUES[agent]][0]}; leave it for the producer')


def filter_queue(agent, result, policies):
    result = dict(result)
    permissions = policies[QUEUES[agent]]
    for task, keys in {'planning': ('hld_to_draft', 'lld_to_draft'), 'coding': ('subtasks',),
                       'review': ('branches_to_review',), 'ideas': ('sparks_needing_rework',),
                       'issues': ('issues_to_solve',)}.items():
        if not permissions.get(task):
            for key in keys:
                if key in result:
                    result[key] = []
    return {**result, 'task_permissions': permissions,
            'instructions': 'Only perform enabled task types. Disabled types stay with the producer. '
                            'If no permitted work is available, log and stop; do not invent fallback work.'}


def report(orch, observation):
    with orch.db() as con:
        policies = read(con)
    config = orch.load_config()['models']
    rows = []
    for declaration, (name, config_key, supported) in MODELS.items():
        job = next((j for j in observation['jobs'] if j['declaration'] == declaration), None)
        rows.append({'declaration': declaration, 'label': name, 'model': (job or {}).get('model') or config.get(config_key, 'unknown'),
                     'tasks': policies[declaration], 'version': version(policies[declaration]),
                     'capabilities': [{'key': task, 'label': TASKS[task][0], 'description': TASKS[task][1]} for task in supported],
                     'job': job, 'controllable': observation['status'] == 'ok' and job is not None,
                     'generation': observation['generation']})
    return {'models': rows, 'scheduler_status': observation['status'], 'observed_at': observation['observed_at']}
