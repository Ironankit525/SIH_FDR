"""Exercise exported Colab setup without a GPU, network or Colab runtime."""
import subprocess
import sys
import json
from pathlib import Path

HERE = Path(__file__).parent


def notebook_cell(name):
    notebook = json.loads((HERE / 'Gemma3_27B_Review_and_Serve.ipynb').read_text())
    return ''.join(next(cell['source'] for cell in notebook['cells'] if cell['id'] == name))


def test_serving_mode_skips_holdout_and_benchmark_without_training_data():
    namespace = {'RUN_EVALUATION': False}
    exec(notebook_cell('prepare-holdout'), namespace)
    exec(notebook_cell('evaluate'), namespace)
    assert namespace['provenance'] is None
    assert namespace['rows'] == []
    assert 'comparison' not in namespace


def test_model_load_metadata_does_not_require_provenance_for_serving(tmp_path, monkeypatch):
    from types import ModuleType, SimpleNamespace
    import hashlib
    from .service import MODEL_ID, PROMPT
    adapter = tmp_path / 'adapter'
    adapter.mkdir()
    for name in ('adapter_model.safetensors', 'processor_config.json', 'tokenizer_config.json', 'tokenizer.json'):
        (adapter / name).write_text('stub, not real weights')
    (adapter / 'adapter_config.json').write_text(json.dumps({'base_model_name_or_path': MODEL_ID}))
    fake_model = SimpleNamespace(config=SimpleNamespace(_commit_hash='stub'), eval=lambda: None)
    fake_processor = object()
    unsloth = ModuleType('unsloth')
    unsloth.FastVisionModel = SimpleNamespace(
        from_pretrained=lambda **kwargs: (fake_model, fake_processor), for_inference=lambda model: None)
    torch = ModuleType('torch')
    torch.cuda = SimpleNamespace(is_available=lambda: True, get_device_name=lambda _: 'CPU test stub',
                                 get_device_properties=lambda _: SimpleNamespace(total_memory=80 * 2**30))
    monkeypatch.setitem(sys.modules, 'unsloth', unsloth)
    monkeypatch.setitem(sys.modules, 'torch', torch)
    monkeypatch.setattr(subprocess, 'check_output', lambda *args, **kwargs: 'stub-environment')
    namespace = {'ADAPTER_DIR': adapter, 'RUN_DIR': tmp_path, 'RUN_EVALUATION': False,
                 'MODEL_ID': MODEL_ID, 'PROMPT': PROMPT, 'MINIMUM_TERM_YEARS': None,
                 'POLICY_REFERENCE': '', 'MAX_CONTEXT_TOKENS': 2048, 'MAX_NEW_TOKENS': 640,
                 'json': json, 'hashlib': hashlib}
    exec(notebook_cell('load-model'), namespace)
    info = json.loads((tmp_path / 'run_info.json').read_text())
    assert info['dataset'] is None and info['evaluation_requested'] is False
    assert namespace['model'] is fake_model and namespace['processor'] is fake_processor
    assert namespace['adapter_sha256'] == hashlib.sha256(b'stub, not real weights').hexdigest()
    namespace['RUN_EVALUATION'] = True
    import pytest
    with pytest.raises(RuntimeError, match='holdout-preparation'):
        exec(notebook_cell('load-model'), namespace)


def test_api_smoke_cell_works_without_holdout_and_keeps_session_key(tmp_path, monkeypatch):
    import tempfile
    from .service import MODEL_ID, ReviewPolicy, create_app
    from .evaluation import make_synthetic_holdout
    calls = []
    def infer(image):
        calls.append(image.size)
        return '{"fdr_number":"SMOKE-ONLY", "deposit_amount":3500000}'
    monkeypatch.setattr(tempfile, 'mkdtemp', lambda: str(tmp_path))
    key = 'test-only-' + 'c' * 40
    namespace = {'MODEL_ID': MODEL_ID, 'policy': ReviewPolicy(), 'create_app': create_app,
                 'make_synthetic_holdout': make_synthetic_holdout, 'infer': infer, 'WORKER_API_KEY': key}
    exec(notebook_cell('api-check'), namespace)
    assert len(calls) == 1
    assert namespace['WORKER_API_KEY'] == key
    assert 'provenance' not in namespace and 'rows' not in namespace


def run_setup(tmp_path, body):
    package_root = tmp_path / 'review'
    bootstrap = (HERE / 'bootstrap_colab.py').read_text().replace(
        '/content/depositflow_gemma_review', str(package_root))
    serve = (HERE / 'serve_colab.py').read_text().replace(
        '/content/depositflow_gemma_review', str(package_root)).replace(
        'START_WORKER = False', 'START_WORKER = True')
    # Stop at the boundary to external services; exercise the real startup preflight.
    preflight = serve.split('    from google.colab import userdata, files')[0]
    result = subprocess.run(
        [sys.executable, '-c',
         f'bootstrap = {bootstrap!r}\npreflight = {preflight!r}\nroot_path = {str(package_root)!r}\n' + body],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr


def test_missing_package_explains_recovery_before_external_imports(tmp_path):
    run_setup(tmp_path, '''
try:
    exec(preflight)
except RuntimeError as error:
    assert 'bootstrap_colab.py' in str(error)
    assert 'bundled' in str(error)
else:
    raise AssertionError('Missing package must stop startup')
assert 'WORKER_API_KEY' not in globals()
''')


def test_bootstrap_restores_package_without_model_or_configuration(tmp_path):
    run_setup(tmp_path, '''
exec(bootstrap)
assert (package / 'service.py').is_file()
assert policy.minimum_years is None
assert 'model' not in globals()
try:
    exec(preflight)
except RuntimeError as error:
    assert 'model-loading and inference cells' in str(error)
else:
    raise AssertionError('Missing model must stop startup')
assert 'WORKER_API_KEY' not in globals()
''')


def test_preflight_restores_import_path_and_keeps_existing_key(tmp_path):
    run_setup(tmp_path, '''
exec(bootstrap)
sys.path.remove(str(package_root))
model, processor = object(), object()
infer = lambda image: '{}'
adapter_sha256 = 'a' * 64
WORKER_API_KEY = 'test-only-' + 'b' * 40
previous_key = WORKER_API_KEY
exec(preflight)
assert str(package_root) in sys.path
assert WORKER_API_KEY == previous_key
from fastapi.testclient import TestClient
with TestClient(worker) as client:
    assert client.get('/health').status_code == 401
    assert client.get('/health', headers={'Authorization': 'Bearer ' + previous_key}).status_code == 200
''')


def test_bootstrap_recovers_after_cached_failed_import(tmp_path):
    run_setup(tmp_path, '''
import sys, importlib
sys.path.insert(0, root_path)
try:
    importlib.import_module('gemma3_27b')
except ModuleNotFoundError:
    pass
else:
    raise AssertionError('Worker package must initially be absent')
assert root_path in sys.path_importer_cache
assert sys.path_importer_cache[root_path] is None
exec(bootstrap)
from gemma3_27b.service import create_app
assert callable(create_app)
assert 'model' not in globals()
''')
