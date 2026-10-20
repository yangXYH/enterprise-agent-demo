import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from utils import shop_report_chat_service as s
from utils import shop_report_ai as ai
import shop_report_chat_routes as routes

FILTERS = {'start': '2026-08', 'end': '2026-08', 'metric': 'net_profit', 'group': 'shop'}


def response(filters=None):
    return {'answer': '店铺报表问答结果',
            'report': {'intent': 'ranking', 'understood_as': '8月各店铺项目净利排行', 'sections': [], 'limitations': [],
                       'highlights': [], 'tables': [], 'charts': [], 'knowledge_sources': [], 'audit': {}},
            'evidence': {'filters': filters or FILTERS, 'query_results': []}}


class ShopReportChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database = (Path(self.tmp.name) / 'chat.sqlite3').resolve().as_posix()
        self.env = patch.dict(os.environ, {'DB_URL': 'sqlite+pysqlite:///' + database})
        self.env.start()
        self.session = s.create('alice', FILTERS)['id']

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def complete(self, question='分析测试箱包'):
        turn, _ = s.reserve('alice', self.session, question, 'request-' + str(len(s.read('alice', self.session)['turns'])))
        s.finish('alice', self.session, turn['id'], response())
        return turn

    def test_durable_history_search_and_owner_isolation(self):
        turn = self.complete()
        s.rename('alice', self.session, '八月店铺复盘')
        stored = s.read('alice', self.session)
        self.assertEqual(stored['turns'][0]['response']['evidence']['filters']['metric'], 'net_profit')
        self.assertEqual(s.listing('alice', '测试箱包')[0]['title'], '八月店铺复盘')
        self.assertEqual(s.listing('bob'), [])
        for operation in (lambda: s.read('bob', self.session), lambda: s.rename('bob', self.session, 'bad'),
                          lambda: s.reserve('bob', self.session, 'bad', 'request-bad'),
                          lambda: s.finish('bob', self.session, turn['id'], response())):
            with self.assertRaises(LookupError):
                operation()

    def test_idempotent_request_and_pending_conflict(self):
        a, created = s.reserve('alice', self.session, '8月排行', 'same-request')
        b, second = s.reserve('alice', self.session, '8月排行', 'same-request')
        self.assertTrue(created)
        self.assertFalse(second)
        self.assertEqual(a['id'], b['id'])
        s.update_stage('alice', self.session, a['id'], '正在生成', '已查询到精确结论')
        state = s.progress('alice', self.session, a['id'])
        self.assertEqual((state['status'], state['stage'], state['partial_answer']), ('pending', '正在生成', '已查询到精确结论'))
        with self.assertRaises(RuntimeError):
            s.reserve('alice', self.session, '另一个问题', 'other-request')
        s.finish('alice', self.session, a['id'], response())
        self.assertEqual(len(s.read('alice', self.session)['turns']), 1)

    def test_error_recovery_keeps_questions_and_allows_retry(self):
        good = self.complete()
        s.reserve('alice', self.session, '未完成问题', 'pending-request')
        s.recover_pending()
        turns = s.read('alice', self.session)['turns']
        self.assertEqual(turns[0]['status'], 'completed')
        self.assertEqual(turns[1]['status'], 'error')
        self.assertEqual(turns[1]['question'], '未完成问题')
        retry, _ = s.reserve('alice', self.session, '未完成问题', 'retry-request')
        self.assertEqual([r['id'] for r in retry['context_refs']], [good['id']])

    def test_routes_save_pending_then_complete_and_reject_other_owner(self):
        app = FastAPI()
        app.include_router(routes.router)

        def auth(request, *args):
            if request.headers.get('X-Test-Owner') == 'denied':
                raise HTTPException(403, '无权限')
            return {'id': request.headers.get('X-Test-Owner', 'alice')}

        with patch.object(routes, 'authorize', auth), \
                patch.object(ai, '_write', AsyncMock(return_value=ai.Draft(
                    sections=[ai.Section(title='直接结论', paragraphs=['八月的项目净利排行第一是 {{Q1.row1}}。', '{{Q1.scope}}。'])],
                    limitations=[]))) as writer:
            with TestClient(app) as client:
                url = '/api/shop-report-chat/sessions/' + self.session
                self.assertEqual(client.get(url, headers={'X-Test-Owner': 'bob'}).status_code, 404)
                self.assertEqual(client.get(url, headers={'X-Test-Owner': 'denied'}).status_code, 403)
                body = {'question': '8月各店铺项目净利排行', 'request_id': 'route-request'}
                sent = client.post(url + '/turns', json=body)
                self.assertEqual(sent.status_code, 202)
                self.assertEqual(sent.json()['status'], 'pending')
                self.assertEqual(client.get(url).json()['turns'][0]['status'], 'completed')
                self.assertEqual(client.get(url + '/turns/' + sent.json()['id'] + '/progress').json()['status'], 'completed')
                client.post(url + '/turns', json=body)
                self.assertEqual(writer.await_count, 1)
                self.assertEqual(client.post(url + '/turns', json={**body, 'request_id': 'blank-request', 'question': '  '}).status_code, 422)

    def test_full_analyze_pipeline_with_mocked_writer(self):
        # 规划→执行→事实→写作→校验→渲染 全链路；写作器返回合法草稿
        async def fake_write(question_text, plan, results, facts, prior_errors=None):
            return ai.Draft(
                sections=[ai.Section(title='直接结论', paragraphs=[
                    '八月的项目净利店铺排行中，第一名是 {{Q1.row1}}。',
                    '统计范围：{{Q1.scope}}。']),
                    ai.Section(title='对比', bullets=['环比：{{Q1.row1.mom}}'])],
                limitations=['暂估数据以当前已录费用计算。'])
        fixture = {
            'source': {'year': 2026, 'labor_included': False}, 'months': ['2026-08'],
            'shops': [{'channel': 'self', 'shop_id': 'demo_life', 'shop_name': '示例生活', 'months': ['2026-08']}],
            'fee_keys': ['promo'], 'fee_labels': {'promo': '推广费'},
            'rows': [{'month': '2026-08', 'channel': 'self', 'shop_id': 'demo_life',
                      'revenue': 100, 'costG': 60, 'rentAlloc': 0, 'promo': 50,
                      'has_data': True, 'data_status': 'partial', 'missing_fees': True,
                      'missing_cost': False, 'source_conflict': False, 'profit_provisional': True}],
        }
        with patch.object(ai, '_write', side_effect=fake_write), patch.object(ai.service, 'load', return_value=fixture):
            import asyncio
            result = asyncio.run(ai.analyze('8月哪些店铺亏损了？分析原因'))
        self.assertIn('示例生活', result['answer'])
        self.assertIn('暂估', result['answer'])
        self.assertIn('-10.00', result['answer'])
        self.assertEqual(result['report']['intent'], 'ranking')
        self.assertTrue(result['report']['tables'])
        self.assertEqual(result['report']['audit']['mode'], 'deterministic')

    def test_metadata_available(self):
        from utils import shop_report_service as data_service
        meta = data_service.metadata()
        self.assertIn('shops', meta)
        self.assertTrue(meta['months'])
        self.assertTrue(meta['fee_keys'])

    def test_pending_fee_limitation_describes_estimate_and_prioritizes_missing_cost(self):
        summary = {'fees_partial': True, 'provisional': True}
        text = ai._partial_limitation([{'summary': summary}])
        self.assertIn('按当前已录费用暂估', text)
        self.assertNotIn('暂不计算', text)
        summary['cost_partial'] = True
        self.assertIn('补全 SKU 成本后计算', ai._partial_limitation([{'summary': summary}]))


if __name__ == '__main__':
    unittest.main()
