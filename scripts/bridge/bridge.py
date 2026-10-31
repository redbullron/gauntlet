#!/usr/bin/env python3
"""MCP stdio adapter and command-line interface; standard library only."""
import argparse
import json
import sys
from pathlib import Path
import core


def obj(properties=None, required=None):
    return dict(type='object', properties=properties or {}, required=required or [], additionalProperties=False)


STR = {'type': 'string'}
CHECK = obj({'name': STR, 'command': {'type': 'array', 'items': STR, 'minItems': 1},
             'cwd': STR, 'timeout': {'type': 'integer', 'minimum': 1, 'maximum': 1800}}, ['name', 'command'])
TOOLS = [
    ('gauntlet_projects', 'List project profiles with source folders, context, and validation commands.', obj()),
    ('gauntlet_register_project', 'Register/update a project profile. Use the user-selected project folder. Checks run in an isolated copy with no shell interpolation. Only configure checks suitable for local testing, never deployment or live operations. Code projects need passing checks for approval. Context should contain relevant requirements and decisions, never secrets.',
     obj({'name': STR, 'path': STR, 'context': STR, 'kind': {'type': 'string', 'enum': ['code', 'document']},
          'checks': {'type': 'array', 'items': CHECK}}, ['name', 'path'])),
    ('gauntlet_start', 'Start an autonomous Codex/Claude review or fix loop for a registered project. Returns immediately with a job ID. Uses existing CLI logins and consumes their usage. Source stays unchanged; changes are in a separate copy and patch. One active job globally. Pass the user task, acceptance criteria, and relevant chat decisions explicitly. Review workers do not inherit this chat. Use gauntlet_status to follow progress and gauntlet_result at completion.',
     obj({'project': STR, 'task': STR, 'mode': {'type': 'string', 'enum': ['fix', 'review'], 'default': 'fix'},
          'writer': {'type': 'string', 'enum': ['codex', 'claude'], 'default': 'codex'},
          'max_rounds': {'type': 'integer', 'minimum': 1, 'maximum': 10, 'default': 5},
          'max_minutes': {'type': 'integer', 'minimum': 1, 'maximum': 240, 'default': 60}}, ['project', 'task'])),
    ('gauntlet_status', 'Read progress of one job, or list recent jobs when job_id is omitted. Poll about every 20-30 seconds while a job runs. Closing the client does not cancel the job.', obj({'job_id': STR})),
    ('gauntlet_result', 'Read the complete review history, check evidence, final status, patch path, and workspace. Approval requires both reviewers on the same revision. No automatic apply, merge, push or deployment.', obj({'job_id': STR}, ['job_id'])),
    ('gauntlet_cancel', 'Stop a running Gauntlet and its active child process tree. Retains all work and evidence.', obj({'job_id': STR}, ['job_id'])),
]


def validate(schema, value, path='arguments'):
    expected = schema.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int}
    if expected in types and type(value) is not types[expected]:
        raise ValueError(path + ' must be ' + expected)
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(path + ': unsupported value')
    if expected == 'object':
        props = schema.get('properties', {})
        if schema.get('additionalProperties') is False and set(value) - set(props):
            raise ValueError(path + ': unknown fields')
        if set(schema.get('required', [])) - set(value):
            raise ValueError(path + ': missing required fields')
        for key, v in value.items():
            validate(props[key], v, path + '.' + key)
    if expected == 'array':
        if len(value) < schema.get('minItems', 0):
            raise ValueError(path + ': too few items')
        for v in value:
            validate(schema['items'], v, path + '[]')
    if expected == 'integer' and not schema.get('minimum', -sys.maxsize) <= value <= schema.get('maximum', sys.maxsize):
        raise ValueError(path + ': outside limits')


def call(name, args):
    spec = next((t for t in TOOLS if t[0] == name), None)
    if not spec:
        raise ValueError('Unknown tool')
    validate(spec[2], args)
    if name == 'gauntlet_projects':
        return core.projects()
    if name == 'gauntlet_register_project':
        return core.register_project(**args)
    if name == 'gauntlet_start':
        return core.start(**args)
    if name == 'gauntlet_status':
        core.recover()
        return core.summary(core.get(args['job_id'])) if args.get('job_id') else core.recent()
    if name == 'gauntlet_result':
        core.recover()
        return core.get(args['job_id'])
    if name == 'gauntlet_cancel':
        return core.cancel(args['job_id'])


