from pathlib import Path
import hashlib
import io
import json
import zipfile

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
ART = ROOT / 'artifacts'
REPORT = ROOT / 'reports'
SOURCE = 'https://archive.ics.uci.edu/static/public/179/secom.zip'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def download():
    RAW.mkdir(parents=True, exist_ok=True)
    response = requests.get(SOURCE, timeout=120)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        for name in ['secom.data', 'secom_labels.data', 'secom.names']:
            (RAW / name).write_bytes(archive.read(name))
    verify()


def verify():
    expected = json.loads((ROOT / 'data' / 'manifest.json').read_text())
    for name, digest in expected['files'].items():
        if sha(RAW / name) != digest:
            raise ValueError(f'Dataset integrity failure: {name}')


def load():
    if not (RAW / 'secom.data').exists():
        download()
    verify()
    x = pd.read_csv(RAW / 'secom.data', sep=r'\s+', header=None)
    labels = pd.read_csv(RAW / 'secom_labels.data', sep=r'\s+', header=None)
    # The released matrix has 590 signals, despite the catalog saying 591 features.
    if x.shape != (1567, 590) or len(labels) != 1567:
        raise ValueError('Unexpected SECOM release shape')
    if not set(labels[0]).issubset({-1, 1}) or np.isinf(x.to_numpy()).any():
        raise ValueError('Invalid labels or infinite measurements')
    x.columns = [f'sensor_{i:03d}' for i in range(x.shape[1])]
    meta = pd.DataFrame({'entity_id': [f'SECOM-{i:04d}' for i in range(len(x))],
                         'timestamp': pd.to_datetime(labels[1], format='%d/%m/%Y %H:%M:%S'),
                         'failed': (labels[0] == 1).astype(int), 'source_row': range(len(x))})
    order = meta.sort_values(['timestamp', 'source_row'], kind='stable').index
    return x.loc[order].reset_index(drop=True), meta.loc[order].reset_index(drop=True)


def partitions(meta):
    """Contiguous timestamp groups: fitting / calibration / policy / final test."""
    times = meta.timestamp
    edges = [0]
    for fraction in [.50, .65, .80]:
        i = int(len(meta) * fraction)
        while i < len(meta) and times.iloc[i] == times.iloc[i-1]:
            i += 1
        edges.append(i)
    edges.append(len(meta))
    return {name: np.arange(a, b) for name, a, b in
            zip(['train', 'calibration', 'policy', 'test'], edges[:-1], edges[1:])}
