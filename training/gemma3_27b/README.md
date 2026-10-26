# Evaluate and connect the separate Gemma 3 27B model

Open **[Gemma3_27B_Review_and_Serve.ipynb](Gemma3_27B_Review_and_Serve.ipynb)** in Google Colab. It is self-contained: uploading this one notebook is enough. It loads your existing adapter from `MyDrive/SIH26265_AICTE_VLM_27B_12B/fine_tuned_vlm_lora`; it does not retrain, overwrite it, or use the earlier 8B model.

**First-time team setup:** follow [VLM_SETUP.md](../../docs/VLM_SETUP.md) for laptop installation, Drive model access, ngrok setup and every notebook cell. The default `RUN_EVALUATION=False` serves the saved model without training images or a holdout benchmark. Code is in Git; trained weights and worker credentials must be obtained separately.

## What is fixed

- The worker accepts the portal's multipart `file` and `model` fields and Bearer authentication, and returns its exact `fields`, `confidences`, `original_text`, `warnings` contract. No backend schema weakening or frontend redesign is needed.
- The model is prompted to extract depositor/institution name, literal holding/lien text, and the six portal fields. Old output names remain supported. A missing name stays null and gets a review warning.
- Review flags are computed by Python from extracted claims and dates. The model's `document_scrutiny_flags` array is ignored. A regression test using your saved prediction reconstructs the missing joint-holding, lien and configured-term flags even when that array is empty.
- Claims describe the receipt. They do not establish bank confirmation, stamp authenticity or approval. Old `*_verified` booleans are retained only as unverified document claims, with an explicit warning that their quote is missing. Conflicting claims go to manual review.
- No universal eight-year rule is installed. By default the worker reports that a term rule is not configured. A threshold requires an explicit reference and applies only to the extracted instrument term, not overall release eligibility. Eight years is used only in the explicitly illustrative regression test unless you deliberately configure it.
- PNG/JPEG and single-page PDFs are supported. Multi-page PDFs are explicitly rejected with instructions to upload the receipt page separately; no pages or conflicting receipts are silently merged. No OCR is used by this worker.
- Authentication precedes upload parsing; actual request bytes, file size and image dimensions are capped. GPU inference is serialized. Busy/failing inference returns retryable status codes; invalid or all-null extraction is rejected. Error responses omit internal exception details.

The existing frontend already renders extraction warnings in the side-by-side evidence panel. These warnings do not replace the existing verification or release workflow.

## Run in Colab

