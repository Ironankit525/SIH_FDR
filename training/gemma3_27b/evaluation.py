"""Held-out evaluation with saved labels, leakage checks and no training calls."""
from __future__ import annotations

import hashlib
import json
import random
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .service import FIELDS, RawExtraction, ReviewPolicy, document_image, portal_response, scrutiny_flags


def pixel_hash(path: Path) -> str:
    content_type = 'image/png' if path.suffix.lower() == '.png' else 'image/jpeg'
    with document_image(path.read_bytes(), content_type) as image:
        return hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()


def load_manifest(manifest: Path, training_images: Path) -> tuple[list[dict], dict]:
    manifest, training_images = manifest.resolve(), training_images.resolve()
    if not training_images.is_dir():
        raise ValueError('Point training_images to the original fdr_dataset_images folder for leakage checks.')
    train_files = [p for p in training_images.rglob('*') if p.suffix.lower() in ('.png', '.jpg', '.jpeg')]
    if not train_files:
        raise ValueError('Training image directory is empty; leakage check cannot run.')
    training_hashes = {pixel_hash(path) for path in train_files}
    rows, ids, hashes, fingerprint = [], set(), set(), []
    for line in manifest.read_text().splitlines():
        if not line.strip(): continue
        row = json.loads(line)
        if not isinstance(row, dict): raise ValueError('Every manifest line must be an object.')
        for key in ('id', 'group_id', 'image'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError('Each row requires id, group_id and image.')
        if row['id'] in ids: raise ValueError('Duplicate evaluation id.')
        ids.add(row['id'])
        if row.get('kind') not in ('synthetic', 'real'):
            raise ValueError('Every row must declare kind=synthetic or real.')
        if set(row.get('fields', {})) != set(FIELDS):
            raise ValueError('Human labels must contain all six portal field keys.')
        expected = row['fields']
        validated = RawExtraction.model_validate({
            'issuing_bank': expected['bank'], 'fdr_number': expected['number'],
            'institution_name': expected['depositor_name'], 'deposit_amount': expected['amount'],
            'issue_date': expected['issue_date'], 'maturity_date': expected['maturity_date'],
        })
        row['fields'] = dict(zip(FIELDS, (validated.issuing_bank, validated.fdr_number,
                                        validated.institution_name, validated.deposit_amount,
                                        validated.issue_date, validated.maturity_date)))
        if any(isinstance(v, str) and len(v) > 200 for v in row['fields'].values()):
            raise ValueError('Human label exceeds portal field length.')
        expected_claims = row.get('document_claims')
        if not isinstance(expected_claims, dict) or set(expected_claims) != {'joint_holding', 'lien', 'stamp'}:
            raise ValueError('Provide document_claims with joint_holding, lien and stamp (true/false/null).')
        if any(value is not None and type(value) is not bool for value in expected_claims.values()):
            raise ValueError('Claim labels must be boolean or null, not strings.')
        path = (manifest.parent / row['image']).resolve()
        if not path.is_relative_to(manifest.parent) or path.is_relative_to(training_images):
            raise ValueError('Evaluation image must be inside its dataset folder, outside training data.')
        if path.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
            raise ValueError('Label each page as a PNG/JPG image for evaluation.')
        digest = pixel_hash(path)
        if digest in training_hashes: raise ValueError('Evaluation image duplicates a training image.')
        if digest in hashes: raise ValueError('Duplicate evaluation image pixels.')
        hashes.add(digest)
        row['_path'] = str(path)
        rows.append(row)
        fingerprint.append({k: v for k, v in row.items() if k != '_path'} | {'pixel_sha256': digest})
    if not rows: raise ValueError('Evaluation manifest is empty.')
    return rows, {'sha256': hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest(),
                  'examples': len(rows), 'training_images_checked': len(train_files),
                  'kinds': sorted({r['kind'] for r in rows}),
                  'limitation': 'Exact pixel duplicates and training-folder reuse checked; manually exclude related scans, crops, pages and near-duplicates.'}


def equivalent(key, left, right):
    if left is None or right is None: return left is right
    if key == 'amount': return Decimal(left) == Decimal(right)
    if key in ('bank', 'depositor_name'):
        return ' '.join(left.casefold().split()) == ' '.join(right.casefold().split())
    return left == right


def metrics(rows: list[dict], results: list[dict], policy: ReviewPolicy) -> dict:
    if not rows or len(rows) != len(results): raise ValueError('Results must align with nonempty evaluation rows.')
    correct = {key: 0 for key in FIELDS}
    present_correct = {key: 0 for key in FIELDS}
    present_total = {key: 0 for key in FIELDS}
    valid = exact = invented = missing_slots = tp = fp = fn = 0
    for row, result in zip(rows, results):
        if row['id'] != result['id']: raise ValueError('Prediction order or ids differ.')
        fields = result.get('fields')
        valid += fields is not None
        all_match = []
        for key in FIELDS:
            expected = row['fields'][key]
            matched = fields is not None and equivalent(key, fields[key], expected)
            correct[key] += matched
            all_match.append(matched)
            if expected is None:
                missing_slots += 1
                invented += fields is not None and fields[key] is not None
            else:
                present_total[key] += 1
                present_correct[key] += matched
        exact += all(all_match)
        expected_flags = set(scrutiny_flags(row['fields'], row['document_claims'], policy))
        predicted_flags = set(result.get('flag_codes', []))
        tp += len(predicted_flags & expected_flags)
        fp += len(predicted_flags - expected_flags)
        fn += len(expected_flags - predicted_flags)
    count = len(rows)
    return {'examples': count, 'schema_valid_rate': valid / count, 'exact_record_accuracy': exact / count,
            'per_field_accuracy': {key: correct[key] / count for key in FIELDS},
            'visible_field_accuracy': {key: present_correct[key] / present_total[key] if present_total[key] else None for key in FIELDS},
            'invented_values_on_null_labels': invented, 'null_label_slots': missing_slots,
            'document_flag_precision': tp / (tp + fp) if tp + fp else None,
            'document_flag_recall': tp / (tp + fn) if tp + fn else None,
            'mean_seconds': sum(r['seconds'] for r in results) / count,
            'scope': 'synthetic pipeline benchmark only' if all(r['kind'] == 'synthetic' for r in rows) else 'human-labelled holdout; check dataset provenance'}


def evaluate(infer, rows: list[dict], policy: ReviewPolicy, output: Path, label: str) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f'{label}_predictions.jsonl'
    if destination.exists(): raise ValueError('Use a new evaluation run directory; do not overwrite results.')
    results = []
    with destination.open('x') as handle:
        for index, row in enumerate(rows, 1):
            start = time.perf_counter()
            result = {'id': row['id'], 'fields': None, 'flag_codes': [], 'raw': None, 'error': None}
            try:
                with Image.open(row['_path']) as source:
                    image = ImageOps.exif_transpose(source).convert('RGB')
                try: raw = infer(image)
                finally: image.close()
                result['raw'] = raw
                response, details = portal_response(raw, policy)
                result.update(fields=response['fields'], flag_codes=details['flag_codes'])
            except (ValueError, TypeError, KeyError):
                result['error'] = 'invalid_json_or_schema'
            except Exception as exc:
                # Fail the run on hardware/runtime faults rather than misreporting them as model accuracy.
                raise RuntimeError('Evaluation inference failed; previous predictions are retained.') from exc
            result['seconds'] = time.perf_counter() - start
            handle.write(json.dumps(result, ensure_ascii=False) + '\n'); handle.flush()
            results.append(result)
            print(label, index, '/', len(rows), result['error'] or 'valid')
    summary = metrics(rows, results, policy)
    (output / f'{label}_metrics.json').write_text(json.dumps(summary, indent=2))
    return summary


def make_synthetic_holdout(folder: Path, count: int = 24) -> Path:
    """New independent layouts/values; not real-bank performance evidence and never used for training."""
    manifest = folder / 'test.jsonl'
    if folder.exists() and any(folder.iterdir()):
        raise ValueError('Use a new holdout directory; existing images/labels will not be overwritten.')
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'images').mkdir()
    rng = random.Random(9701)
    def font(size):
        for name in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'DejaVuSans.ttf'):
            try: return ImageFont.truetype(name, size)
            except OSError: pass
        return ImageFont.load_default(size=size)
    records = []
    for i in range(count):
        year, month = rng.randint(2018, 2026), i % 12 + 1
        term = (3, 8, 10, 5)[i % 4]
        fields = {'bank': ('Example Learning Bank', 'Fictional Deposit Bank', 'Demo Campus Bank')[i % 3],
                  'number': f'HOLDOUT-{90000+i}-{rng.randrange(1000, 9999)}',
                  'depositor_name': f'Sample Education Trust {i+101}',
                  'amount': f'{rng.randrange(100000, 5000000)}.00',
                  'issue_date': date(year, month, 15).isoformat(),
                  'maturity_date': date(year + term, month, 15).isoformat()}
        joint = (True, False, None)[i % 3]
        lien = (False, True, None)[(i // 3) % 3]
        stamp = i % 2 == 0
        if i % 7 == 0: fields['depositor_name'] = None
        if i % 11 == 0: fields['maturity_date'] = None
        holding = 'Jointly held: Institution Trust and AICTE' if joint else 'Single Holder: Institution Trust Only' if joint is False else None
        lien_text = 'Unconditional lien marked in favour of AICTE' if lien else 'No regulatory lien recorded' if lien is False else None
        entries = [('Issuing bank', fields['bank']), ('FDR number', fields['number']),
                   ('Depositor', fields['depositor_name']), ('Principal amount INR', fields['amount']),
                   ('Issue date (YYYY-MM-DD)', fields['issue_date']), ('Maturity date (YYYY-MM-DD)', fields['maturity_date']),
                   ('Holding pattern', holding), ('Lien statement', lien_text)]
        if i % 3 == 1: entries.reverse()
        if i % 3 == 2: entries = entries[3:] + entries[:3]
        image = Image.new('RGB', (1500, 1700), '#fffdf5' if i % 2 else 'white')
        draw = ImageDraw.Draw(image)
        draw.text((55, 40), 'FICTIONAL EVALUATION RECEIPT — NO FINANCIAL VALIDITY', font=font(32), fill='#852222')
        draw.text((55, 110), 'Fixed deposit: independent holdout example', font=font(38), fill='black')
        y = 220
        for title, value in entries:
            if value is None: continue
            draw.text((60, y), title, font=font(27), fill='#445566')
            draw.text((60, y + 42), value, font=font(34), fill='black')
            y += 135
        if stamp:
            draw.rectangle((60, 1430, 650, 1550), outline='#334477', width=3)
            draw.text((80, 1460), 'SAMPLE BANK STAMP', font=font(30), fill='#334477')
            draw.text((80, 1505), 'Fictional; does not authenticate this document', font=font(21), fill='#334477')
        image_path = f'images/holdout-{i:03d}.png'
        image.save(folder / image_path)
        records.append({'id': f'holdout-{i:03d}', 'group_id': f'new-document-{i:03d}', 'kind': 'synthetic',
                        'image': image_path, 'fields': fields,
                        'document_claims': {'joint_holding': joint, 'lien': lien, 'stamp': stamp}})
    manifest.write_text(''.join(json.dumps(row) + '\n' for row in records))
    return manifest
