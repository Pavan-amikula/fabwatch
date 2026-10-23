"""Run the declared chronological experiment and freeze serving artifacts."""
import json
import time
import warnings
import shutil
import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.feature_selection import VarianceThreshold, SelectKBest, f_classif
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier, HistGradientBoostingClassifier, IsolationForest
from sklearn.metrics import (average_precision_score, roc_auc_score, brier_score_loss,
                            confusion_matrix, precision_recall_curve, roc_curve)
from .data import load, partitions, ART, REPORT, ROOT, sha

SEED = 47


def metrics(y, p, threshold):
    tn, fp, fn, tp = confusion_matrix(y, p >= threshold, labels=[0, 1]).ravel()
    return {'ap': float(average_precision_score(y, p)),
            'roc_auc': float(roc_auc_score(y, p)), 'brier': float(brier_score_loss(y, p)),
            'recall': float(tp / max(tp+fn, 1)), 'precision': float(tp/max(tp+fp, 1)),
            'alert_rate': float((tp+fp)/len(y)), 'cost_per_100': float(100*(10*fn+fp)/len(y)),
            'tn': int(tn), 'fp': int(fp), 'fn': int(fn), 'tp': int(tp)}


def calibrate(p, calibrator):
    z = np.log(np.clip(p, 1e-6, 1-1e-6) / np.clip(1-p, 1e-6, 1))
    return calibrator.predict_proba(z.reshape(-1, 1))[:, 1]


def predict(bundle, x):
    p = bundle['pipeline'].predict_proba(x)[:, 1]
    return calibrate(p, bundle['calibrator']) if bundle['calibrator'] is not None else p


