"""Development-only challenger selection; reused test is explicitly exploratory.

The original model is never overwritten or promoted by this script.
"""
import json
import warnings
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.feature_selection import VarianceThreshold, SelectKBest, f_classif
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score, confusion_matrix
from fabwatch.data import load, partitions, REPORT


def main():
    warnings.filterwarnings('ignore',category=UserWarning,module='sklearn.feature_selection')
    x,m=load();s=partitions(m);tr=s['train'];va=s['policy'];te=s['test'];y=m.failed.to_numpy()
    candidates={
        'svm_rbf_20':(20,SVC(C=1,gamma='scale',class_weight='balanced')),
        'svm_rbf_60':(60,SVC(C=1,gamma='scale',class_weight='balanced')),
        'svm_rbf_all':('all',SVC(C=1,gamma='scale',class_weight='balanced')),
        'extra_trees_all':('all',ExtraTreesClassifier(n_estimators=500,min_samples_leaf=3,class_weight='balanced',n_jobs=2,random_state=47)),
        'random_forest_all':('all',RandomForestClassifier(n_estimators=500,min_samples_leaf=3,class_weight='balanced_subsample',n_jobs=2,random_state=47)),
        'logistic_10':(10,LogisticRegression(C=.03,class_weight='balanced',max_iter=3000,random_state=47)),
        'logistic_all':('all',LogisticRegression(C=.01,class_weight='balanced',max_iter=3000,random_state=47)),
    }
    pipelines={};rows=[]
    def score(pipeline,frame):
        return pipeline.decision_function(frame) if hasattr(pipeline,'decision_function') else pipeline.predict_proba(frame)[:,1]
    for name,(k,model) in candidates.items():
        pipeline=Pipeline([('impute',SimpleImputer(strategy='median',add_indicator=True)),('variance',VarianceThreshold()),
                           ('select',SelectKBest(f_classif,k=k)),('scale',StandardScaler()),('model',model)])
        pipeline.fit(x.iloc[tr],y[tr]);p=score(pipeline,x.iloc[va]);ap=float(average_precision_score(y[va],p))
        pipelines[name]=pipeline;row={'name':name,'policy_ap':ap};rows.append(row);print(json.dumps(row),flush=True)
    winner=max(rows,key=lambda r:r['policy_ap']);pipeline=pipelines[winner['name']]
    pv=score(pipeline,x.iloc[va]);pt=score(pipeline,x.iloc[te])
    # Cost rule remains 10:1. Ranking scores need no probability calibration.
    thresholds=np.unique(np.r_[pv.min()-1,pv,pv.max()+1])
    def cost(t):
        pred=pv>=t
        return (int(((y[va]==1)&~pred).sum())*10+int(((y[va]==0)&pred).sum()),int(pred.sum()))
    threshold=float(min(thresholds,key=cost));tn,fp,fn,tp=confusion_matrix(y[te],pt>=threshold,labels=[0,1]).ravel()
    result={'status':'Exploratory challenger; final test previously inspected; no promotion',
            'protocol':'7 declared additional candidates fitted on original training only; selection and threshold on original policy only',
            'candidates':rows,'selected':winner,'threshold':threshold,
            'reused_test':{'ap':float(average_precision_score(y[te],pt)),'roc_auc':float(roc_auc_score(y[te],pt)),
                           'tn':int(tn),'fp':int(fp),'fn':int(fn),'tp':int(tp),'recall':float(tp/max(tp+fn,1)),
                           'precision':float(tp/max(tp+fp,1)),'cost_per_100':float(100*(10*fn+fp)/len(te))},
            'interpretation':'New future/site validation required; original frozen serving model remains unchanged.'}
    (REPORT/'challenger_study.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
