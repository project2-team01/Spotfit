"""외부 산출물·원패널·손계산으로 통합 기준을 검증한다. 기존 팀원 파일을 수정하지 않는다."""
import itertools
import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import build
import model

HERE=Path(__file__).resolve().parent


class IntegratedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=pd.read_parquet(HERE/'data/통합_상권업종_2025.parquet')
        cls.meta=json.loads((HERE/'data/integration_meta.json').read_text(encoding='utf-8'))
        cls.before=build.hashes()
        cls.keys=['trdar_code','industry_code']

    def test_input_integrity(self):
        self.assertEqual(self.before,self.meta['input_sha256'])
        self.assertEqual(len(self.d),76591)
        self.assertFalse(self.d.duplicated(self.keys).any())
        self.assertEqual(self.d.trdar_code.nunique(),1644)

    def test_target_and_sales_scope(self):
        t=self.d.loc[self.d.score_status.eq('점수 대상')]
        self.assertEqual(len(t),20522)
        self.assertTrue(t.stores.ge(5).all())
        self.assertEqual(t.industry_code.nunique(),77)
        self.assertTrue(t.industry_peers.ge(30).all())
        self.assertEqual(t.score_sales.notna().sum(),13773)
        self.assertTrue(self.d.loc[self.d.sales_status.eq('미제공 업종'),'score_sales'].isna().all())

    def test_exact_jiyeong_score_oracle(self):
        jy=pd.read_parquet(build.FILES['jiyeong_scores'])
        p=self.d.merge(jy[self.keys+['score_total','score_demand']],on=self.keys,validate='one_to_one')
        t=p.loc[p.score_status.eq('점수 대상')]
        np.testing.assert_allclose(t.score_total_default,t.score_total,atol=1e-9)
        np.testing.assert_allclose(t.score_dem_avg,t.score_demand,atol=1e-9,equal_nan=True)
        self.assertEqual(t.default_delta.abs().gt(1e-8).sum(),126)

    def test_seunghee_type_oracle(self):
        s=pd.read_parquet(build.FILES['seunghee_types'])
        p=self.d.merge(s[self.keys+['type_full','EP','LV','SD']],on=self.keys,suffixes=('','_oracle'),validate='one_to_one')
        diff=p.candidate_type.fillna('?').ne(p.type_full.fillna('?'))
        self.assertEqual(set(zip(p.loc[diff,'trdar_name'],p.loc[diff,'industry_name'])),{('대청초등학교','제과점'),('천호역','PC방')})
        self.assertTrue(p.loc[diff,'candidate_type'].isna().all())
        for a in model.AXES:
            t=p.loc[p.score_status.eq('점수 대상')]
            if a=='EP':t=t.loc[~t.boundary_changed]
            self.assertTrue(t[a].fillna('?').eq(t[a+'_oracle'].fillna('?')).all())
        self.assertEqual(p.candidate_type.notna().sum(),7678)
        self.assertEqual(self.d.boundary_changed.sum(),2)

    def test_official_sd_mapping(self):
        self.assertTrue(self.d.loc[self.d.SD.eq('S').fillna(False),'chg_code'].eq('HH').all())
        self.assertTrue(self.d.loc[self.d.SD.eq('D').fillna(False),'chg_code'].eq('LL').all())
        self.assertTrue(self.d.loc[self.d.chg_code.isin(['LH','HL']),'SD'].isna().all())
        self.assertEqual(self.meta['area_sd'],{'정체':541,'다이나믹':504,'상권축소':349,'상권확장':250})

    def test_lv_boundaries_and_invalid(self):
        r=pd.Series([55,45,56,44,0,-1,np.nan,0],dtype=float)
        w=pd.Series([45,55,44,56,0,2,1,10],dtype=float)
        _,axis=model.lv_axis(r,w)
        self.assertEqual(axis.fillna('?').tolist(),['?','?','L','V','?','?','?','V'])

    def test_ep_boundaries_and_repeated(self):
        d=pd.DataFrame({'score_status':['점수 대상']*100,'sales_quarters':[4]*100,'ticket':range(1,101),'repeated_sales':[False]*100,'industry_code':['A']*100})
        _,axis,peers=model.ep_axis(d)
        self.assertEqual(peers.iloc[0],100)
        self.assertTrue(pd.isna(axis.iloc[44]) and pd.isna(axis.iloc[54]))
        self.assertEqual(axis.iloc[43],'E');self.assertEqual(axis.iloc[55],'P')
        d.loc[:98,'repeated_sales']=True
        self.assertTrue(model.ep_axis(d)[1].isna().all())

    def test_missing_demand_and_zero_weights(self):
        t=self.d.loc[self.d.score_status.eq('점수 대상')]
        self.assertEqual(t.score_dem_avg.isna().sum(),126)
        self.assertEqual(t.score_dem_available.notna().sum(),20522)
        z,n=model.score(t,dict.fromkeys(model.WEIGHTS,0))
        self.assertTrue(z.isna().all());self.assertTrue(n.eq(0).all())
        with self.assertRaises(ValueError):model.score(t,{'sales':-1})

    def test_score_hand_calculation(self):
        for name in ['삼전역 4번','숭례문수입상가(남대문시장)']:
            r=self.d.loc[self.d.trdar_name.eq(name)&self.d.score_status.eq('점수 대상')].iloc[0]
            vals=[r.score_sales,r.score_comp,r.score_stab,r.score_dem_avg]
            weights=[30,25,15,30]
            expected=sum(v*w for v,w in zip(vals,weights) if pd.notna(v))/sum(w for v,w in zip(vals,weights) if pd.notna(v))
            self.assertAlmostEqual(r.score_total_default,expected,10)

    def test_matches_and_empty_results(self):
        d=self.d.loc[self.d.industry_code.eq('CS100010')]
        for letters in itertools.product('LV','EP','SD'):
            choices=dict(zip(model.AXES,letters));r=model.explore(d,choices)
            self.assertTrue(r.candidate_type.eq(''.join(letters)).all())
        no=self.d.loc[self.d.industry_code.eq('CS200022')]
        if len(no):
            self.assertEqual(len(model.explore(no,{'EP':'P'})),0)
        with self.assertRaises(ValueError):model.matches(d,{'SD':'G'})
        self.assertTrue(model.matches(d,{}).all())

    def test_quiz_boundaries_and_revisions(self):
        qs=self.meta['questions'];self.assertEqual(len(qs),15)
        self.assertEqual(len({q['id'] for q in qs}),15)
        self.assertEqual([q['id'] for q in qs if q['revised']],[11,12,13,14,15])
        answers={str(q['id']):q['options'][0]['value'] for q in qs}
        for axis,letters in model.AXES.items():
            subset=[q for q in qs if q['axis']==axis]
            for i,q in enumerate(subset):answers[str(q['id'])]=letters[0] if i<3 else letters[1]
        r=model.quiz_result(qs,answers)
        self.assertEqual(r['code'],'LES');self.assertEqual(r['choices'],dict.fromkeys(model.AXES,''))
        answers['1']='L';answers['2']='L';answers['3']='L';answers['4']='L';answers['5']='V'
        self.assertEqual(model.quiz_result(qs,answers)['choices']['LV'],'L')
        answers.pop('1');self.assertEqual(model.quiz_result(qs,answers)['choices']['LV'],'')
        answers['1']='G'
        with self.assertRaises(ValueError):model.quiz_result(qs,answers)

    def test_quiz_all_answer_patterns(self):
        qs=self.meta['questions']
        # 각 5문항의 32가지 조합을 손으로 센 개수와 비교. 다른 축은 미완료 그대로 둔다.
        for axis,letters in model.AXES.items():
            subset=[q for q in qs if q['axis']==axis]
            for bits in itertools.product([0,1],repeat=5):
                answers={str(q['id']):letters[bit] for q,bit in zip(subset,bits)}
                result=model.quiz_result(qs,answers)
                expected=letters[0] if bits.count(0)>=4 else letters[1] if bits.count(1)>=4 else ''
                self.assertEqual(result['choices'][axis],expected)

    def test_sensitivity_and_metadata_totals(self):
        self.assertEqual(sum(t['count'] for t in self.meta['types']),7678)
        self.assertEqual(self.meta['counts']['held'],12844)
        base=self.meta['sensitivity'][0]
        self.assertAlmostEqual(base['rank_correlation_median'],1)
        self.assertEqual(base['top10_retained_min'],10)
        self.assertEqual(self.before,build.hashes())


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(IntegratedTest)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'version':model.VERSION,'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful(),'input_sha256':build.hashes()}
    (HERE/'report/validation_python.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
