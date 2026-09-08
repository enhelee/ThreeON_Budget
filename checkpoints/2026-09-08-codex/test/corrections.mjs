import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url),R=require('../src/reconcile.js'),C=require('../src/constants.js'),P=require('../src/pipeline.js');
const h=['예산과목','예산귀속 부서명(처.지사)','사업명','최종 실적금액'];
const org='용인지사',acct='60909008',acctName='수선유지비-열원정기유지보수';
const p=(biz,value,o=org)=>[acctName,o,biz,value];
const tx=(text,amount,o=org)=>({org:o,acct,acctName,ledger:'손익',text,amount,date:45000,docNos:[]});
const c=(text,target,options={})=>({id:'TEST',org,acct,label:target,targets:[target],texts:[{text}],action:'assign',requireAmount:true,...options});
const fill=(ps,ts,cs=[])=>R.fill([h,...ps],ts,'손익',C,cs);
let count=0;function check(name,fn){fn();count++;}
check('보정으로 같은 금액 복수 후보 구분',()=>{const r=fill([p('사업A',100),p('사업B',100)],[tx('기성',100000)],[c('기성','사업B')]);assert.equal(r.aoa[1][3],0);assert.equal(r.aoa[2][3],100);});
check('다른 지사 보정 불가',()=>{const r=fill([p('사업A',100),p('사업B',100)],[tx('기성',100000)],[c('기성','사업B',{org:'동탄지사'})]);assert.equal(r.matches.length,0);});
check('보정 후보 없음은 금액 자동매칭으로 덮어쓰지 않음',()=>{const r=fill([p('사업A',100)],[tx('기성',100000)],[c('기성','새로 지은 사업')]);assert.equal(r.matches.length,0);assert.equal(r.corrections[0][5],'검토필요');});
check('합계 불일치 보정은 유보',()=>{const r=fill([p('사업A',100),p('사업B',200)],[tx('기성',200000)],[c('기성','사업A')]);assert.equal(r.matches.length,0);});
check('명시적 차이 허용도 원금을 보존',()=>{const r=fill([p('사업A',100)],[tx('기성',100700)],[c('기성','사업A',{requireAmount:false})]);assert.equal(r.aoa[1][3],100.7);assert.equal(r.matches[0][7],0.7);assert.match(r.log[0][6],/확인/);});
check('담당자 제외는 지정 전표만 보존 내역으로 이동',()=>{const r=fill([p('사업A',100)],[tx('착오',100000),tx('다른 전표',200000)],[c('착오','제외',{action:'exclude',targets:[],texts:[{text:'착오',amountThousand:100}]})]);assert.equal(r.exclusions.length,1);assert.equal(r.exclusions[0][4],100);assert.equal(r.stats.unplanned,1);});
check('제외 원금 변경 시 자동 제외 금지',()=>{const r=fill([p('사업A',100)],[tx('착오',200000)],[c('착오','제외',{action:'exclude',targets:[],texts:[{text:'착오',amountThousand:100}]})]);assert.equal(r.exclusions.length,0);assert.equal(r.corrections[0][5],'검토필요');});
check('LTSA 순액과 변동비·제어 Extra Work 분리',()=>{const r=fill([p('공무_가스터빈 LTSA(고정비)',100),p('가스터빈 LTSA 내자 변동비',700)],[tx('GT LTSA 월 비용인식',70000),tx('가스터빈 LTSA 1회 기성(고정비)',70000),tx('GT LTSA 비용역인식',-40000),tx('가스터빈 LTSA 내자변동비',700000)]);assert.equal(r.aoa[1][3],100);assert.equal(r.matches.find(m=>m[10].includes('고정비'))[8],3);});
check('소방 점검용역과 보완공사 혼동 방지',()=>{const r=fill([p('소방 점검용역',100),p('소방 지적사항 보완공사',200)],[{...tx('소방 용역 1분기',70000),date:45000},{...tx('소방 용역 2분기',130000),date:45001}]);assert.equal(r.matches.length,0);});
check('기계·전기 합산에 제어사업 혼입 금지',()=>{const r=fill([p('기계 정기점검',100),p('전기 정기점검',200),p('제어 정기점검',50)],[tx('정기점검 준공',350000)]);assert.equal(r.matches.length,0);});

console.log('보정 합성 테스트: '+count+' 통과');
