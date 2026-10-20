import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import openpyxl
from utils import operating_analysis_service as data
from utils import operating_query_service as query
from utils import operating_knowledge_service as knowledge
from utils import operating_analysis_ai as ai

class OperatingQueryKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        database=(self.root/'data.sqlite3').resolve().as_posix()
        self.env=patch.dict(os.environ,{'DB_URL':'sqlite+pysqlite:///'+database,
                                        'OPERATING_KNOWLEDGE_DIR':str(self.root/'knowledge'),
                                        'KNOWLEDGE_ROOT':str(self.root/'uploaded')})
        self.env.start();(self.root/'knowledge').mkdir()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def report(self,name,day,sku,product,money,quantity=1):
        wb=openpyxl.Workbook();sh=wb.active
        sh.append(['时间','SKU','SKU名称','货号','三级类目',*data.METRICS.values()])
        sh.append([day,sku,product,'CODE-'+sku,'电脑包',money,quantity,1,1,10,5,1,1,money])
        p=self.root/name;wb.save(p);wb.close();data.import_excel(p)
    def test_product_ranking_returns_actual_name_sku_and_value(self):
        self.report('a.xlsx','2026-01-01','SKU-1','商品甲',10,3)
        self.report('b.xlsx','2026-01-01','SKU-2','商品乙',20,2)
        spec=query.QuerySpec(id='Q1',title='卖得好的商品',start='2026-01-01',end='2026-01-01',metric='revenue',group='sku')
        result,evidence=query.execute(spec)
        self.assertEqual(result['rows'][0]['label'],'SKU-2')
        self.assertEqual(result['rows'][0]['name'],'商品乙')
        self.assertEqual(result['rows'][0]['value'],20)
        self.assertEqual(evidence['ranking'][0]['code'],'CODE-SKU-2')
        quantity,_=query.execute(spec.model_copy(update={'metric':'quantity'}))
        self.assertEqual(quantity['rows'][0]['label'],'SKU-1')
    def test_exact_sku_and_driver_decomposition(self):
        self.report('a.xlsx','2025-12-01','SKU-1','商品甲',10,1)
        self.report('b.xlsx','2026-01-01','SKU-1','商品甲',30,2)
        self.report('c.xlsx','2026-01-01','SKU-10','不应命中',999,1)
        spec=query.QuerySpec(id='Q1',title='商品变化',start='2026-01-01',end='2026-01-01',keyword='SKU-1',match='sku',
                             metric='revenue',group='total',comparisons=['mom'],drivers=True)
        result,_=query.execute(spec)
        self.assertEqual(result['value'],30)
        self.assertEqual(result['object']['name'],'商品甲')
        self.assertEqual(result['object']['sku'],'SKU-1')
        d=result['drivers']['mom']
        self.assertAlmostEqual(d['quantity_contribution']+d['price_contribution'],20)
        self.assertEqual(d['growth_products'][0]['label'],'SKU-1')
        self.assertEqual(d['declining_products'],[])
    def test_month_group_keeps_years_separate_and_derived_metric_is_weighted(self):
        self.report('a.xlsx','2025-07-01','1','甲',100,10)
        self.report('b.xlsx','2026-07-01','1','甲',100,20)
        result,_=query.execute(query.QuerySpec(id='Q1',title='月趋势',start='2025-07-01',end='2026-07-01',metric='unit_price',group='month'))
        self.assertEqual([r['label'] for r in result['rows']],['2025-07','2026-07'])
        self.assertEqual([r['value'] for r in result['rows']],[10,5])
        compared,_=query.execute(query.QuerySpec(id='Q1',title='三期比较',start='2026-07-01',end='2026-07-01',metric='revenue',comparisons=['yoy','yoy2']))
        self.assertEqual(compared['comparisons']['yoy']['selected_value'],100)
        self.assertIsNone(compared['comparisons']['yoy2']['selected_value'])
        self.assertEqual(compared['comparisons']['yoy2']['coverage']['available_days'],0)
        with self.assertRaises(ValueError):
            query.Plan(intent='comparison',normalized_question='比较两个期间的转化率日均',queries=[
                query.QuerySpec(id='Q1',title='甲',start='2025-07-01',end='2025-07-01',metric='conversion'),
                query.QuerySpec(id='Q2',title='乙',start='2026-07-01',end='2026-07-01',metric='conversion')],
                comparisons=[query.ComparisonSpec(left='Q1',right='Q2',title='转化率比较',basis='daily_average')])
    def test_knowledge_versioned_retrieval_and_source_lookup(self):
        path=self.root/'knowledge'/'运营手册.md';path.write_text('# 商品复盘\n成交下滑要比较销量和件均价，并核对活动记录。','utf-8')
        status=knowledge.sync(True);self.assertEqual(len(status['documents']),1)
        hit=knowledge.retrieve('成交金额下滑怎么复盘',1)[0]
        self.assertEqual(hit['title'],'运营手册.md');self.assertIn('销量',hit['text'])
        self.assertEqual(knowledge.read_chunk(hit['id'])['id'],hit['id'])
        old=hit['id'];path.write_text('# 加购复盘\n加购客户下降要查看商品访客和页面变更。','utf-8')
        knowledge.sync(True)
        with self.assertRaises(LookupError):knowledge.read_chunk(old)
        self.assertEqual(knowledge.retrieve('加购客户页面变化',1)[0]['heading'],'加购复盘')
    def test_popular_product_question_is_forced_to_concrete_dual_ranking(self):
        plan=query.Plan(intent='clarification',normalized_question='哪个商品卖得好',clarification='请给日期')
        upgraded=ai._popular_product_override('这个店铺哪个商品是卖得好的 不回答哪个商品',plan,{'dates':['2024-10-01','2026-09-13']})
        self.assertEqual(upgraded.intent,'ranking')
        self.assertEqual([(q.metric,q.group,q.start,q.end) for q in upgraded.queries],
                         [('revenue','sku','2024-10-01','2026-09-13'),('quantity','sku','2024-10-01','2026-09-13')])
        self.assertIn('具体商品名称',upgraded.answer_requirements[0])
        sku_plan=ai._sku_performance_override('100116294817SKU，我想知道全年的访客趋势或者同比数据，比如转化率，成交情况等等',
                                               {'dates':['2024-10-01','2026-09-13']})
        self.assertEqual(sku_plan.normalized_question.split(' 在 ')[0],'SKU 100116294817')
        self.assertEqual((sku_plan.queries[0].start,sku_plan.queries[0].end),('2026-01-01','2026-09-13'))
        self.assertEqual([q.metric for q in sku_plan.queries],['visitors','conversion','revenue','quantity'])
        self.assertTrue(all(q.match=='sku' and q.comparisons==['yoy'] and q.group=='month' for q in sku_plan.queries))
        history=[{'role':'assistant','data_context':{'queries':[{'spec':{'match':'sku','keyword':'100116294817','metric':metric}} for metric in ('visitors','conversion','revenue','quantity')]}}]
        context_plan=ai._context_sku_comparison_override('这个sku今年8月跟去年跟前年对比',{},history,{'dates':['2024-10-01','2026-09-13']})
        self.assertEqual(context_plan.normalized_question,'SKU 100116294817 的 2026 年 8 月与去年同期、前年同期经营指标对比')
        self.assertEqual([q.metric for q in context_plan.queries],['visitors','conversion','revenue','quantity'])
        self.assertTrue(all(q.start=='2026-08-01' and q.end=='2026-08-31' and q.comparisons==['yoy','yoy2'] for q in context_plan.queries))
    def test_answer_validator_rejects_missing_product_and_invented_numbers(self):
        plan=query.Plan(intent='ranking',normalized_question='商品排行',queries=[query.QuerySpec(id='Q1',title='排行',start='2026-01-01',end='2026-01-01',group='sku')])
        facts={'Q1.row1':{'id':'Q1.row1','text':'商品乙，20.00 元'}}
        with self.assertRaises(ValueError):ai._validate_draft(ai.Draft(sections=[ai.Section(title='结论',paragraphs=['请看排行'])]),facts,[],plan)
        with self.assertRaises(ValueError):ai._validate_draft(ai.Draft(sections=[ai.Section(title='结论',paragraphs=['商品销售额为20元 {{Q1.row1}}'])]),facts,[],plan)
        used=ai._validate_draft(ai.Draft(sections=[ai.Section(title='结论',paragraphs=['卖得好的商品是 {{Q1.row1}}'])]),facts,[],plan)
        self.assertEqual(used,['Q1.row1'])
        bounded=ai._bounded_draft({'sections':[{'title':'结论','paragraphs':[],'bullets':['{{Q1.row1}}']*12,'citations':[]}], 'limitations':[]})
        self.assertEqual(len(bounded.sections[0].bullets),8)
        fallback_plan=query.Plan(intent='trend',normalized_question='多指标趋势',queries=[
            query.QuerySpec(id=f'Q{i}',title='趋势',start='2026-01-01',end='2026-01-01',group='month') for i in range(1,5)])
        fallback_results=[{'id':f'Q{i}','spec':{'group':'month'},'rows':[{}],'comparisons':{},'drivers':{}} for i in range(1,5)]
        fallback_facts={f'Q{i}.{suffix}':{'text':'已核对事实'} for i in range(1,5) for suffix in ('scope','peak','low')}
        fallback=ai._fallback_draft(fallback_plan,fallback_results,fallback_facts)
        self.assertTrue(all(len(section.bullets)<=8 for section in fallback.sections))

    def test_planner_timeout_can_continue_a_monthly_decline_followup_locally(self):
        history=[{'role':'assistant','data_context':{'queries':[{'spec':{
            'id':'Q1','title':'2024 年成交金额月度趋势','start':'2024-01-01','end':'2024-12-31',
            'keyword':'','match':'contains','category':'','brand':'','metric':'revenue','group':'month',
            'order':'asc','limit':12,'comparisons':[],'drivers':False}}]}}]
        plan=ai._history_fallback_plan('为什么最后24年12月还下降了',{},history,{'dates':['2024-10-01','2026-09-13']})
        self.assertEqual(plan.intent,'diagnosis')
        self.assertEqual((plan.queries[0].start,plan.queries[0].end),('2024-12-01','2024-12-31'))
        self.assertEqual(plan.queries[0].comparisons,['mom'])
        self.assertTrue(plan.queries[0].drivers)
        self.assertEqual(plan.execution,'deterministic')

if __name__=='__main__':unittest.main()