def mcp():
    # No HTTP port, service, npm install, or resident model process is required.
    for raw in sys.stdin:
        request = None
        try:
            request = json.loads(raw)
            if not isinstance(request, dict) or request.get('jsonrpc') != '2.0':
                raise ValueError('Expected JSON-RPC 2.0 request')
            if 'id' not in request:
                continue
            method = request.get('method')
            params = request.get('params', {})
            if method == 'initialize':
                version = params.get('protocolVersion', '2025-11-25')
                result = {'protocolVersion': version if version in ('2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25') else '2025-11-25',
                          'capabilities': {'tools': {'listChanged': False}},
                          'serverInfo': {'name': 'local-gauntlet', 'version': '1.0.0'},
                          'instructions': 'Local Codex/Claude review bridge for any registered project. Start a job only for user-requested work; explicitly pass task and context. One worker at a time. Poll status, then read results. Both reviewers must approve the same revision and configured checks must pass. Jobs survive client exit. Never start nested reviews from a worker. Never claim a running or unvalidated job passed. Patches require an explicit apply step.'}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': [dict(name=n, description=d, inputSchema=s,
                                        annotations={'readOnlyHint': n in ('gauntlet_projects', 'gauntlet_status', 'gauntlet_result'),
                                                     'destructiveHint': False, 'openWorldHint': n == 'gauntlet_start'}) for n, d, s in TOOLS]}
            elif method == 'tools/call':
                try:
                    value = call(params['name'], params.get('arguments', {}))
                    result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}], 'isError': False}
                except Exception as e:
                    result = {'content': [{'type': 'text', 'text': str(e)}], 'isError': True}
            else:
                print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'error': {'code': -32601, 'message': 'Method not found'}}), flush=True)
                continue
            response = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
        except Exception as e:
            response = {'jsonrpc': '2.0', 'id': request.get('id') if isinstance(request, dict) else None,
                        'error': {'code': -32700 if isinstance(e, json.JSONDecodeError) else -32600, 'message': str(e)}}
        print(json.dumps(response, ensure_ascii=False), flush=True)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stdin.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Local Codex / Claude Gauntlet bridge')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('mcp')
    sub.add_parser('projects')
    sub.add_parser('doctor')
    p = sub.add_parser('register')
    p.add_argument('name'); p.add_argument('path')
    p.add_argument('--profile', help='JSON file with checks, context and kind')
    p = sub.add_parser('start')
    p.add_argument('project'); p.add_argument('task', nargs='?')
    p.add_argument('--task-file')
    p.add_argument('--mode', choices=['review', 'fix'], default='fix')
    p.add_argument('--writer', choices=['codex', 'claude'], default='codex')
    p.add_argument('--max-rounds', type=int, default=5)
    p.add_argument('--max-minutes', type=int, default=60)
    for action in ('status', 'result', 'cancel', 'worker'):
        p = sub.add_parser(action)
        p.add_argument('job_id', nargs='?' if action == 'status' else None)
    a = parser.parse_args()
    if a.action == 'mcp':
        mcp(); return
    if a.action == 'worker':
        core.worker(a.job_id); return
    if a.action == 'doctor':
        import shutil
        c = core.config()
        result = {'python': sys.executable, 'git': shutil.which('git'), 'state': str(core.STATE),
                  'agents': {k: {'executable': v['executable'], 'exists': Path(v['executable']).is_file(),
                                 'model': v.get('model', 'CLI default')} for k, v in c['agents'].items()},
                  'projects': [p['name'] for p in core.projects()], 'recent_jobs': core.recent()}
    elif a.action == 'projects':
        result = core.projects()
    elif a.action == 'register':
        options = json.loads(Path(a.profile).read_text(encoding='utf-8-sig')) if a.profile else {}
        result = core.register_project(a.name, a.path, **options)
    elif a.action == 'start':
        task = Path(a.task_file).read_text(encoding='utf-8-sig') if a.task_file else a.task
        result = core.start(a.project, task, a.mode, a.writer, a.max_rounds, a.max_minutes)
    else:
        result = call('gauntlet_' + a.action, {'job_id': a.job_id} if a.job_id else {})
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
