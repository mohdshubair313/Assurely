"""Run the live free-tier matrix using credentials already loaded into Docker.

Run from the project root: python backend/eval/free_runtime_live.py
The API and isolated eval containers must already exist. This helper never loads
a dotenv file; credentials travel to the eval process over stdin, stay in memory,
and are never included in artifacts. Langfuse verification uses its CLI.
"""

# The embedded program is passed directly to Python inside the eval container.
# ruff: noqa: E501
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

BOOTSTRAP = r'''
import asyncio,json,math,os,re,sys,uuid
from datetime import datetime,timezone
from pathlib import Path
runtime_input=json.load(sys.stdin)
resume=runtime_input.pop('__RAGAS_RESUME__',None)
os.environ.update(runtime_input)
os.environ['OPENROUTER_MODELS']='nvidia/nemotron-3-super-120b-a12b:free'
os.environ['RAGAS_OPENROUTER_MODEL']=os.environ['OPENROUTER_MODELS']
os.environ['RAGAS_DO_NOT_TRACK']='true'
os.environ['LOG_LEVEL']='warning'
from app.core import config
config.Settings.model_config['env_file']=None
config.get_settings=lambda:config.Settings(_env_file=None)
import httpx
from eval import ragas_live as rl
from app.graph.nodes import explanation_report as report_node
from app.core.correlation import current_turn
OUTPUT=Path('/artifacts')/os.environ['RAGAS_RUN_OUTPUT_NAME']
PARTIAL=OUTPUT.with_suffix('.partial.json')
progress={'timestamp':datetime.now(timezone.utc).isoformat(),'run_status':'in_progress','runner':'RAGAS collections API','live_pipeline':True,'mocked_pipeline_components':[],'runtime_env_only':True,'dotenv_accessed':False,'evidence_input_version':3,'after_pipeline_delay_seconds':75,'between_cases_delay_seconds':180,'metric_providers':{'context_precision':'groq','context_recall':'groq','answer_relevancy':'groq','faithfulness':'openrouter'},'faithfulness_model':os.environ['RAGAS_OPENROUTER_MODEL'],'scores':[],'provider_diagnostics':[],'report_format_diagnostics':[],'openrouter_cost_usd':0.0,'openrouter_responses_with_cost':0}
if resume:
    for key in ('scores','provider_diagnostics','report_format_diagnostics','openrouter_cost_usd','openrouter_responses_with_cost'):
        progress[key]=list(resume[key]) if isinstance(resume[key],list) else resume[key]
    progress['retained_case_ids']=[entry['case_id'] for entry in progress['scores']]
    progress['resumed_from']=os.environ['RAGAS_RESUME_SOURCE_NAME']
    progress['previous_failed_pipelines']=resume.get('previous_failed_pipelines',[])+([resume['failed_pipeline']] if 'failed_pipeline' in resume else [])
    progress['maintenance']='Only explicitly truncated reports retry once at 4096 tokens; the original successful 2048-token path, prompt and validators are unchanged.'
original_report_call=report_node.llm_call
async def report_diagnostic_call(*args,**kwargs):
    result=await original_report_call(*args,**kwargs)
    text=result.content.strip()
    event={'provider':result.provider,'model':result.model,'finish_reason':result.finish_reason if result.finish_reason in {'stop','length','content_filter','tool_calls'} else 'other','completion_tokens':result.completion_tokens,'content_chars':len(text),'starts_code_fence':text.startswith('```'),'ends_code_fence':text.endswith('```')}
    turn=current_turn.get()
    if turn:event.update(turn.identifiers())
    try:
        parsed=json.loads(text)
        event.update(valid_json=True,sentence_list=isinstance(parsed,dict) and isinstance(parsed.get('sentences'),list))
    except json.JSONDecodeError as exc:
        event.update(valid_json=False,json_error_position=exc.pos,json_error_line=exc.lineno,json_error_column=exc.colno)
        if text.startswith('```') and text.endswith('```'):
            try:
                parsed=json.loads('\n'.join(text.splitlines()[1:-1]))
                event['fence_body_valid_json']=True
                event['fence_body_sentence_list']=isinstance(parsed,dict) and isinstance(parsed.get('sentences'),list)
            except json.JSONDecodeError:event['fence_body_valid_json']=False
    progress['report_format_diagnostics'].append(event)
    PARTIAL.write_text(json.dumps(progress,indent=2))
    print('REPORT_FORMAT_DIAGNOSTIC '+json.dumps(event),flush=True)
    return result
report_node.llm_call=report_diagnostic_call
allowed_codes={'rate_limit_exceeded','tool_use_failed','invalid_request_error','insufficient_quota','RESOURCE_EXHAUSTED','INVALID_ARGUMENT','PERMISSION_DENIED','UNAUTHENTICATED','NOT_FOUND','UNAVAILABLE','context_length_exceeded'}
allowed_messages={'Rate limit exceeded','Rate limit exceeded: free-models-per-day.','Rate limit exceeded: free-models-per-minute.','The model is overloaded. Please try again later.','The model is experiencing high demand. Please try again later.'}
original_send=httpx.AsyncClient.send
async def diagnostic_send(self,request,*args,**kwargs):
    response=await original_send(self,request,*args,**kwargs)
    if request.url.host=='openrouter.ai' and response.is_success:
        try:
            await response.aread()
            cost=response.json().get('usage',{}).get('cost')
            if isinstance(cost,(int,float)) and not isinstance(cost,bool):
                progress['openrouter_cost_usd']+=cost
                progress['openrouter_responses_with_cost']+=1
                if cost>0:raise RuntimeError('Unexpected nonzero free-model cost')
        except (ValueError,TypeError,KeyError):pass
    if response.status_code>=400 and request.url.host in {'api.groq.com','openrouter.ai','generativelanguage.googleapis.com'}:
        diag={'provider_host':request.url.host,'http_status':response.status_code}
        try:
            await response.aread()
            payload=response.json()
            error=payload.get('error',payload)
            if isinstance(error,list):error=error[0]
            code=error.get('code') if isinstance(error,dict) else None
            if isinstance(code,int) or (isinstance(code,str) and code in allowed_codes):diag['error_code']=code
            status=error.get('status') if isinstance(error,dict) else None
            if isinstance(status,str) and status in allowed_codes:diag['error_status']=status
            msg=error.get('message','') if isinstance(error,dict) else ''
            diag['quota_numbers']=[{'field':k.lower(),'value':v} for k,v in re.findall(r'(?i)\b(limit|used|requested|remaining|try again in)\s*[:=]?\s*(\d+(?:\.\d+)?)',msg)]
            if msg in allowed_messages:diag['error_message']=msg
        except Exception:pass
        diag['rate_limit_headers']={k:v for k,v in response.headers.items() if ('ratelimit' in k.lower() or k.lower()=='retry-after') and re.fullmatch(r'[0-9., :TZ+\-]+',v)}
        progress['provider_diagnostics'].append(diag)
        PARTIAL.write_text(json.dumps(progress,indent=2))
        print('PROVIDER_DIAGNOSTIC '+json.dumps(diag),flush=True)
    return response
httpx.AsyncClient.send=diagnostic_send
original_cases=rl.load_cases
retained_ids={entry['case_id'] for entry in progress['scores']}
rl.load_cases=lambda:sorted([c for c in original_cases() if c['id'] not in retained_ids],key=lambda c:(not c['id'].startswith('case_08'),c['id']))
original_factory=rl.create_metrics
async def factory(*args,**kwargs):
    bundle=await original_factory(*args,**kwargs)
    if resume and any(resume[key]!=bundle[key] for key in ('evaluator_model','evaluator_provider','faithfulness_model','faithfulness_provider','embedding_model','faithfulness_context')):
        raise ValueError('Resume metric-provider configuration changed')
    for k in ('evaluator_model','evaluator_provider','faithfulness_model','faithfulness_provider','embedding_model','faithfulness_context'):progress[k]=bundle[k]
    return bundle
rl.create_metrics=factory
class EvaluationStopped(RuntimeError):pass
original_score=rl.score_case
async def checkpoint_score(sample,reference,metrics,**kwargs):
    evidence_count=len(sample['generation_contexts'])
    print('CASE_STARTED '+sample['case_id']+' retrieved='+str(sample['retrieved_fact_count'])+' generation_evidence='+str(evidence_count)+'; 75-second quota headroom',flush=True)
    await asyncio.sleep(75)
    scores=await original_score(sample,reference,metrics,**kwargs)
    for score in scores.values():
        if score.get('status')=='scored' and (score.get('value') is None or not math.isfinite(score['value'])):score.update(status='not_scored',reason='nonfinite_judge_result')
    entry={k:sample[k] for k in ('case_id','retrieved_fact_count','intent','missing_field_count','report_status','answer_source','delivery_hold','approved')}
    entry.update(generation_evidence_count=evidence_count,trace_ids=[t['trace_id'] for t in sample['turns']],decision_trace_ids=[t['decision_trace_id'] for t in sample['turns']],turn_count=len(sample['turns']),scores=scores)
    progress['scores'].append(entry)
    progress['case_count']=len(progress['scores'])
    PARTIAL.write_text(json.dumps(progress,indent=2,allow_nan=False))
    print('CASE_SCORES '+json.dumps({'case_id':sample['case_id'],'scores':scores}),flush=True)
    if any(s['status'] not in {'scored','not_applicable','not_requested'} for s in scores.values()):raise EvaluationStopped(sample['case_id'])
    return scores
rl.score_case=checkpoint_score
async def postgres_verification(results):
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.models.db.decision_trace import DecisionTrace
    ids={uuid.UUID(t) for r in results for t in r['decision_trace_ids']}
    async with AsyncSessionLocal() as db:
        rows=await db.execute(select(DecisionTrace.id).where(DecisionTrace.id.in_(ids)))
        found={r[0] for r in rows.all()}
    count=sum(len(r['trace_ids']) for r in results)
    return {'decision_trace_rows_expected':len(ids),'decision_trace_rows_found':len(found),'decision_trace_rows_all_present':found==ids,'langfuse_configured':True,'langfuse_trace_status_counts':{'pending_cli_verification':count},'langfuse_verification_method':'langfuse-cli observations on host'}
rl.verify_trace_persistence=postgres_verification
async def main():
    try:
        await rl.run(OUTPUT,judge_provider='groq',faithfulness_provider='openrouter',between_cases_delay_seconds=180)
        artifact=json.loads(OUTPUT.read_text())
        artifact.update({k:v for k,v in progress.items() if k not in {'scores','case_count','run_status'}})
        if resume:
            artifact['scores']=resume['scores']+artifact['scores']
            artifact['case_count']=len(artifact['scores'])
            artifact['trace_persistence']=await postgres_verification(artifact['scores']+progress['previous_failed_pipelines'])
        artifact['run_status']='metrics_complete_pending_cli_verification'
        OUTPUT.write_text(json.dumps(artifact,indent=2,allow_nan=False))
        print('ALL_CASE_METRICS_COMPLETED',flush=True)
    except Exception as exc:
        progress.update(run_status='failed',fatal_error_class=type(exc).__name__)
        if isinstance(exc,EvaluationStopped):progress['failed_case']=str(exc)
        if isinstance(exc,rl.PipelineReportUnavailableError):
            progress['failed_pipeline']=exc.details
            progress['failed_case']=exc.details['case_id']
        cases=progress['scores']+progress.get('previous_failed_pipelines',[])+([progress['failed_pipeline']] if 'failed_pipeline' in progress else [])
        if cases:progress['trace_persistence']=await postgres_verification(cases)
        OUTPUT.write_text(json.dumps(progress,indent=2,allow_nan=False))
        print('EVALUATION_STOPPED '+json.dumps({'error_class':type(exc).__name__,'failed_case':progress.get('failed_case'),'completed_case_count':len(progress['scores'])}),flush=True)
        return 2
    return 0
raise SystemExit(asyncio.run(main()))
'''