1. Upload the notebook to Colab and save a copy in your Drive. Use a fresh **A100 GPU runtime**, matching the class used for your recorded 27B run. GPU reload has not been executed locally; do not assume a smaller GPU will fit.
2. Run the install cell. If Colab requests a restart, restart and continue at Mount Drive. Unsloth 2026.10.8, Transformers 5.17.0 and PEFT 0.21.2 match the versions recorded in your run/export. Transitive GPU dependencies resolve for the runtime; the full package list is saved per evaluation.
3. Mount Drive. Confirm `ROOT` points to the folder containing your saved adapter. Leave `RUN_EVALUATION=False` for serving; training images are not required. For evaluation, set it to `True`, point `TRAINING_IMAGES` to the original training images, and choose `EVALUATION_KIND`.
4. Run bundled code, holdout preparation, model loading, **Define receipt inference**, evaluation and API check in order. With evaluation disabled the holdout/benchmark cells skip their work and the API check generates a fictional smoke-test receipt. It still performs one actual model inference. No training happens.
5. If evaluation is enabled, the default synthetic benchmark creates 24 fictional receipts and checks exact pixel duplication against the training folder. Review `comparison.json`, prediction files, and per-field results. The baseline disables LoRA; the adapted pass uses the same inputs and generation settings. Synthetic scores do not establish real-bank accuracy.
6. To serve the model, set `START_WORKER = True` in the optional server cell. Put your ngrok account token in Colab Secrets as `NGROK_AUTHTOKEN`, or enter it through the hidden prompt. Open [ngrok Domains](https://dashboard.ngrok.com/domains) in that same account; request/create the assigned development domain if none exists. Add its hostname as `NGROK_DOMAIN` in Colab Secrets and enable notebook access for both secrets, or enter the hostname when prompted. The API has a separate random Bearer key; the ngrok account token is not API authentication.
7. The cell downloads `backend-vlm.env` to your computer. From the project root run `.venv/bin/python scripts/connect_vlm.py /path/to/backend-vlm.env` to validate worker health and merge only its connection settings. Restart the backend, then upload a new instrument receipt. The existing instrument-extraction job will use `vlm_http`. For teammates sharing this worker, follow [the team testing guide](../../docs/TEAM_TESTING.md).

The downloaded settings use **`VLM_ENDPOINT`**, including `/api/v1/extract-only`, not `COLAB_VLM_ENDPOINT`. `VLM_MODEL_VERSION` records an adapter fingerprint. The worker API key is never printed or saved to the shared Drive model folder. The updated cells reuse the key within a runtime; a fresh runtime creates a new key, so import the new settings after restarting the session.

Keep Colab running while the portal uses it. A session/tunnel disconnect stops the service and the backend will retry failures within its existing limits. To return to local OCR, set `EXTRACTION_PROVIDER=ocr` and restart the backend. Stop this worker using the final optional stop cell.

For `ERR_NGROK_15013`, first ensure a development domain exists in the ngrok account associated with your token. Setting a Colab secret alone cannot create it. The [updated server cell](serve_colab.py) can be pasted into your current notebook; set `START_WORKER=True` and run only that cell. A failed tunnel attempt stops its local HTTP server but leaves the loaded model intact, so retraining, reevaluation, and restarting the GPU runtime are unnecessary. Local notebook updates do not automatically change an already uploaded Colab copy.

Only instrument uploads use the configured VLM; existing supporting-document handling is unchanged. Already completed extractions are not silently overwritten by changing the provider. Use a new receipt upload for the integration check.

### Recover from `No module named 'gemma3_27b'`

This is bundled project code, not a package to install from PyPI. The serving cell alone does not create it.

1. In your Colab notebook rerun **Install the bundled, CPU-tested worker and evaluation code**. If your notebook lacks that cell, upload [bootstrap_colab.py](bootstrap_colab.py) using Colab's Files sidebar and copy its actual path. Run `%run /content/bootstrap_colab.py` if it is under `/content`, or `%run /bootstrap_colab.py` if it is at `/`. Use a notebook code cell, not the terminal. This restores the package, refreshes cached imports and leaves model weights loaded.
2. Paste the updated [serve_colab.py](serve_colab.py) into the serving cell, set `START_WORKER = True`, and run it. It restores the import path and checks that the model, processor, inference function and adapter fingerprint exist before opening a tunnel.
3. If Colab reset the runtime, run dependencies, Drive configuration, bundled code, holdout preparation, model loading and inference in notebook order first. Previously saved weights remain on Drive; no retraining is needed. The evaluation benchmark need not be repeated merely to restart serving.
4. Import the newly downloaded `backend-vlm.env` with `scripts/connect_vlm.py`, then restart your backend.

The updated server passes the ngrok token through [pyngrok configuration](https://pyngrok.readthedocs.io/en/stable/api.html#pyngrok.conf.PyngrokConfig), avoiding the CLI message parsing that caused the earlier “Authtoken already set” error. It still checks tunnel creation and authenticated worker health.

## Evaluate genuinely unseen receipts

Prepare human-labelled images that were excluded from every training/tuning run:

```text
SIH26265_AICTE_VLM_27B_12B/real_holdout/
  test.jsonl
  images/receipt-001.png
  images/receipt-002.jpg
```

Each JSONL line must have all six field labels and three document-claim labels:

```json
{"id":"unseen-001","group_id":"source-001","kind":"real","image":"images/receipt-001.png","fields":{"bank":"Visible bank name","number":"VISIBLE-REFERENCE","depositor_name":"Visible institution name","amount":"1500000.00","issue_date":"2025-06-15","maturity_date":"2033-06-15"},"document_claims":{"joint_holding":null,"lien":null,"stamp":null}}
```

Use null for absent, ambiguous or unreadable values. Claim labels describe what the image says/shows, not whether a bank has confirmed it. Render individual PDF pages before labelling. Do not attach a whole document's answer to a page lacking that text.

Keep related scans, pages, crops, renewals and other near-duplicates out of training. `group_id` records the source grouping; the code cannot reconstruct the old notebook's missing training manifests. Pixel hashes catch exact duplicates only. Hold out different layouts as well, and do not tune against the final test set.

Choose `RUN_EVALUATION = True` and `EVALUATION_KIND = 'REAL'` and rerun in a new evaluation directory. The notebook rejects synthetic-labelled rows in REAL mode, but human provenance review remains necessary. It reports schema validity, exact-record and per-field accuracy, visible-field accuracy, invented values on null labels, document-review flag precision/recall and latency. Invalid predictions count as failures. Hardware/runtime errors stop evaluation instead of becoming misleading accuracy scores.

The original 36 examples have no validation/test split. Do not relabel them as unseen or claim the new synthetic benchmark measures real-document performance. If the adapted model underperforms its base, inspect errors before deciding whether to retrain.

## Saved artifacts

Every run saves model/prompt/environment metadata under `MyDrive/SIH26265_AICTE_VLM_27B_12B/review_runs/<RUN_NAME>/`. Serving mode records a null dataset and no accuracy metrics. With evaluation enabled, the directory also contains the dataset fingerprint and labels, extraction prompt, policy settings, adapter weight hash, installed package versions, base/adapter raw predictions, per-run metrics and comparison. Original weights remain unchanged. `minimum_years=None` intentionally reports an unconfigured term check instead of clearance.

## Local validation and source files

- [service.py](service.py): strict model-output normalization, deterministic review flags, bounded image/PDF loading and authenticated worker.
- [evaluation.py](evaluation.py): saved-label holdout generation, exact-image leakage checks, baseline/adapter metrics and raw prediction output.
- [test_worker.py](test_worker.py): CPU regression, upload, authentication, error, duplicate-detection and metric tests.
- [../../backend/tests/test_gemma_worker_contract.py](../../backend/tests/test_gemma_worker_contract.py): real portal HTTP client exercised against the worker using inference stubs.
- [build_notebook.py](build_notebook.py): regenerates the self-contained notebook from the tested modules.

From the project root:

```bash
.venv/bin/python -m pytest training/gemma3_27b/test_worker.py training/gemma3_27b/test_colab_setup.py -q
cd backend
../.venv/bin/python -m pytest tests/test_gemma_worker_contract.py -q
```

These tests verify software behavior, not 27B model accuracy. A real fresh-session GPU reload and held-out evaluation must be run in Colab. Repository updates do not edit your existing shared notebook or start a GPU job; upload the updated notebook or copy the recovery cells explicitly.
