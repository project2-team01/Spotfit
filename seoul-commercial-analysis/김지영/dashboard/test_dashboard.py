"""자료 부재와 필터 변경에서 집계 의미가 유지되는지 확인한다."""
from pathlib import Path
import unittest
import pandas as pd
import dashboard_data as dd

class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle=dd.load_bundle(Path(__file__).parent)
        cls.fact=cls.bundle['fact']
        cls.industry=cls.fact.loc[cls.fact.industry_name.eq('커피-음료'),'industry_code'].iloc[0]

    def test_default_totals_match_source_slice(self):
        selected,_=dd.filter_scope(self.fact,self.industry,'20254',minimum=5)
        expected=self.fact.query('industry_code == @self.industry and quarter == "20254" and store_count >= 5')
        self.assertEqual(len(selected),len(expected))
        self.assertEqual(dd.metrics(selected)['stores'],expected.store_count.sum())
        self.assertTrue(selected.main_analysis_eligible.all())

    def test_empty_filter_has_no_fake_zero_sales(self):
        selected,history=dd.filter_scope(self.fact,self.industry,'20254',gu='없는 자치구')
        self.assertTrue(selected.empty)
        self.assertTrue(pd.isna(dd.metrics(selected)['sales']))
        self.assertEqual(len(dd.table_data(selected)),0)
        for f in [dd.ranking_chart(selected),dd.trend_chart(history,50),dd.profile_chart(selected),dd.scatter_chart(selected),dd.map_chart(selected,self.bundle['points'])]:
            self.assertGreater(len(f.layout.annotations or []),0)

    def test_unsupported_industry_keeps_stores(self):
        unsupported=self.fact.loc[self.fact.sales_status.eq('unsupported_industry'),'industry_code'].iloc[0]
        selected,history=dd.filter_scope(self.fact,unsupported,'20254',minimum=0)
        self.assertFalse(selected.empty)
        self.assertTrue(selected.sales_amount.isna().all())
        self.assertTrue(pd.isna(dd.metrics(selected)['sales']))
        self.assertGreater(dd.metrics(selected)['stores'],0)
        self.assertTrue(dd.table_data(selected)['분기 매출(억원)'].isna().all())
        self.assertGreater(len(dd.profile_chart(selected).layout.annotations),0)

    def test_gu_type_and_minimum_are_consistent(self):
        for q in ['20251','20252','20253','20254']:
            wide,history=dd.filter_scope(self.fact,self.industry,q,gu='강남구',trdar_type='발달상권',minimum=0)
            narrow,_=dd.filter_scope(self.fact,self.industry,q,gu='강남구',trdar_type='발달상권',minimum=20)
            self.assertTrue(set(narrow.trdar_code)<=set(wide.trdar_code))
            self.assertTrue(narrow.store_count.ge(20).all())
            self.assertTrue(history.gu_name.eq('강남구').all())
            self.assertTrue(history.trdar_type.eq('발달상권').all())

    def test_real_observed_zero_is_not_missing(self):
        sample=self.fact.iloc[[0]].copy()
        sample['sales_amount']=0.;sample['sales_observed']=True;sample['sales_per_store_month']=0.
        self.assertEqual(dd.metrics(sample)['sales'],0)
        self.assertEqual(dd.metrics(sample)['observed'],1)
        sample['sales_amount']=float('nan');sample['sales_observed']=False
        self.assertTrue(pd.isna(dd.metrics(sample)['sales']))

    def test_all_plot_types_serialize(self):
        selected,history=dd.filter_scope(self.fact,self.industry,'20254',minimum=5)
        code=selected.trdar_code.iloc[0]
        for f in [dd.ranking_chart(selected),dd.ranking_chart(selected,'store_count'),dd.trend_chart(history,5),dd.map_chart(selected,self.bundle['points']),dd.selected_trend(history,code),dd.selected_flow(history,code),dd.profile_chart(selected,'time'),dd.profile_chart(selected,'age'),dd.profile_chart(selected,'day'),dd.scatter_chart(selected)]:
            self.assertGreater(len(f.to_json()),100)
        # 수요는 한 상권·분기에 한 행만 연결한다.
        self.assertEqual(len(dd.selected_context(self.bundle,'20254',code)),1)

if __name__=='__main__':unittest.main()