def observation_status(payload: dict[str, Any], trace_id: str) -> str:
    """Unwrap the CLI's HTTP envelope without exposing headers or observation IO."""
    http_status = payload.get("status", 200)
    if http_status != 200:
        return f"http_{http_status}"
    body = payload.get("body", payload)
    if isinstance(body, str):
        body = json.loads(body)
    data = body.get("data", [])
    return "found" if any(item.get("traceId") == trace_id for item in data) else "not_found"


def validate_resume(artifact: dict[str, Any]) -> None:
    """Retain only completed real measurements using the identical metric contract."""
    expected_providers = {
        "context_precision": "groq", "context_recall": "groq",
        "answer_relevancy": "groq", "faithfulness": "openrouter",
    }
    if (
        artifact.get("evidence_input_version") != 3
        or artifact.get("metric_providers") != expected_providers
        or artifact.get("faithfulness_model") != "nvidia/nemotron-3-super-120b-a12b:free"
        or artifact.get("faithfulness_context") != "complete_sourced_explanation_evidence"
        or artifact.get("live_pipeline") is not True
        or artifact.get("mocked_pipeline_components") != []
    ):
        raise ValueError("Resume source has an incompatible provider/evidence contract")
    entries = artifact.get("scores", [])
    if not 0 < len(entries) < 8:
        raise ValueError("Resume requires between one and seven completed cases")
    seen: set[str] = set()
    early = {"case_03_missing_info_loop", "case_07_ambiguous_intent"}
    for entry in entries:
        case_id = entry["case_id"]
        if case_id in seen:
            raise ValueError("Resume contains duplicate case IDs")
        seen.add(case_id)
        if case_id in early:
            valid_target = entry.get("answer_source") == "clarification_response"
        else:
            valid_target = (
                entry.get("answer_source") == "generated_report"
                and entry.get("report_status") == "ready"
            )
        if not valid_target:
            raise ValueError("Resume source contains an invalid generation target")
        scores = entry.get("scores", {})
        if set(scores) != set(expected_providers):
            raise ValueError("Resume source has missing metrics")
        for score in scores.values():
            if score.get("status") == "scored":
                value = score.get("value")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("Resume contains a nonfinite or missing score")
            elif score.get("status") != "not_applicable":
                raise ValueError("Resume source contains unresolved or invalid metric data")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-container", default="insurance-api")
    parser.add_argument("--eval-container", default="insurance-ragas-free-20261008")
    parser.add_argument("--resume-from", help="Completed case checkpoint filename inside artifacts")
    parser.add_argument(
        "--output-name",
        default=f"ragas-live-free-full-evidence-{datetime.now(UTC).date()}.json",
    )
    args = parser.parse_args()
    if Path(args.output_name).name != args.output_name or not args.output_name.endswith(".json"):
        raise ValueError("Output name must be a JSON filename inside artifacts")
    output = ROOT / "artifacts" / args.output_name
    if output.exists():
        raise ValueError("Output already exists; choose a fresh --output-name")
    resume = None
    if args.resume_from:
        if Path(args.resume_from).name != args.resume_from:
            raise ValueError("Resume source must be a filename inside artifacts")
        resume = json.loads((ROOT / "artifacts" / args.resume_from).read_text(encoding="utf-8"))
        validate_resume(resume)
    inspected = subprocess.run(
        ["docker", "inspect", args.api_container], capture_output=True, text=True, check=True
    )
    info = json.loads(inspected.stdout)[0]
    runtime = dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)
    required = (
        "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
        "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY",
    )
    missing = [name for name in required if not runtime.get(name)]
    if missing:
        raise ValueError(f"Runtime credentials missing: {', '.join(missing)}")
    runtime["RAGAS_RUN_OUTPUT_NAME"] = args.output_name
    if resume:
        runtime["RAGAS_RESUME_SOURCE_NAME"] = args.resume_from
        runtime["__RAGAS_RESUME__"] = resume
        print(f"Resuming complete-evidence matrix; retaining {len(resume['scores'])} validated cases.", flush=True)
    else:
        print("Starting complete-evidence live matrix: case 08 first, then 01-07.", flush=True)
    completed = subprocess.run(
        ["docker", "exec", "-i", "-w", "/tmp", args.eval_container, "python", "-u", "-c", BOOTSTRAP],
        input=json.dumps(runtime), text=True,
    )
    if not output.exists():
        return completed.returncode or 2
    artifact = json.loads(output.read_text(encoding="utf-8"))
    cases = artifact.get("scores", []) + (
        [artifact["failed_pipeline"]] if "failed_pipeline" in artifact else []
    ) + artifact.get("previous_failed_pipelines", [])
    trace_ids = {trace_id for entry in cases for trace_id in entry["trace_ids"]}
    cli_env = os.environ.copy()
    cli_env.update({key: value for key, value in runtime.items() if key.startswith("LANGFUSE_")})
    cli_env["LANGFUSE_BASE_URL"] = (
        runtime.get("LANGFUSE_HOST") or runtime.get("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com"
    )
    counts: dict[str, int] = {}
    for trace_id in sorted(trace_ids):
        try:
            response = subprocess.run(
                ["npx.cmd", "--yes", "langfuse-cli", "api", "observations", "list",
                 "--trace-id", trace_id, "--fields", "core", "--limit", "1", "--json"],
                env=cli_env, cwd=tempfile.gettempdir(), capture_output=True, text=True, timeout=60,
            )
            status = (
                observation_status(json.loads(response.stdout), trace_id)
                if response.returncode == 0 else "cli_error"
            )
        except Exception as exc:
            status = "cli_" + type(exc).__name__
        counts[status] = counts.get(status, 0) + 1
        print("LANGFUSE_VERIFICATION " + json.dumps({"trace_id": trace_id, "status": status}), flush=True)
    persistence = artifact.setdefault("trace_persistence", {})
    persistence["langfuse_trace_status_counts"] = counts
    persistence["langfuse_verification_method"] = "langfuse-cli observations --fields core"
    resolved = len(artifact.get("scores", [])) == 8 and all(
        score["status"] in {"scored", "not_applicable"}
        for entry in artifact.get("scores", []) for score in entry["scores"].values()
    )
    verified = persistence.get("decision_trace_rows_all_present") and counts.get("found", 0) == len(trace_ids)
    artifact["run_status"] = "complete" if resolved and verified else "incomplete"
    output.write_text(json.dumps(artifact, indent=2, allow_nan=False), encoding="utf-8")
    print("FINAL_RUN_STATUS " + json.dumps({"status": artifact["run_status"], "case_count": len(artifact.get("scores", [])), "persistence": persistence}), flush=True)
    return 0 if artifact["run_status"] == "complete" else 2


if __name__ == "__main__":
    sys.exit(main())
