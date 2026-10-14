from __future__ import annotations
import asyncio, json, os, signal, sys
from pathlib import Path
import jsonschema
from .workspace import atomic_json, digest, sha, read_json, HarnessError, ConfigError, now
from .checkpoints import restore, commit, clock
from .runtime import slot

async def process(argv, cwd, stdout, stderr, timeout, stdin=None, extra_env=None):
    env=dict(os.environ)
    env['PATH']=str(Path(sys.executable).parent)+os.pathsep+env.get('PATH','')
    env['PYTHONDONTWRITEBYTECODE']='1'
    if extra_env:env.update(extra_env)
    with stdout.open('wb') as out, stderr.open('wb') as err:
        p=await asyncio.create_subprocess_exec(*argv,cwd=cwd,env=env,stdout=out,stderr=err,
               stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,start_new_session=True)
        try:
            communication=asyncio.create_task(p.communicate(stdin.encode() if stdin is not None else None))
            deadline=clock()+timeout
            while not communication.done():
                remaining=deadline-clock()
                if remaining<=0:raise asyncio.TimeoutError()
                await asyncio.wait({communication},timeout=min(1,remaining))
            await communication
            return p.returncode
        except BaseException:
            try: os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: await asyncio.wait_for(p.wait(),3)
            except asyncio.TimeoutError:
                try: os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                await p.wait()
            raise

def command(config, workspace, schema, response, images):
    a=config['agent']
    argv=[a['executable'],'exec','--model',a['model'],'--config','model_reasoning_effort='+json.dumps(a['reasoning_effort']),
          '--config','approval_policy="never"','--sandbox',a['sandbox'],'--ephemeral','--skip-git-repo-check',
          '--cd',str(workspace),'--output-schema',str(schema),'--output-last-message',str(response),'--json']
    if images: argv += ['--image',*map(str,images)]
    return argv+['--','-']

def usage_from_events(path):
    totals={}; seen=False
    for line in path.read_text(errors='replace').splitlines():
        try: event=json.loads(line)
        except ValueError: continue
        if event.get('type')=='turn.completed' and isinstance(event.get('usage'),dict):
            for k,v in event['usage'].items():
                if isinstance(v,(int,float)):
                    totals[k]=totals.get(k,0)+v; seen=True
    return totals if seen else None

