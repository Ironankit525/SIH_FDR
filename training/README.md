# DepositFlow VLM — Gemma 3 27B

The current project uses **Gemma 3 27B with our trained LoRA adapter**. The model runs on a Google Colab GPU. Each teammate runs the frontend and backend on their own laptop and connects the backend to Colab through an authenticated ngrok HTTPS endpoint.

**Start with [the complete Colab + ngrok + laptop setup guide](../docs/VLM_SETUP.md).** No new training is required to run the saved model.

## Current model and files

| Item | Used by this project |
| --- | --- |
| Model | Gemma 3 27B |
| Base checkpoint | `unsloth/gemma-3-27b-it-unsloth-bnb-4bit` |
| Trained adapter | `fine_tuned_vlm_lora` in the model owner's Google Drive |
| Colab notebook | [Gemma3_27B_Review_and_Serve.ipynb](gemma3_27b/Gemma3_27B_Review_and_Serve.ipynb) |
| Worker implementation | [gemma3_27b/service.py](gemma3_27b/service.py) |
| Serving and optional evaluation details | [gemma3_27b/README.md](gemma3_27b/README.md) |
| Team workflow tests | [TEAM_TESTING.md](../docs/TEAM_TESTING.md) |

Git contains the code and notebook. The trained weights remain in Drive. Teammates using an existing worker need its current `backend-vlm.env` privately from the owner; teammates running their own worker also need access to the complete adapter export.

## Start your own Colab worker

1. Upload the linked Gemma 3 27B notebook to Colab and select the A100 80 GB GPU class used by the recorded session.
2. Run dependency installation, mount Drive, and set `ROOT` to the folder containing `fine_tuned_vlm_lora`.
3. Leave `RUN_EVALUATION = False` for serving. Run the bundled-code, model-loading and **Define receipt inference** cells in notebook order. The holdout/benchmark cells skip evaluation in this mode.
4. Run the local API smoke-test cell to check a real model inference.
5. Add `NGROK_AUTHTOKEN` and `NGROK_DOMAIN` in Colab Secrets, using the same ngrok account for both.
6. Run the serving cell with `START_WORKER = True`. It downloads `backend-vlm.env` to your laptop. Leave `STOP_WORKER = False` while testing.

The complete guide explains model-folder access, every cell, ngrok account setup, and recovery from missing imports, missing `infer`, missing files and connection errors. Keep the Colab worker running while the portal uses it.

## Connect your laptop

After cloning `llm_integerate` and installing dependencies as described in [the setup guide](../docs/VLM_SETUP.md), run these commands in your laptop terminal from the repository root:

```bash
.venv/bin/python scripts/connect_vlm.py "$HOME/Downloads/backend-vlm.env"
.venv/bin/python scripts/prepare_team_demo.py
python3 scripts/dev.py
```

Use the actual downloaded filename if your browser added a suffix such as `(3)`. If the app is already running, stop its launcher with Ctrl+C before restarting it with the new settings.

Open **http://localhost:5173** and follow the [receipt and workflow tests](../docs/TEAM_TESTING.md). Upload receipts with category **Instrument**. The VLM extracts document fields; the backend compares them with submitted information and independent bank findings. Successful extraction alone does not authenticate a receipt.

## Optional evaluation and historical reference

To evaluate the trained Gemma adapter, follow [the evaluation guide](gemma3_27b/README.md) with `RUN_EVALUATION = True` and the required dataset. Serving does not require the training dataset. Software tests and the API smoke test do not establish model accuracy.

The [archived training experiment](LEGACY_8B.md) is retained for historical reference and is not part of this setup.
