import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from utils import operating_chat_service as s
import operating_chat_routes as routes

FILTERS={'start':'2026-08-01','end':'2026-08-31','brand':'测试旅行','metric':'revenue','group':'sku'}
def response(filters=None):
    return {'answer':'经营数据分析结果','evidence':{'filters':filters or FILTERS,'ranking':[{'label':'SKU-A','value':125.25}]}}

class OperatingChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        database=(Path(self.tmp.name)/'chat.sqlite3').resolve().as_posix()
        self.env=patch.dict(os.environ,{'DB_URL':'sqlite+pysqlite:///'+database})
        self.env.start()
        self.session=s.create('alice',FILTERS)['id']
    def tearDown(self):
        self.env.stop();self.tmp.cleanup()
    def complete(self,question='分析测试旅行',filters=None):
        turn,_=s.reserve('alice',self.session,question,'request-'+str(len(s.read('alice',self.session)['turns'])))
        s.finish('alice',self.session,turn['id'],response(filters))
        return turn
    def test_durable_history_search_and_owner_isolation(self):
        turn=self.complete()
        s.rename('alice',self.session,'八月品牌复盘')
        stored=s.read('alice',self.session)
        self.assertEqual(stored['turns'][0]['response']['evidence']['ranking'][0]['value'],125.25)
        self.assertEqual(s.listing('alice','测试旅行')[0]['title'],'八月品牌复盘')
        self.assertEqual(s.listing('bob'),[])
        for operation in (lambda:s.read('bob',self.session),lambda:s.rename('bob',self.session,'bad'),
                          lambda:s.reserve('bob',self.session,'bad','request-bad'),lambda:s.finish('bob',self.session,turn['id'],response())):
            with self.assertRaises(LookupError):operation()
    def test_idempotent_request_and_pending_conflict(self):
        a,created=s.reserve('alice',self.session,'八月同比','same-request')
        b,second=s.reserve('alice',self.session,'八月同比','same-request')
        self.assertTrue(created);self.assertFalse(second);self.assertEqual(a['id'],b['id'])
        s.update_stage('alice',self.session,a['id'],'正在流式生成','已经查询到精确结论')
        state=s.progress('alice',self.session,a['id'])
        self.assertEqual((state['status'],state['stage'],state['partial_answer']),('pending','正在流式生成','已经查询到精确结论'))
        with self.assertRaises(LookupError):s.progress('bob',self.session,a['id'])
        with self.assertRaises(RuntimeError):s.reserve('alice',self.session,'另一个问题','other-request')
        s.finish('alice',self.session,a['id'],response())
        s.finish('alice',self.session,a['id'],response({'brand':'不应覆盖'}))
        self.assertEqual(s.read('alice',self.session)['filters']['brand'],'测试旅行')
        self.assertEqual(len(s.read('alice',self.session)['turns']),1)
    def test_new_question_has_no_preset_scope_and_followup_uses_actual_answer(self):
        # Even an older empty conversation with saved default filters must not preset a query.
        first,_=s.reserve('alice',self.session,'2025年7月测试旅行成交金额','no-preset-request')
        self.assertEqual(first['filters'],{})
        actual={**FILTERS,'start':'2025-07-01','end':'2025-07-31'}
        s.finish('alice',self.session,first['id'],response(actual))
        next_turn,_=s.reserve('alice',self.session,'上个月呢','follow-context-request')
        self.assertEqual(next_turn['filters'],actual)
    def test_older_explicit_reference_and_latest_filter_carry(self):
        first=self.complete('分析背包',{'**': 'unused',**FILTERS,'brand':'DEMO_BAGS'})
        for i in range(9):self.complete('查询'+str(i))
        turn,_=s.reserve('alice',self.session,'这个品牌上个月呢','followup-request',context_ids=[first['id']])
        indexed,history=s.generation_context('alice',self.session,turn['id'])
        self.assertEqual(indexed['filters']['brand'],'测试旅行')
        self.assertEqual(history[0]['turn_id'],first['id'])
        self.assertTrue(history[0]['explicit_reference'])
        self.assertEqual(history[1]['data_context']['filters']['brand'],'DEMO_BAGS')
        self.assertEqual(history[1]['data_context']['top_products'][0]['label'],'SKU-A')
        self.assertLessEqual(len(history),16)
        self.assertEqual(indexed['context_refs'][0]['filters']['brand'],'DEMO_BAGS')
    def test_invalid_cross_session_reference_and_filters_roll_back(self):
        first=self.complete()
        other=s.create('alice',FILTERS)['id']
        with self.assertRaises(ValueError):s.reserve('alice',other,'引用','other-ref',context_ids=[first['id']])
        with self.assertRaises(ValueError):s.reserve('alice',other,'日期错误','bad-date',filters={'start':'2026-13-01','end':'2026-08-01'})
        self.assertEqual(s.read('alice',other)['turns'],[])
    def test_error_recovery_keeps_questions_and_allows_retry(self):
        good=self.complete()
        bad,_=s.reserve('alice',self.session,'未完成问题','pending-request')
        s.recover_pending()
        turns=s.read('alice',self.session)['turns']
        self.assertEqual(turns[0]['status'],'completed')
        self.assertEqual(turns[1]['status'],'error')
        self.assertEqual(turns[1]['question'],'未完成问题')
        retry,_=s.reserve('alice',self.session,'未完成问题','retry-request')
        self.assertEqual([r['id'] for r in retry['context_refs']],[good['id']])
    def test_routes_save_pending_then_complete_and_reject_other_owner(self):
        app=FastAPI();app.include_router(routes.router)
        def auth(request,*args):
            if request.headers.get('X-Test-Owner')=='denied':raise HTTPException(403,'无权限')
            return {'id':request.headers.get('X-Test-Owner','alice')}
        with patch.object(routes,'authorize',auth),patch.object(routes.operating_analysis_ai,'analyze',AsyncMock(return_value=response())) as model:
            with TestClient(app) as client:
                url='/api/operating-chat/sessions/'+self.session
                self.assertEqual(client.get(url,headers={'X-Test-Owner':'bob'}).status_code,404)
                self.assertEqual(client.get(url,headers={'X-Test-Owner':'denied'}).status_code,403)
                body={'question':'八月同比','request_id':'route-request'}
                sent=client.post(url+'/turns',json=body)
                self.assertEqual(sent.status_code,202);self.assertEqual(sent.json()['status'],'pending')
                self.assertEqual(client.get(url).json()['turns'][0]['status'],'completed')
                self.assertEqual(client.get(url+'/turns/'+sent.json()['id']+'/progress').json()['status'],'completed')
                client.post(url+'/turns',json=body)
                self.assertEqual(model.await_count,1)
                self.assertEqual(client.post(url+'/turns',json={**body,'request_id':'blank-request','question':'  '}).status_code,422)

if __name__=='__main__':unittest.main()
