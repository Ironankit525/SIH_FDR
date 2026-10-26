# Train the DepositFlow vision model in Google Colab

For your **separate, already-trained Gemma 3 27B adapter**, use the [27B evaluation and integration guide](gemma3_27b/README.md) and its [self-contained Colab notebook](gemma3_27b/Gemma3_27B_Review_and_Serve.ipynb). The instructions below are for the earlier 8B training plan.

Use [DepositFlow_Qwen3_VL_8B_Colab.ipynb](DepositFlow_Qwen3_VL_8B_Colab.ipynb). It contains the installation, dataset preparation, training, evaluation, saving, and reload code. [colab_train_qwen3_vl_8b.py](colab_train_qwen3_vl_8b.py) is the same code exported as labelled cells for reference; use the notebook in Colab.

This fine-tunes **Qwen3-VL-8B-Instruct** with **4-bit QLoRA**. The model reads receipt images directly and returns six fields: bank, FDR number, depositor, amount, issue date, and maturity date. It does not require Tesseract. It does not authenticate a bank receipt or approve a release.

## 1. Open the notebook and enable a GPU

1. Go to [Google Colab](https://colab.research.google.com/).
2. Choose **File → Upload notebook** and select `DepositFlow_Qwen3_VL_8B_Colab.ipynb` from this directory.
3. Choose **File → Save a copy in Drive** to retain the notebook itself.
4. Choose **Runtime → Change runtime type → GPU**. Start with your available 16 GB GPU.
5. Run the GPU check and installation cells. If Colab asks to restart, restart and continue at **Mount Drive**.
6. Run the Mount Drive cell and authorize access to your own Drive.

The first model download is large. Allow space for the base model in the runtime, plus your dataset, adapter and two optimizer checkpoints in Drive. Check available storage before a long run. No Hugging Face token is required for the public checkpoint used here.

**16 GB is a target to test, not a guaranteed fit.** The notebook uses batch size 1, a frozen vision encoder, language-side LoRA rank 16, gradient checkpointing and a limited image resolution. It checks forward/backward memory before training. Optimizer creation and generation can still require additional memory. This is adapter fine-tuning, not full training of all eight billion parameters.

## 2. Run the fictional demo first

Keep these settings in the configuration cell:

```python
MODE = 'DEMO'
RESUME = False
DEMO_MAX_STEPS = 20
```

Continue running cells in order through **final-evaluation**. Leave the last two optional cells disabled for now.

The notebook creates 90 visibly fictional receipt images: 60 training, 15 validation, and 15 test. It checks labels and split isolation, previews the input resolution, loads the model, runs a memory check, measures the pretrained baseline, trains for 20 optimizer steps and saves the adapter before evaluating it. By default, baseline and final evaluation use the same six held-out test examples.

This demo only checks that the pipeline works. Its scores do not demonstrate accuracy on real receipts. Do not use a demo-trained adapter as a validated production extractor.

## 3. Prepare your real training dataset

Create this folder in Drive:

```text
MyDrive/DepositFlow_VLM_8B/dataset/
├── train.jsonl
├── validation.jsonl
├── test.jsonl
└── images/
    ├── receipt-001-page-1.png
    ├── receipt-002-page-1.jpg
    └── ...
```

Each JSONL file contains one JSON object per line. Example:

```json
{"id":"receipt-001-page-1","group_id":"receipt-001","image":"images/receipt-001-page-1.png","fields":{"bank":"Example Bank","number":"DEMO-001","depositor_name":"Example Institute","amount":"1500000.00","issue_date":"2026-01-15","maturity_date":null}}
```

- Supply all six field keys; use JSON `null` for absent, ambiguous or unreadable values.
- Label only text visible on that image. Do not fill missing fields using a bank response or an institution's form.
- Write amounts as decimal strings without commas and dates as unambiguous `YYYY-MM-DD` values.
- Render PDF pages to PNG/JPG before training and label each page separately. PDF rendering does not perform OCR.
- Keep every page, crop and augmentation of the same receipt in one split, with the same `group_id`. Keep related renewals or near-duplicates together as well.
- Reserve validation data for choosing settings and test data for final measurement. A starting split is roughly 80%/10%/10%, by source-document group. Each split must be nonempty.
- Include varied layouts, legible scans/photos, missing fields and realistic image quality. Hold out some layouts to measure generalisation. Repeating a handful of examples cannot establish general extraction ability.

The validator rejects invalid labels, repeated IDs, exact duplicate image pixels, and source groups shared across splits. Review near-duplicates manually; hashing does not catch every variation of the same document.

## 4. Train on real receipts

Start a new GPU session or restart the existing runtime to release the demo model. Run the installation if needed, then change:

```python
MODE = 'REAL'
RESUME = False
# Leave RUN_NAME generating a new timestamp.
EPOCHS = 2
EVAL_SAMPLES = 0  # Evaluate every held-out test image; takes longer.
```

Run the notebook through **final-evaluation**. Inspect the resized preview: if digits are unreadable, use better source images, correctly labelled crops, or more resolution with sufficient VRAM. Do not train on illegible inputs while supplying answers the image cannot support.

Validation loss selects the best saved checkpoint. Review `comparison.json` and the raw predictions to see whether fine-tuning actually improves extraction. Invalid JSON counts as failure; the evaluation also counts invented values where the human label is null. Do not choose training settings by repeatedly inspecting test scores.

If you run out of memory, start a fresh runtime and try `LORA_R = 8`. You can reduce `MAX_PIXELS` only if the preview remains readable. If it still fails, use a larger GPU or a smaller model. Do not keep retrying an already exhausted runtime.

## 5. Find the saved model in Drive

The save cell prints the exact directory:

```text
MyDrive/DepositFlow_VLM_8B/runs/<RUN_NAME>/
├── adapter/
│   ├── adapter_model.safetensors
│   ├── adapter_config.json
│   ├── training_manifest.json
│   ├── extraction_prompt.txt
│   └── processor and tokenizer files
├── checkpoints/
├── run_config.json
├── base_revision.txt
├── environment.freeze.txt
├── test_selection.json
├── baseline_metrics.json
├── baseline_predictions.json
├── finetuned_metrics.json
├── finetuned_predictions.json
├── comparison.json
└── training_metrics.json
```

**Keep the whole adapter folder.** It contains the learned LoRA weights and processor configuration, not a standalone copy of all base-model weights. Reloading needs the recorded base checkpoint as well. Keep the run configuration and dependency record for reproduction. The notebook does not upload anything to GitHub or Hugging Face or change Drive sharing settings.

Checkpoints also contain training state for resuming. They are written directly to Drive every ten optimizer steps by default; writes take time. Wait for a save to finish before disconnecting. Progress since the last complete checkpoint may be lost.

## 6. Resume interrupted training

In a fresh session, install dependencies and set the original values in the configuration cell:

```python
MODE = 'REAL'  # Or DEMO, matching the interrupted run.
RUN_NAME = 'fdr-PASTE-YOUR-ORIGINAL-RUN-NAME'
RESUME = True
```

Restore the same dataset and settings, then run through the training cells. The notebook compares the saved configuration and dataset fingerprint before continuing. It retains the original baseline and resumes the latest checkpoint. If a disconnect interrupted a checkpoint write, use an earlier complete checkpoint instead; do not delete your only usable copy. If no checkpoint was saved yet, use a new run name and `RESUME = False`.

## 7. Test a saved adapter without training again

In a fresh GPU session, run the installation and mount Drive. Skip the dataset/model/training cells. In **Reload after a disconnect**, set:

```python
RELOAD_SAVED_MODEL = True
SAVED_ADAPTER = '/content/drive/MyDrive/DepositFlow_VLM_8B/runs/YOUR_RUN_NAME/adapter'
```

Run that cell. Then in **Try your own image or one PDF page**, set:

```python
RUN_CUSTOM_INFERENCE = True
INPUT_FILE = '/content/drive/MyDrive/my-receipt.pdf'
PDF_PAGE_INDEX = 0
```

Run the cell to see the extracted JSON. PNG/JPG inputs also work. A PDF is rendered one page at a time. Inspect the result against the original receipt; model output is not verified bank evidence.

## Validation and portal integration

The notebook's Python cells, fictional dataset generation, label validation and metric functions are checked locally. **GPU loading, training and saving have not been executed here.** Run the demo in Colab before investing in a full training run.

Installation follows [Unsloth's Qwen3-VL 8B notebook](https://colab.research.google.com/github/unslothai/notebooks/blob/main/nb/Qwen3_VL_%288B%29-Vision.ipynb) and [vision fine-tuning guide](https://unsloth.ai/docs/basics/vision-fine-tuning), with Transformers 4.57.6 and TRL 0.22.2. Some accelerator packages remain unpinned, as in the upstream installation. The exact installed versions are saved per run; future Colab/package changes may require updates.

This delivery adds training artifacts only. Connecting the trained adapter to the portal is a separate step: load the base model and adapter in a GPU inference service, authenticate requests, validate returned fields, and retain extraction provenance. The existing portal OCR configuration has not been changed. A temporary Colab session should not be treated as a permanent production API.
