# Paste this cell into your existing Colab session; set START_WORKER=True to run.
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
    if not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', ngrok_domain):
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
    settings_text = '\n'.join([
        'EXTRACTION_PROVIDER=vlm_http', 'VLM_ENDPOINT=' + endpoint,
        'VLM_API_KEY=' + WORKER_API_KEY, 'VLM_MODEL=' + MODEL_ID,
        'VLM_MODEL_VERSION=gemma27b-' + adapter_sha256[:12], 'VLM_TIMEOUT_SECONDS=300', ''])
    fd = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle: handle.write(settings_text)
    del settings_text
    files.download(str(env_file))
    print('Worker ready. Merge the downloaded settings into backend/.env and restart your backend.')
    print('Do not use COLAB_VLM_ENDPOINT; this project reads VLM_ENDPOINT.')
