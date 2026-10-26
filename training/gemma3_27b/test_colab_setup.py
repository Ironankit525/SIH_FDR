"""Exercise exported Colab setup without a GPU, network or Colab runtime."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


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
         f'bootstrap = {bootstrap!r}\npreflight = {preflight!r}\n' + body],
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
