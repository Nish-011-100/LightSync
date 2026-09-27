"""Expanding monthly validation within March-September; reused development data."""
import json
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from threadpoolctl import threadpool_limits
from src.modeling import ElevationBaseline,DawnDuskHybrid,metrics,predict_nonnegative
from src.prepare_data import ROOT

def evaluate(root=ROOT):
    data=pd.read_parquet(root/'data/processed/solar_model_input.parquet')
    features=json.loads((root/'config/model_features.json').read_text())['features']
    rows=[];folds=[]
    for month in range(6,10):
        start=pd.Timestamp(year=2024,month=month,day=1,tz='Asia/Kolkata');end=start+pd.offsets.MonthBegin(1)
        train=data[data.timestamp_local<start];val=data[(data.timestamp_local>=start)&(data.timestamp_local<end)]
        assert train.timestamp_local.max()<val.timestamp_local.min()
        folds.append(dict(fold=str(start.date()),train_rows=len(train),validation_rows=len(val),train_end=str(train.timestamp_local.max()),validation_end=str(val.timestamp_local.max())))
        for name,model in [('Elevation baseline',ElevationBaseline()),('Random Forest',RandomForestRegressor(n_estimators=150,max_depth=12,min_samples_leaf=10,n_jobs=2,random_state=42)),('Random Forest + dawn/dusk curves',DawnDuskHybrid())]:
            with threadpool_limits(limits=2):model.fit(train[features],train.solar_radiation_w_m2)
            result=metrics(val,predict_nonnegative(model,val[features]));segments={v['segment']:v for v in result}
            eligible=all(segments[k]['n']>=30 for k in ['dawn','dusk','daytime'])
            score=.4*segments['dawn']['mae_w_m2']+.4*segments['dusk']['mae_w_m2']+.2*segments['daytime']['mae_w_m2'] if eligible else None
            rows.extend(dict(fold=str(start.date()),model=name,eligible=eligible,score=score,**v) for v in result)
    out=root/'reports/modeling';frame=pd.DataFrame(rows);frame.to_csv(out/'rolling_metrics.csv',index=False)
    per=frame[frame.segment.eq('all')&frame.eligible]
    board=per.groupby('model').agg(mean_score=('score','mean'),worst_fold_score=('score','max'),score_std=('score','std'),folds=('fold','nunique')).sort_values('mean_score').reset_index()
    for seg in ['dawn','dusk','daytime']:
        board[seg+'_mae']=board.model.map(frame[frame.segment.eq(seg)&frame.eligible].groupby('model').mae_w_m2.mean())
    board.to_csv(out/'rolling_leaderboard.csv',index=False)
    pd.DataFrame(folds).to_csv(out/'rolling_folds.csv',index=False)
    report=dict(rule='Equal-weight eligible monthly folds; 0.4 dawn MAE + 0.4 dusk MAE + 0.2 daytime MAE. Minimum 30 targets per segment.',months='June-September 2024; expanding training from March',recommended_model=board.iloc[0].model,status='Retrospective development validation; folds overlap previously inspected data. October onward excluded from this selection. No fresh test or field accuracy claim.',deployment='Review recommendation before changing deployed artifact; current artifact remains unchanged by this script.')
    (out/'rolling_evaluation.json').write_text(json.dumps(report,indent=2))
    print(board.to_string(index=False));return board,frame,report
if __name__=='__main__':evaluate()