def train():
    warnings.filterwarnings('ignore', category=UserWarning, module='sklearn.feature_selection')
    ART.mkdir(exist_ok=True); REPORT.mkdir(exist_ok=True)
    x, meta = load(); splits = partitions(meta); y = meta.failed.to_numpy()
    tr, ca, va, te = [splits[k] for k in ['train', 'calibration', 'policy', 'test']]
    models = {
        'logistic': LogisticRegression(C=.03, class_weight='balanced', max_iter=2000, random_state=SEED),
        'extra_trees': ExtraTreesClassifier(n_estimators=350, max_features=.5, min_samples_leaf=4, class_weight='balanced', n_jobs=2, random_state=SEED),
        'random_forest': RandomForestClassifier(n_estimators=350, max_features=.5, min_samples_leaf=4, class_weight='balanced_subsample', n_jobs=2, random_state=SEED),
        'hist_boost': HistGradientBoostingClassifier(max_iter=140, max_leaf_nodes=7, learning_rate=.04, l2_regularization=5, random_state=SEED)}
    candidates = []; fitted = {}
    for name, model in models.items():
        pipeline = Pipeline([('impute', SimpleImputer(strategy='median', add_indicator=True)),
                             ('variance', VarianceThreshold()), ('select', SelectKBest(f_classif, k=60)),
                             ('scale', StandardScaler()), ('model', model)])
        pipeline.fit(x.iloc[tr], y[tr])
        pc = pipeline.predict_proba(x.iloc[ca])[:, 1]
        pv = pipeline.predict_proba(x.iloc[va])[:, 1]
        z = np.log(np.clip(pc, 1e-6, 1-1e-6)/np.clip(1-pc, 1e-6, 1))
        cal = LogisticRegression(C=1, random_state=SEED).fit(z.reshape(-1, 1), y[ca])
        calibrated = calibrate(pv, cal)
        # Calibration choice uses policy Brier only; ranking uses policy AP.
        use_cal = brier_score_loss(y[va], calibrated) < brier_score_loss(y[va], pv)
        p = calibrated if use_cal else pv
        row = {'name': name, 'policy_ap': float(average_precision_score(y[va], p)),
               'policy_brier': float(brier_score_loss(y[va], p)), 'calibrated': bool(use_cal)}
        candidates.append(row)
        fitted[name] = {'pipeline': pipeline, 'calibrator': cal if use_cal else None}
        print(json.dumps(row), flush=True)
    winner = max(candidates, key=lambda r: (r['policy_ap'], -r['policy_brier']))
    bundle = fitted[winner['name']]; pv = predict(bundle, x.iloc[va])
    thresholds = np.unique(np.r_[0, pv, 1.000001])
    threshold = min(thresholds, key=lambda t: (metrics(y[va], pv, t)['cost_per_100'], metrics(y[va], pv, t)['alert_rate']))
    bundle.update({'threshold': float(threshold), 'name': winner['name'],
                   'columns': list(x.columns), 'train_median': x.iloc[tr].median().fillna(0).to_numpy(),
                   'train_std': x.iloc[tr].std().fillna(0).clip(lower=1e-8).to_numpy(),
                   'missing_limit': float(max(.15, x.iloc[tr].isna().mean(axis=1).quantile(.99)))})
    # Fixed exploratory association ranking from TRAINING data only.
    a = x.iloc[tr]; std = a.std().replace(0, np.nan)
    effect = ((a[y[tr] == 1].mean()-a[y[tr] == 0].mean())/std).abs().fillna(0)
    available = a.notna().mean() >= .70
    bundle['investigation_sensors'] = list(effect[available].nlargest(12).index)
    joblib.dump(bundle, ART / 'model.joblib')
    pt = predict(bundle, x.iloc[te]); test = metrics(y[te], pt, threshold)
    prior = float(y[tr].mean()); baseline_p = np.full(len(te), prior)
    baseline = metrics(y[te], baseline_p, 1.000001)
    transformed = bundle['pipeline'][:-1].transform(x.iloc[tr])
    iso = IsolationForest(n_estimators=150, random_state=SEED, n_jobs=2).fit(transformed[y[tr] == 0])
    iso_score = -iso.score_samples(bundle['pipeline'][:-1].transform(x.iloc[te]))
    # Day block resampling preserves within-day dependency; this is not external validation.
    rng = np.random.default_rng(SEED); days = meta.iloc[te].timestamp.dt.strftime('%Y-%m-%d').to_numpy()
    groups = [np.flatnonzero(days == day) for day in np.unique(days)]
    boot = []
    for _ in range(500):
        ix = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        if len(np.unique(y[te][ix])) == 2:
            m = metrics(y[te][ix], pt[ix], threshold)
            m['cost_saving_vs_pass'] = metrics(y[te][ix], baseline_p[ix], 1.000001)['cost_per_100']-m['cost_per_100']
            boot.append(m)
    ci = {k: [float(v) for v in np.quantile([b[k] for b in boot], [.025, .975])]
          for k in ['ap', 'recall', 'precision', 'cost_per_100', 'cost_saving_vs_pass']}
    times = []
    predict(bundle, x.iloc[te[:1]])
    for i in te[:100]:
        start = time.perf_counter(); predict(bundle, x.iloc[[i]]); times.append((time.perf_counter()-start)*1000)
    split_report = {k: {'n': len(ix), 'fails': int(y[ix].sum()),
                        'start': str(meta.iloc[ix].timestamp.min()), 'end': str(meta.iloc[ix].timestamp.max())}
                    for k, ix in splits.items()}
    result = {'dataset': {'rows': len(x), 'sensors': x.shape[1], 'fails': int(y.sum()),
                          'missing_fraction': float(x.isna().to_numpy().mean()), 'constant_train_sensors': int((x.iloc[tr].nunique() <= 1).sum())},
              'splits': split_report, 'candidates': candidates, 'winner': winner,
              'threshold': float(threshold), 'test': test, 'all_pass': baseline,
              'isolation_forest_test_ap': float(average_precision_score(y[te], iso_score)),
              'bootstrap_95_ci': ci, 'bootstrap_valid': len(boot),
              'cost_assumption': {'missed_failure': 10, 'false_alert': 1, 'currency': 'hypothetical units'},
              'latency_ms': {'p50': float(np.median(times)), 'p95': float(np.quantile(times, .95)), 'n': len(times),
                             'scope': 'warm single-row pandas + sklearn pipeline; excludes HTTP, SQL and explanation'},
              'model_sha256': sha(ART / 'model.joblib'), 'seed': SEED}
    (REPORT / 'metrics.json').write_text(json.dumps(result, indent=2))
    records = meta.copy(); records['split'] = ''
    for k, ix in splits.items(): records.loc[ix, 'split'] = k
    records.to_csv(REPORT / 'split_manifest.csv', index=False)
    pd.DataFrame({'entity_id': meta.iloc[te].entity_id, 'timestamp': meta.iloc[te].timestamp,
                  'actual_failure': y[te], 'risk': pt, 'alert': pt >= threshold}).to_csv(REPORT / 'test_predictions.csv', index=False)
    pd.DataFrame({'sensor': x.columns, 'missing_fraction': x.isna().mean(),
                  'training_missing_fraction': a.isna().mean(), 'training_distinct': a.nunique(),
                  'training_effect_abs': effect}).to_csv(REPORT / 'sensor_quality.csv', index=False)
    plt.rcParams.update({'axes.spines.top': False, 'axes.spines.right': False, 'font.size': 10})
    fig, ax = plt.subplots(1, 3, figsize=(14, 4), layout='constrained')
    precision, recall, _ = precision_recall_curve(y[te], pt)
    ax[0].plot(recall, precision, color='#946322', label=f"Model AP {test['ap']:.3f}")
    ax[0].axhline(y[te].mean(), color='#777', linestyle='--', label='Test prevalence')
    ax[0].set(xlabel='Recall', ylabel='Precision', title='Chronological test · PR curve'); ax[0].legend()
    fpr, tpr, _ = roc_curve(y[te], pt); ax[1].plot(fpr, tpr, color='#253f39'); ax[1].plot([0,1],[0,1], '--', color='#aaa')
    ax[1].set(xlabel='False positive rate', ylabel='True positive rate', title=f"ROC AUC {test['roc_auc']:.3f}")
    matrix = np.array([[test['tn'],test['fp']],[test['fn'],test['tp']]])
    ax[2].imshow(matrix, cmap='YlOrBr')
    for (i,j), value in np.ndenumerate(matrix): ax[2].text(j,i,str(value),ha='center',va='center')
    ax[2].set(xticks=[0,1],xticklabels=['Pass','Alert'],yticks=[0,1],yticklabels=['Pass','Fail'],title='Frozen operating point',xlabel='Decision',ylabel='Actual')
    fig.savefig(REPORT / 'evaluation.png', dpi=160); plt.close(fig)
    shutil.copyfile(REPORT / 'evaluation.png', ROOT / 'web' / 'evaluation.png')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__': train()