async def invoke(config, budget, work: Path, prompt: str, schema: dict, images=(), validator=None):
    work.mkdir(parents=True,exist_ok=True)
    meta=work/'.harness'; meta.mkdir(exist_ok=True)
    schema_path=meta/'schema.json'
    prompt_path=meta/'prompt.txt'
    identity=digest({'prompt':prompt,'schema':schema,'images':[sha(p) for p in images],'model':config['agent']['model'],'effort':config['agent']['reasoning_effort']})
    cached=restore(meta/'complete.json')
    if cached:
        if cached['identity']!=identity: raise ConfigError('Agent checkpoint inputs changed')
        return cached['payload']
    atomic_json(schema_path,schema); prompt_path.write_text(prompt)
    recover=meta/'repair-existing.json'
    if recover.exists():
        previous=sorted(meta.glob('attempt-*/response.json'))
        if previous:
            response=previous[-1]
            try:
                recovered=read_json(response);jsonschema.validate(recovered,schema)
                if validator:validator(recovered)
            except Exception as exc:
                repair_dir=work/'format-repair';repair_dir.mkdir(exist_ok=True)
                (repair_dir/'original-output.txt').write_text(response.read_text())
                repair_prompt=('Fix only the JSON structure and internal references in original-output.txt. Preserve all existing content. '
                    'For any edge with null endpoint or unknown direction add its edge ID to an uncertainty related_ids. '
                    'Do not inspect images or other directories or network. Return only corrected JSON. Validation error: '+str(exc))
                recovered=await invoke(config,budget,repair_dir,repair_prompt,schema,(),validator)
            fixed=meta/'recovered-response.json';atomic_json(fixed,recovered)
            commit(meta/'complete.json',{'identity':identity,'payload':recovered},[fixed,prompt_path,schema_path,*images])
            return recovered
    attempts=len(list(meta.glob('attempt-*')))
    # At most one transport retry per invocation; past attempts also count on resume.
    last=''
    for attempt in range(attempts, attempts+1+config['agent']['max_transport_retries']):
        ad=meta/f'attempt-{attempt:02d}'; ad.mkdir(exist_ok=True)
        response=ad/'response.json'; events=ad/'events.jsonl'; stderr=ad/'stderr.log'
        argv=command(config,work,schema_path,response,images)
        atomic_json(ad/'request.json',{'argv':argv,'identity':identity,'requested_model':config['agent']['model'],
                    'reasoning_effort':config['agent']['reasoning_effort'],'at':now(),'role_workspace':str(work)})
        async with slot('agent'):
            timeout=budget.begin(config['agent']['call_timeout_seconds'])
            try:
                rc=await process(argv,work,events,stderr,timeout,stdin=prompt)
            except asyncio.TimeoutError as exc:
                raise HarnessError(f'Agent timed out; logs: {ad}') from exc
            finally: budget.finish()
        atomic_json(ad/'execution.json',{'exit_code':rc,'usage':usage_from_events(events),'cost_usd':None})
        if rc != 0:
            last=(stderr.read_text(errors='replace')+'\n'+events.read_text(errors='replace'))[-5000:]
            # Plugin catalog warnings can include 401 even when model access works.
            provider_errors=[]
            for line in events.read_text(errors='replace').splitlines():
                try: event=json.loads(line)
                except ValueError: continue
                if event.get('type') in ('error','turn.failed'):provider_errors.append(json.dumps(event))
            provider_error='\n'.join(provider_errors).lower()
            if any(s in provider_error for s in ('401','403','model_not_found','unsupported model','unauthorized')):
                raise ConfigError(f'Provider/model authorization failed; inspect {ad}')
            if attempt==attempts and config['agent']['max_transport_retries'] and any(s in last.lower() for s in ('429','502','503','connection reset','stream disconnected')):
                await asyncio.sleep(min(2,budget.remaining)); continue
            raise HarnessError(f'Codex exited {rc}; logs: {ad}')
        try:
            payload=read_json(response); jsonschema.validate(payload,schema)
            if validator: validator(payload)
        except Exception as exc:
            repair_dir=work/'format-repair'
            if work.name=='format-repair':
                raise HarnessError(f'AGENT_OUTPUT_ERROR after one format repair: {exc}; response: {response}') from exc
            repair_dir.mkdir(exist_ok=True)
            raw=response.read_text(errors='replace') if response.exists() else ''
            if not raw:raise HarnessError(f'AGENT_OUTPUT_ERROR: no response to repair; {response}') from exc
            (repair_dir/'original-output.txt').write_text(raw)
            repair_prompt=('Repair only the JSON structure and internal references of original-output.txt to satisfy the supplied schema and validation error. '
                'Preserve the existing observations and all gate triggered decisions and findings. Do not inspect images, do not re-evaluate visual quality, '
                'do not read outside this directory, and do not use the network. Add missing uncertainty references for unknown/null diagram endpoints. '
                'Return corrected JSON only. Validation error: '+str(exc))
            payload=await invoke(config,budget,repair_dir,repair_prompt,schema,(),validator)
            if 'gate_keeper' in schema.get('properties',{}):
                try:
                    original=json.loads(raw)
                    if payload['gate_keeper']['triggered']!=original['gate_keeper']['triggered']:
                        raise HarnessError('Format repair changed a gate decision')
                except (ValueError,KeyError,TypeError):raise HarnessError('Cannot verify gate preservation during format repair')
            response=ad/"corrected-response.json"
            atomic_json(response,payload)
        commit(meta/'complete.json',{'identity':identity,'payload':payload},[response,prompt_path,schema_path,*images])
        return payload
    raise HarnessError(f'Agent retry exhausted: {last[:200]}')
