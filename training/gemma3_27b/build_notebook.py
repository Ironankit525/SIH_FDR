"""Rebuild the self-contained Colab notebook from the tested service/evaluation modules."""
import json
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
cells = []
def md(source):
    cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': textwrap.dedent(source).strip() + '\n'})
def code(name, source):
    cells.append({'cell_type': 'code', 'id': name, 'metadata': {}, 'execution_count': None, 'outputs': [],
                  'source': textwrap.dedent(source).strip() + '\n'})

md('''
# DepositFlow — review and serve your Gemma 3 27B adapter

This notebook loads your **existing Gemma 3 27B LoRA adapter**. It does not train, overwrite your model,
or use the earlier 8B model. It provides unseen-data evaluation, deterministic document-review warnings,
and the exact API used by your portal. Start in a **fresh Colab A100 GPU session**; your recorded training
used an A100 80 GB. Other hardware has not been tested here.

Run cells in order. **RUN_EVALUATION = False** starts the saved model for team testing without a training
dataset or a benchmark run. The API check still makes one real inference on a fictional receipt.
Enable evaluation to compare the base and adapter on **24 newly generated fictional receipts**.
They exercise the pipeline but do not establish real-bank accuracy. For a real assessment, supply labelled
receipts excluded from all training and tuning. Evaluation outputs save to Drive; actual API keys do not.

The service/core logic and backend contract are tested on CPU. **GPU loading and accuracy must be measured
by running these cells.** The original weights remain unchanged. Running this notebook does not upload weights to GitHub.
''')
code('install', '''
import subprocess, sys
# Pin the three library versions recorded in your successful run/export. Other GPU dependencies resolve
# for the runtime; the full installed set is saved below. This notebook performs inference, not TRL training.
subprocess.check_call([sys.executable, '-m', 'pip', 'install',
    'unsloth==2026.10.8', 'transformers==5.17.0', 'peft==0.21.2',
    'fastapi>=0.115.12,<1', 'uvicorn>=0.34,<1', 'python-multipart>=0.0.20,<1',
    'pydantic>=2,<3', 'Pillow>=11,<13', 'PyMuPDF>=1.25,<2',
    'httpx>=0.28,<1', 'pyngrok>=7,<8'])
print('If Colab requests a restart, restart now and continue at Mount Drive. Do not run old installation cells.')
''')
md('''
## Mount Drive and configure serving or evaluation

The default path matches your shared export's folder name. Change ROOT if your Drive copy is elsewhere.
For real evaluation, put `test.jsonl` and its labelled PNG/JPG pages under `ROOT/real_holdout/` and choose REAL.
Leave RUN_EVALUATION=False to serve the saved adapter; the original training images are needed only for evaluation.

The optional term threshold is **disabled by default**. `8` with an explicit illustrative reference can reproduce
that part of your old demo. An authorised, applicable policy is required before using any term threshold in real cases.
''')
code('configuration', '''
from google.colab import drive
from pathlib import Path
from datetime import datetime, timezone
import json, os, sys, hashlib

drive.mount('/content/drive')
ROOT = Path('/content/drive/MyDrive/SIH26265_AICTE_VLM_27B_12B')
ADAPTER_DIR = ROOT / 'fine_tuned_vlm_lora'
TRAINING_IMAGES = ROOT / 'fdr_dataset_images'
RUN_EVALUATION = False       # True only when running the holdout benchmark; not needed to serve.
EVALUATION_KIND = 'SYNTHETIC'  # SYNTHETIC or REAL
REAL_MANIFEST = ROOT / 'real_holdout' / 'test.jsonl'
MINIMUM_TERM_YEARS = None     # e.g. 8 only with an appropriate POLICY_REFERENCE
POLICY_REFERENCE = ''        # e.g. 'Illustrative old-demo rule; not verified APH policy'
MAX_NEW_TOKENS = 640
MAX_CONTEXT_TOKENS = 2048
RUN_NAME = datetime.now(timezone.utc).strftime('review-%Y%m%d-%H%M%S-%f')
RUN_DIR = ROOT / 'review_runs' / RUN_NAME
RUN_DIR.mkdir(parents=True, exist_ok=False)
assert EVALUATION_KIND in ('SYNTHETIC', 'REAL')
print('Run artifacts:', RUN_DIR)
''')
md('''
## Install the bundled, CPU-tested worker and evaluation code

This cell writes the source bundled inside this notebook to the temporary Colab runtime. It does not fetch
unreviewed code from your Drive. The same source is available in the project's `training/gemma3_27b` directory.
''')
bundled = {name: (HERE / name).read_text() for name in ('__init__.py', 'service.py', 'evaluation.py')}
code('bundled-code', f'''
from pathlib import Path
import sys, importlib
package_root = Path('/content/depositflow_gemma_review')
package = package_root / 'gemma3_27b'
package.mkdir(parents=True, exist_ok=True)
bundled_sources = {bundled!r}
for name, source in bundled_sources.items():
    (package / name).write_text(source)
if str(package_root) not in sys.path:
    sys.path.insert(0, str(package_root))
# A previous failed import may have cached this formerly missing directory.
importlib.invalidate_caches()
from gemma3_27b.service import MODEL_ID, PROMPT, ReviewPolicy, create_app, portal_response
from gemma3_27b.evaluation import make_synthetic_holdout, load_manifest, evaluate
policy = ReviewPolicy(globals().get('MINIMUM_TERM_YEARS'), globals().get('POLICY_REFERENCE', ''))
print('Worker and evaluation code ready; existing model state was not changed.')
''')
code('prepare-holdout', '''
rows, provenance = [], None
if not RUN_EVALUATION:
    print('Serving mode: holdout preparation skipped. No evaluation metrics will be claimed.')
else:
    if EVALUATION_KIND == 'SYNTHETIC':
        manifest_path = make_synthetic_holdout(RUN_DIR / 'synthetic_holdout', count=24)
    else:
        manifest_path = REAL_MANIFEST
    rows, provenance = load_manifest(manifest_path, TRAINING_IMAGES)
    if EVALUATION_KIND == 'REAL' and provenance['kinds'] != ['real']:
        raise ValueError('REAL mode requires real-labelled holdout rows; do not relabel synthetic images as real.')
    (RUN_DIR / 'dataset_provenance.json').write_text(json.dumps(provenance, indent=2))
    (RUN_DIR / 'heldout_labels.jsonl').write_text(''.join(json.dumps({k:v for k,v in row.items() if k != '_path'}) + '\\n' for row in rows))
    print(json.dumps(provenance, indent=2))
    from PIL import Image
    from IPython.display import display
    with Image.open(rows[0]['_path']) as preview:
        display(preview.resize((750, round(preview.height * 750 / preview.width))))
    print('Manually exclude related pages, crops and near-duplicates; exact pixel checks cannot prove full independence.')
''')
md('''
## Reload the saved adapter in this fresh runtime

This explicitly checks that your saved adapter belongs to the **27B Gemma model**, then loads it with its base.
The 466 MB adapter is not the full base model; the first base download is large. No automatic model-size fallback occurs.
The adapter did not record a base revision, so the run records the revision actually loaded when available.
''')
code('load-model', '''
# Import Unsloth before torch/transformers.
from unsloth import FastVisionModel
import torch, subprocess, sys, time
if globals().get('RUN_EVALUATION', False) and not globals().get('provenance'):
    raise RuntimeError('Run the holdout-preparation cell before loading for evaluation, or set RUN_EVALUATION=False for serving.')
if not torch.cuda.is_available():
    raise RuntimeError('Select a GPU runtime; use the A100 class used for your recorded 27B training.')
print('GPU:', torch.cuda.get_device_name(0), 'GiB:', round(torch.cuda.get_device_properties(0).total_memory / 2**30, 1))
required = ['adapter_config.json', 'adapter_model.safetensors', 'processor_config.json', 'tokenizer_config.json', 'tokenizer.json']
for name in required:
    if not (ADAPTER_DIR / name).is_file(): raise FileNotFoundError(ADAPTER_DIR / name)
adapter_config = json.loads((ADAPTER_DIR / 'adapter_config.json').read_text())
if adapter_config.get('base_model_name_or_path') != MODEL_ID:
    raise ValueError('This adapter does not identify the expected Gemma 3 27B base model.')
def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''): digest.update(chunk)
    return digest.hexdigest()
adapter_sha256 = file_sha256(ADAPTER_DIR / 'adapter_model.safetensors')
model, processor = FastVisionModel.from_pretrained(
    model_name=str(ADAPTER_DIR), load_in_4bit=True, max_seq_length=MAX_CONTEXT_TOKENS)
FastVisionModel.for_inference(model)
model.eval()
run_info = {'model': MODEL_ID, 'adapter_sha256': adapter_sha256,
    'adapter_directory': str(ADAPTER_DIR), 'base_revision_recorded_by_adapter': adapter_config.get('revision'),
    'loaded_config_revision': getattr(model.config, '_commit_hash', None),
    'dataset': globals().get('provenance') if globals().get('RUN_EVALUATION', False) else None,
    'evaluation_requested': globals().get('RUN_EVALUATION', False), 'prompt': PROMPT,
    'policy': {'minimum_years': MINIMUM_TERM_YEARS, 'reference': POLICY_REFERENCE},
    'max_context_tokens': MAX_CONTEXT_TOKENS, 'max_new_tokens': MAX_NEW_TOKENS}
(RUN_DIR / 'run_info.json').write_text(json.dumps(run_info, indent=2))
(RUN_DIR / 'extraction_prompt.txt').write_text(PROMPT)
(RUN_DIR / 'environment.freeze.txt').write_text(subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True))
print('Fresh-session adapter load completed. Adapter fingerprint:', adapter_sha256)
''')
md('''
## Define receipt inference

Run this cell after the model-loading cell. It defines `infer(image)`, which the HTTP worker calls for each
receipt. It does not reload or retrain the model. Defining the function is required even when evaluation is skipped.
''')
code('inference', '''
@torch.inference_mode()
def infer(image):
    # Only the image and instruction enter the prompt; human labels never enter inference.
    messages = [{'role': 'user', 'content': [{'type': 'image'}, {'type': 'text', 'text': PROMPT}]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(images=image, text=text, add_special_tokens=False,
                       return_tensors='pt', truncation=False).to('cuda')
    output = None
    try:
        length = inputs['input_ids'].shape[-1]
        if length + MAX_NEW_TOKENS > MAX_CONTEXT_TOKENS:
            raise RuntimeError('Input plus answer exceeds the configured context; inspect image/crop settings.')
        torch.cuda.synchronize()
        output = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False, use_cache=True)
        torch.cuda.synchronize()
        return processor.batch_decode(output[:, length:], skip_special_tokens=True)[0].strip()
    finally:
        del inputs, output
''')
md('''
## Compare the pretrained base and your adapter on exactly the same unseen receipts

Skipped when RUN_EVALUATION=False. This benchmark is optional for connecting an already-trained model.
This performs inference only. The base pass temporarily disables LoRA; the second pass re-enables your adapter.
Both passes use the same prompt, image processing, deterministic generation and full holdout. Raw outputs and
per-field accuracy are saved alongside JSON validity, null-field hallucinations, review-flag precision/recall and latency.
Synthetic results measure only this fictional dataset. Inspect real-data errors before using the service on real cases.
''')
code('evaluate', '''
if not RUN_EVALUATION:
    print('Serving mode: benchmark skipped. Use the API check below to test one real inference.')
else:
    if not globals().get('rows') or not globals().get('provenance'):
        raise RuntimeError('Run holdout preparation before evaluating.')
    if not hasattr(model, 'disable_adapter'):
        raise RuntimeError('PEFT adapter disable context is unavailable; do not label an adapted run as the baseline.')
    with model.disable_adapter():
        baseline = evaluate(infer, rows, policy, RUN_DIR, 'base')
    adapted = evaluate(infer, rows, policy, RUN_DIR, 'adapter')
    comparison = {'base': baseline, 'adapter': adapted,
        'exact_record_delta': adapted['exact_record_accuracy'] - baseline['exact_record_accuracy'],
        'same_ids': [row['id'] for row in rows], 'dataset_sha256': provenance['sha256']}
    (RUN_DIR / 'comparison.json').write_text(json.dumps(comparison, indent=2))
    print(json.dumps(comparison, indent=2))
    print('SYNTHETIC ONLY: not a real-bank accuracy claim.' if EVALUATION_KIND == 'SYNTHETIC' else 'Review the predictions and human labels before accepting the model.')
''')
md('''
## Check the exact portal API locally inside Colab

The request uses multipart **file**, optional **model**, and a Bearer API key. The response contains the six
portal fields, empty confidence scores, preserved document claims and deterministic review warnings.
This test uses the real loaded model. An unreadable/all-null result must be reviewed instead of marked successful.
The frontend already displays these warnings in its evidence comparison panel.
''')
code('api-check', '''
import secrets, json, tempfile
from pathlib import Path
from fastapi.testclient import TestClient
if 'worker_server' in globals() and worker_server.started and not worker_server.should_exit:
    raise RuntimeError('Stop the serving cell before running a separate API inference test.')
if globals().get('rows'):
    smoke_path = Path(rows[0]['_path'])
else:
    # Temporary fictional input for an API smoke test; no accuracy/leakage claim.
    smoke_manifest = make_synthetic_holdout(Path(tempfile.mkdtemp()) / 'api-smoke', count=2)
    smoke_record = json.loads(smoke_manifest.read_text().splitlines()[1])
    smoke_path = smoke_manifest.parent / smoke_record['image']
if 'WORKER_API_KEY' not in globals():
    WORKER_API_KEY = secrets.token_urlsafe(32)  # Reuse this runtime's key; never print it.
worker = create_app(infer, api_key=WORKER_API_KEY, model_id=MODEL_ID, policy=policy)
with TestClient(worker) as test_client:
    headers = {'Authorization': 'Bearer ' + WORKER_API_KEY}
    assert test_client.get('/health').status_code == 401
    assert test_client.get('/health', headers=headers).status_code == 200
    path = smoke_path
    mime = 'image/png' if path.suffix.lower() == '.png' else 'image/jpeg'
    response = test_client.post('/api/v1/extract-only', headers=headers,
        data={'model': MODEL_ID}, files={'file': (path.name, path.read_bytes(), mime)})
    print('API test status:', response.status_code)
    print(json.dumps(response.json(), indent=2))
    response.raise_for_status()
    assert set(response.json()) == {'fields', 'confidences', 'original_text', 'warnings'}
print('Portal request/response smoke test passed with the loaded adapter.')
''')
md('''
## Optional: connect your local portal to this temporary GPU worker

First inspect the API test (and evaluation if enabled). Set `START_WORKER = True` to serve the model. Store your ngrok
account token in Colab Secrets as `NGROK_AUTHTOKEN`, or enter it through the hidden prompt.
Open https://dashboard.ngrok.com/domains in the same account and request a development domain if none
exists. Copy the assigned hostname into Colab Secrets as `NGROK_DOMAIN` and enable notebook access,
or enter it when prompted. A Colab secret does not create the domain in your ngrok account.

This cell downloads **backend-vlm.env** to your computer. It contains the endpoint and a live API key;
copy those settings into your local `backend/.env`, then restart the backend. It is not saved in the shared
model folder or printed in notebook output. Keep the Colab runtime alive; a disconnect stops inference.
Only PNG/JPEG and a single-page PDF are supported. Export the FDR receipt page separately from multi-page bundles.
''')
code('serve', '''
START_WORKER = False
if START_WORKER:
    from pathlib import Path
    import sys, re, secrets, importlib
    if 'worker_server' in globals() and worker_server.started and not worker_server.should_exit:
        raise RuntimeError('Worker is already running. Use the stop cell before restarting.')
    package_root = Path('/content/depositflow_gemma_review')
    if not (package_root / 'gemma3_27b' / 'service.py').is_file():
        raise RuntimeError('Worker code is missing. Run the cell titled "Install the bundled, CPU-tested '
            'worker and evaluation code", or run bootstrap_colab.py, then rerun this cell. '
            'Do not pip-install gemma3_27b; it is bundled project code.')
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    importlib.invalidate_caches()
    from gemma3_27b.service import MODEL_ID, ReviewPolicy, create_app
    if (globals().get('model') is None or globals().get('processor') is None
            or not callable(globals().get('infer'))
            or not re.fullmatch(r'[a-f0-9]{64}', str(globals().get('adapter_sha256', '')))):
        raise RuntimeError('The loaded model, processor, inference function or adapter fingerprint is missing. '
            'Run the model-loading and inference cells first. After a runtime reset, also rerun '
            'the dependency, Drive configuration, bundled-code and holdout-preparation cells in order. '
            'Retraining is not required.')
    if 'policy' not in globals():
        policy = ReviewPolicy(globals().get('MINIMUM_TERM_YEARS'), globals().get('POLICY_REFERENCE', ''))
    if 'WORKER_API_KEY' not in globals():
        WORKER_API_KEY = secrets.token_urlsafe(32)
    worker = create_app(infer, api_key=WORKER_API_KEY, model_id=MODEL_ID, policy=policy)
    from google.colab import userdata, files
    from getpass import getpass
    from pyngrok import conf, ngrok
    import uvicorn, threading, time, httpx, socket, os, re
    try:
        ngrok_token = userdata.get('NGROK_AUTHTOKEN')
    except Exception:
        ngrok_token = getpass('Ngrok account token (hidden): ')
    if not ngrok_token: raise ValueError('An ngrok account token is required to open the tunnel.')
    try:
        ngrok_domain = userdata.get('NGROK_DOMAIN')
    except Exception:
        ngrok_domain = ''
    if not ngrok_domain:
        ngrok_domain = input('Assigned hostname from https://dashboard.ngrok.com/domains: ')
    ngrok_domain = ngrok_domain.strip().lower().removeprefix('https://').rstrip('/')
    if not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]{2,63}', ngrok_domain):
        raise ValueError('Enter the assigned hostname only, without a port, URL path or query.')
    # Pass the token through config; avoid parsing version-dependent CLI save messages.
    conf.get_default().auth_token = ngrok_token
    del ngrok_token
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    worker_server = uvicorn.Server(uvicorn.Config(worker, host='127.0.0.1', port=port,
        log_level='warning', access_log=False, limit_concurrency=4, timeout_keep_alive=5))
    worker_thread = threading.Thread(target=worker_server.run, daemon=True)
    worker_thread.start()
    for _ in range(100):
        if worker_server.started: break
        time.sleep(0.1)
    if not worker_server.started:
        worker_server.should_exit = True
        worker_thread.join(timeout=5)
        raise RuntimeError('Worker failed to start.')
    tunnel = None
    try:
        tunnel = ngrok.connect(addr=port, proto='http', domain=ngrok_domain, bind_tls=True)
        endpoint = tunnel.public_url.rstrip('/') + '/api/v1/extract-only'
        if not endpoint.startswith('https://'): raise RuntimeError('An HTTPS tunnel is required.')
        health = httpx.get(tunnel.public_url + '/health', headers={'Authorization': 'Bearer ' + WORKER_API_KEY}, timeout=30)
        health.raise_for_status()
    except Exception as exc:
        worker_server.should_exit = True
        if tunnel is not None:
            try: ngrok.disconnect(tunnel.public_url)
            except Exception: pass
        worker_thread.join(timeout=5)
        if 'ERR_NGROK_15013' in str(exc):
            raise RuntimeError('ngrok cannot find a development domain for this account. Request one at '
                'https://dashboard.ngrok.com/domains, ensure NGROK_AUTHTOKEN and NGROK_DOMAIN belong '
                'to the same account, then rerun only this server cell. The model remains loaded.') from None
        raise
    # This lives only in the temporary runtime and is downloaded directly, never saved into shared Drive.
    env_file = Path('/content/backend-vlm.env')
    settings_text = '\\n'.join([
        'EXTRACTION_PROVIDER=vlm_http', 'VLM_ENDPOINT=' + endpoint,
        'VLM_API_KEY=' + WORKER_API_KEY, 'VLM_MODEL=' + MODEL_ID,
        'VLM_MODEL_VERSION=gemma27b-' + adapter_sha256[:12], 'VLM_TIMEOUT_SECONDS=300', ''])
    fd = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle: handle.write(settings_text)
    del settings_text
    files.download(str(env_file))
    print('Worker ready. Merge the downloaded settings into backend/.env and restart your backend.')
    print('Do not use COLAB_VLM_ENDPOINT; this project reads VLM_ENDPOINT.')
''')
code('stop', '''
STOP_WORKER = False
if STOP_WORKER:
    if globals().get('tunnel') is not None: ngrok.disconnect(tunnel.public_url)
    if 'worker_server' in globals(): worker_server.should_exit = True
    if 'worker_thread' in globals(): worker_thread.join(timeout=10)
    print('This notebook worker has been stopped.')
''')
md('''
## Real holdout format and next steps

Put each human-labelled page under `ROOT/real_holdout/` and write one JSON object per line in `test.jsonl`:

```json
{"id":"unseen-001","group_id":"source-document-001","kind":"real","image":"images/unseen-001.png","fields":{"bank":"Visible bank name","number":"VISIBLE-REFERENCE","depositor_name":"Visible institution","amount":"1500000.00","issue_date":"2025-06-15","maturity_date":"2033-06-15"},"document_claims":{"joint_holding":null,"lien":null,"stamp":null}}
```

Labels must match visible image content; use null for missing/unclear values. Claim labels describe the image,
not bank truth. All pages/crops/near-duplicates from the same document must stay out of training. Exact pixel
hash checks are included; independent provenance still needs human review. Do not train or tune on this holdout.

Each run saves labels, dataset fingerprint, package versions, adapter hash, prompt, policy, baseline/adapter raw
predictions and comparison metrics. No training occurs and existing adapter files are never overwritten.
If the adapter performs worse than its base, inspect the errors before further fine-tuning. Do not equate a
successful HTTP call or low training loss with production readiness.

Sources: [Gemma 3 Unsloth guide](https://unsloth.ai/docs/models/tutorials/gemma-3-how-to-run-and-fine-tune),
[PEFT checkpoint format](https://huggingface.co/docs/peft/main/en/developer_guides/checkpoint).
''')
for i, cell in enumerate(cells):
    cell.setdefault('id', f'notes-{i}')
    cell['source'] = cell['source'].splitlines(keepends=True)
    if cell['cell_type'] == 'code': compile(''.join(cell['source']), cell['id'], 'exec')
notebook = {'nbformat': 4, 'nbformat_minor': 5,
    'metadata': {'accelerator': 'GPU', 'colab': {'name': 'Gemma3_27B_Review_and_Serve.ipynb', 'provenance': []},
                 'kernelspec': {'display_name': 'Python 3', 'name': 'python3'}, 'language_info': {'name': 'python'}},
    'cells': cells}
(HERE / 'Gemma3_27B_Review_and_Serve.ipynb').write_text(json.dumps(notebook, indent=2, ensure_ascii=False) + '\n')
(HERE / 'serve_colab.py').write_text('# Paste this cell into your existing Colab session; set START_WORKER=True to run.\n'
    + ''.join(next(cell['source'] for cell in cells if cell.get('id') == 'serve')))
(HERE / 'bootstrap_colab.py').write_text('# Run in Colab to restore the bundled worker without reloading model weights.\n'
    + ''.join(next(cell['source'] for cell in cells if cell.get('id') == 'bundled-code')))
print('Generated self-contained notebook:', len(cells), 'cells; all Python cells compile.')
