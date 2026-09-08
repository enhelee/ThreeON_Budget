import copy
import json
from pathlib import Path
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
import checkpoint_actuals as ca

ACCOUNT = '수선유지비-열원정기점검'

def payload():
    return {'schemaVersion':1, 'amountUnit':'KRW_THOUSAND', 'amountMatching':True, 'sourceYears':[2025],
        'sourceTotals':[{'ledger':'손익','org':'동탄지사','account':ACCOUNT,'amountWon':400000},
                        {'ledger':'손익','org':'파주지사','account':ACCOUNT,'amountWon':200000}],
        'reconciliation':{
            'groups':[['묶음ID','원장','지사','예산과목','처리방법','전표 합계(천원)','사업 실적 합계(천원)','단수차이(천원)','전표항목수','사업수','대상 사업명','전표텍스트','참조전표번호'],
                      ['G1','손익','동탄지사',ACCOUNT,'확인',300.002,300,0.002,1,2,'공통 / 제어','합성',''],
                      ['G2','손익','파주지사',ACCOUNT,'확인',200,200,0,1,1,'공통','합성','']],
            'details':[['묶음ID','원장','지사','예산과목','집계표 원본행','사업명','기준 실적(천원)','반영 실적(천원)'],
                       ['G1','손익','동탄지사',ACCOUNT,1,'공통',100,100],
                       ['G1','손익','동탄지사',ACCOUNT,2,'제어',200,200.002],
                       ['G2','손익','파주지사',ACCOUNT,1,'공통',200,200]],
            'exclusions':[['원장','지사','예산과목','전표텍스트','제외 금액(천원)','담당자 제외 사유','보정ID','참조전표번호']]}}

def encode(data=None):
    return json.dumps(payload() if data is None else data)

@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path

def test_split_keeps_won_and_same_named_sites_separate():
    _, actuals, summary = ca.prepare_result(encode(),2025)
    assert actuals.groupby('사업장')['금액'].sum().to_dict() == {'동탄지사':300002,'파주지사':200000}
    assert len(actuals)==3
    assert summary['미배정순액(원)'].sum()==99998

@pytest.mark.parametrize('mutation', ['scope','duplicate','amount','missing_group','unit','year','multi_year','nan','source'])
def test_invalid_data_rejected(mutation):
    data=payload()
    if mutation=='scope': data['reconciliation']['details'][1][2]='타지사'
    if mutation=='duplicate': data['reconciliation']['details'].append(copy.deepcopy(data['reconciliation']['details'][1]))
    if mutation=='amount': data['reconciliation']['details'][1][-1]=99
    if mutation=='missing_group': data['reconciliation']['groups'].pop()
    if mutation=='unit': data['amountUnit']='KRW'
    if mutation=='year': data['sourceYears']=[2024]
    if mutation=='multi_year': data['sourceYears']=[2024,2025]
    if mutation=='nan': data['reconciliation']['details'][1][-1]=float('nan')
    if mutation=='source': del data['sourceTotals']
    with pytest.raises(ValueError): ca.prepare_result(encode(data),2025)

def test_reimport_idempotent_and_older_versions_preserved(isolated):
    Path('classified_2025.csv').write_text('existing data')
    ca.save_result(encode(),2025); ca.save_result(encode(),2025)
    actuals,_=ca.load_saved()
    assert actuals['금액'].sum()==500002
    assert len(list(ca.STORE.glob('2025-*.json')))==1
    changed=payload(); changed['sourceTotals'][0]['amountWon']=450000
    ca.save_result(encode(changed),2025)
    assert len(list(ca.STORE.glob('2025-*.json')))==2
    assert len(ca.load_saved()[0])==3
    assert Path('classified_2025.csv').read_text()=='existing data'

def test_saved_data_integrity(isolated):
    ca.save_result(encode(),2025)
    path=next(ca.STORE.glob('2025-*.json'))
    data=json.loads(path.read_text(encoding='utf-8')); data['result']['sourceTotals'][0]['amountWon']=123
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError): ca.load_saved()

def test_new_menu_renders(isolated):
    app=Path(__file__).resolve().parents[1]/'app.py'
    at=AppTest.from_file(str(app),default_timeout=30).run()
    at.sidebar.radio[0].set_value('예산 실적 집계').run()
    at.sidebar.radio[1].set_value('사업 실적 연결').run()
    assert not at.exception
    assert any(s.value=='사업 실적 연결' for s in at.subheader)

def _standardization():
    from views.standardization_page import render
    render()

def _forecast():
    from views.longterm_forecast_page import render
    render()

def test_both_production_pages_receive_matching_data(isolated,monkeypatch):
    import views.standardization_page as sp
    import views.longterm_forecast_page as fp
    ca.save_result(encode(),2025)
    seen=[]
    def capture(actuals,*args,**kwargs):
        seen.append(actuals.copy())
    monkeypatch.setattr(sp,'_render_standardization',capture)
    monkeypatch.setattr(fp,'_render_compute_and_export',capture)
    for name in ['_render_schedule_manager','_render_hot_parts_manager','_render_factor_manager','_render_hq_temp_projects','_render_surprise_projects']:
        monkeypatch.setattr(fp,name,lambda:pd.DataFrame())
    monkeypatch.setattr(fp,'_render_hq_master_manager',lambda:(pd.DataFrame(),pd.DataFrame()))
    for fn in [_standardization,_forecast]:
        at=AppTest.from_function(fn,default_timeout=30).run()
        assert not at.exception
    assert len(seen)==2
    for frame in seen:
        assert frame['금액'].sum()==500002
        assert set(frame['사업장'])=={'동탄지사','파주지사'}
        assert set(frame['연도'])=={2025}

def test_connected_actuals_feed_real_standardization(isolated):
    import standardization as std
    ca.save_result(encode(),2025)
    actuals,_=ca.load_saved()
    grades=pd.DataFrame({'사업장':['동탄지사','파주지사'],'연도':[2025,2025],'등급':['MI','MI']})
    methods=pd.DataFrame({'사업장':['동탄지사','파주지사'],'예산과목':[ACCOUNT,ACCOUNT],'방식':['최근실적','최근실적']})
    result=std.compute_standard_amounts(actuals,grades,methods)
    values=result.set_index('사업장')['표준금액'].to_dict()
    assert values['동탄지사']==300002 and values['파주지사']==200000
