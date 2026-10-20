"""Bounded, parameterized business-query tools, calculated facts and contribution evidence."""
from itertools import combinations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
from utils import operating_analysis_service as data

DERIVED={'conversion':('商品记录合计转化率','customers','visitors'),
         'unit_price':('成交件均价','revenue','quantity'),
         'cart_rate':('记录加购客户访客比','cart_customers','visitors'),
         'customer_value':('商品记录客户均成交金额','revenue','customers'),
         'order_value':('订单记录均成交金额','revenue','orders')}
METRICS={**data.METRICS,**{k:v[0] for k,v in DERIVED.items()}}
Metric=Literal['revenue','quantity','orders','customers','views','visitors','cart_quantity','cart_customers','cart_amount',
               'conversion','unit_price','cart_rate','customer_value','order_value']

class QuerySpec(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str=Field(pattern=r'^Q[1-6]$')
    title:str=Field(min_length=1,max_length=140)
    start:str
    end:str
    keyword:str=Field('',max_length=250)
    match:Literal['contains','sku','code']='contains'
    category:str=Field('',max_length=250)
    brand:str=Field('',max_length=250)
    metric:Metric='revenue'
    group:Literal['total','sku','category','brand','day','month']='total'
    order:Literal['desc','asc']='desc'
    limit:int=Field(10,ge=1,le=50)
    comparisons:list[Literal['yoy','yoy2','mom']]=Field(default_factory=list,max_length=3)
    drivers:bool=False
    @model_validator(mode='after')
    def dates(self):data.validate_range(self.start,self.end);return self

class ComparisonSpec(BaseModel):
    model_config=ConfigDict(extra='forbid')
    left:str
    right:str
    title:str=Field(max_length=140)
    basis:Literal['total','daily_average']='total'

class Plan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    intent:Literal['lookup','ranking','trend','comparison','diagnosis','knowledge','mixed','coverage','clarification']
    normalized_question:str=Field(min_length=1,max_length=2400)
    answer_requirements:list[str]=Field(default_factory=list,max_length=10)
    queries:list[QuerySpec]=Field(default_factory=list,max_length=6)
    comparisons:list[ComparisonSpec]=Field(default_factory=list,max_length=6)
    knowledge_ids:list[str]=Field(default_factory=list,max_length=8)
    clarification:str=Field('',max_length=800)
    execution:Literal['model_assisted','deterministic']='model_assisted'
    @model_validator(mode='after')
    def references(self):
        ids=[q.id for q in self.queries]
        if len(ids)!=len(set(ids)):raise ValueError('查询ID不可重复')
        for p in self.comparisons:
            if p.left not in ids or p.right not in ids:raise ValueError('比较引用未知查询ID')
            a,b=[next(q for q in self.queries if q.id==i) for i in (p.left,p.right)]
            if a.metric!=b.metric:raise ValueError('比较必须使用相同指标')
            if p.basis=='daily_average' and a.metric in DERIVED:
                raise ValueError('比率和均值指标不能再次按天平均')
        if self.intent not in ('knowledge','coverage','clarification') and not self.queries:raise ValueError('此问题需要数据库查询')
        if self.intent=='clarification' and not self.clarification:raise ValueError('追问内容不能为空')
        return self

def value(summary,metric):
    if metric not in DERIVED:return summary.get(metric)
    _,numerator,denominator=DERIVED[metric]
    return summary[numerator]/summary[denominator] if summary.get(denominator) else None

def unit(metric):
    if metric in ('conversion','cart_rate'):return '%'
    if metric in ('revenue','cart_amount','unit_price','customer_value','order_value'):return '元'
    if metric in ('quantity','cart_quantity'):return '件'
    if metric=='orders':return '单（商品记录合计）'
    if metric in ('customers','visitors','cart_customers'):return '人次（商品记录合计）'
    return '次'

def formatted(v,metric):
    if v is None:return '不可计算（分母为零或无完整数据）'
    if metric in ('conversion','cart_rate'):return f'{v*100:,.2f}%'
    return f'{v:,.2f} {unit(metric)}'

def formatted_delta(v,metric):
    if v is None:return '不可计算'
    if metric in ('conversion','cart_rate'):return f'{v*100:+,.2f} 个百分点'
    return ('+' if v>0 else '')+formatted(v,metric)

def query_where(q,start=None,end=None):
    sql,args=data.where(start or q.start,end or q.end,q.keyword if q.match=='contains' else '',q.category,q.brand)
    if q.keyword and q.match!='contains':sql+=' AND '+q.match+'=?';args.append(q.keyword)
    return sql,args

def grouped(c,q,start=None,end=None):
    sql,args=query_where(q,start,end)
    if q.group=='total':return []
    expression={'sku':'sku','category':'category','brand':"COALESCE((SELECT brand FROM jy_operating_brands b WHERE b.name=jy_records.name),'待识别')",
                'day':'day','month':'substr(day,1,7)'}[q.group]
    # Group expressions and metric names come only from validated enums.
    raw=c.execute('SELECT '+expression+' label,MAX(name) name,MAX(code) code,COUNT(DISTINCT sku) sku_count,'+
                  ','.join(f'SUM({m}) {m}' for m in data.METRICS)+' FROM jy_records WHERE '+sql+' GROUP BY '+expression,args)
    result=[]
    for r in raw:
        row=dict(r)
        for m in data.METRICS:row[m]=data.money_value(row[m]) if m in ('revenue','cart_amount') else row[m] or 0
        row['value']=value(row,q.metric);result.append(row)
    if q.group in ('day','month'):result.sort(key=lambda r:r['label'])
    else:result.sort(key=lambda r:(r['value'] is None,-(r['value'] or 0) if q.order=='desc' else (r['value'] or 0),r['label']))
    return result

def execute(q):
    sql,args=query_where(q)
    from datetime import date
    with data.connect() as c:
        summary=data.totals(c,sql,args);cov=data.coverage(c,q.start,q.end);comparisons={}
        for key in q.comparisons:
            n={'yoy':-12,'yoy2':-24,'mom':-1}[key]
            start=data.shift_month(date.fromisoformat(q.start),n).isoformat();end=data.shift_month(date.fromisoformat(q.end),n).isoformat()
            cs,ca=query_where(q,start,end);cc=data.coverage(c,start,end);t=data.totals(c,cs,ca)
            # Complete natural periods remain comparable even when their calendar day counts differ
            # (for example November versus December). Coverage still exposes both day counts.
            comparable=cov['complete'] and cc['complete']
            comparisons[key]={'coverage':cc,'summary':t,'rates':{k:(summary[k]-t[k])/abs(t[k]) if comparable and t[k] else None for k in data.METRICS}}
        rows=grouped(c,q)
        sources=[dict(r) for r in c.execute('SELECT filename,COUNT(*) AS `rows`,MIN(source_row) first_row,MAX(source_row) last_row FROM jy_records WHERE '+sql+' GROUP BY filename',args)]
        identity=dict(c.execute('SELECT MAX(name) name,MAX(code) code,MAX(sku) sku FROM jy_records WHERE '+sql,args).fetchone()) if q.match in ('sku','code') else None
    e={'summary':summary,'coverage':cov,'comparisons':comparisons,'filters':q.model_dump(),
       'ranking':[],'trend':[],'sources':sources,'category_distribution':[],'note':data.NOTE,'total':summary['row_count']}
    total=value(e['summary'],q.metric)
    for row in rows:
        row['share']=row['value']/total if total and q.metric not in DERIVED else None
    selected=rows if q.group in ('day','month') else rows[:q.limit]
    for comp in e['comparisons'].values():
        previous=value(comp['summary'],q.metric) if comp['coverage']['available_days'] else None
        comparable=e['coverage']['complete'] and comp['coverage']['complete']
        comp['selected_value']=previous
        comp['selected_rate']=(total-previous)/abs(previous) if comparable and total is not None and previous else None
        comp['selected_delta']=total-previous if comparable and total is not None and previous is not None else None
    result={'id':q.id,'title':q.title,'spec':q.model_dump(),'summary':e['summary'],'coverage':e['coverage'],
            'value':total,'metric_label':METRICS[q.metric],'unit':unit(q.metric),'rows':selected,
            'group_count':len(rows),'comparisons':{k:v for k,v in e['comparisons'].items() if k in q.comparisons},'sources':e['sources'],'object':identity}
    e['ranking']=selected if q.group not in ('total','day','month') else []
    if q.drivers and q.metric in data.METRICS:
        result['drivers']=drivers(q,e)
    return result,e

def drivers(q,e):
    output={}
    for key in q.comparisons:
        comp=e['comparisons'][key]
        if comp['selected_delta'] is None:continue
        current,previous=e['summary'],comp['summary']
        details={'period':comp['coverage'],'metric_label':METRICS[q.metric]}
        if q.metric=='revenue' and current['quantity']>0 and previous['quantity']>0:
            p1=current['revenue']/current['quantity'];p0=previous['revenue']/previous['quantity']
            details['quantity_contribution']=(current['quantity']-previous['quantity'])*(p1+p0)/2
            details['price_contribution']=(p1-p0)*(current['quantity']+previous['quantity'])/2
            details['note']='销量与件均价的对称算术分解，合计等于成交金额变化；不证明因果。'
        cq=q.model_copy(update={'group':'sku','metric':q.metric})
        with data.connect() as c:
            a={r['label']:r for r in grouped(c,cq)}
            b={r['label']:r for r in grouped(c,cq,comp['coverage']['start'],comp['coverage']['end'])}
        changes=[]
        for sku in a.keys()|b.keys():
            present=a.get(sku);old=b.get(sku);row=present or old
            av=present['value'] if present else 0;bv=old['value'] if old else 0
            if av is None or bv is None:continue
            changes.append({'label':sku,'name':row['name'],'code':row['code'],'current':av,'previous':bv,'delta':av-bv,
                            'presence':'两期都有' if present and old else '本期有记录，基期无记录' if present else '基期有记录，本期无记录'})
        changes.sort(key=lambda r:(r['delta'],r['label']),reverse=True)
        details['growth_products']=[r for r in changes if r['delta']>0][:5]
        details['declining_products']=sorted((r for r in changes if r['delta']<0),key=lambda r:(r['delta'],r['label']))[:5]
        output[key]=details
    return output

def facts_for(results,plan,meta):
    facts={};tables=[]
    def add(identifier,label,text):facts[identifier]={'id':identifier,'label':label,'text':text}
    add('DATA.scope','全部数据范围',f"{meta['dates'][0]} 至 {meta['dates'][-1]}，共 {len(meta['dates'])} 个有数据日期，{len(meta['batches'])} 个来源月报")
    for r in results:
        q=r['spec'];qid=r['id'];metric=q['metric'];cv=r['coverage']
        add(qid+'.scope',r['title']+'统计范围',f"{q['start']} 至 {q['end']}，{q['brand'] or '全部品牌'}，{q['category'] or '全部类目'}，商品关键词 {q['keyword'] or '不限'}，有数据 {cv['available_days']}/{cv['expected_days']} 天")
        add(qid+'.value',r['title']+'汇总'+r['metric_label'],formatted(r['value'],metric))
        add(qid+'.sku_count','参与统计SKU数',f"{r['summary']['sku_count']:,} 个 SKU")
        if q.get('match') in ('sku','code') and r.get('object') and r['object'].get('name'):
            obj=r['object']
            add(qid+'.object','精确查询商品',f"{obj['name']}（SKU {obj.get('sku') or (q['keyword'] if q['match']=='sku' else '未指定')}，货号 {obj.get('code') or (q['keyword'] if q['match']=='code' else '未填')}）")
        # The planner creates one query per requested metric. Keeping only the selected metric
        # in the writer's fact registry improves relevance and bounds model context.
        add(qid+'.'+metric,METRICS[metric]+'（'+r['title']+'）',formatted(value(r['summary'],metric),metric))
        for key,comp in r['comparisons'].items():
            name={'yoy':'去年同期','yoy2':'前年同期','mom':'上月同期'}[key]
            add(qid+'.'+key+'.period',name+'范围',f"{comp['coverage']['start']} 至 {comp['coverage']['end']}，有数据 {comp['coverage']['available_days']}/{comp['coverage']['expected_days']} 天")
            add(qid+'.'+key+'.value',name+r['metric_label'],'无数据' if not comp['coverage']['available_days'] else formatted(comp['selected_value'],metric))
            rate=comp['selected_rate'];delta=comp['selected_delta']
            add(qid+'.'+key+'.rate',name+'变化率',f'{rate*100:+.2f}%' if rate is not None else '不可完整比较（缺少日期、天数不等或基数为零）')
            add(qid+'.'+key+'.delta',name+'变化量',formatted_delta(delta,metric) if delta is not None else '不可完整比较')
        if r['rows']:
            rows=[]
            valid=[(i,row) for i,row in enumerate(r['rows']) if row['value'] is not None]
            detailed_indices=set(range(len(r['rows'])))
            if q['group'] in ('day','month') and len(r['rows'])>60:
                detailed_indices=set(range(6))|set(range(len(r['rows'])-6,len(r['rows'])))
                detailed_indices.update(range(0,len(r['rows']),max(1,len(r['rows'])//30)))
                if valid:detailed_indices.update([max(valid,key=lambda x:x[1]['value'])[0],min(valid,key=lambda x:x[1]['value'])[0]])
            for i,row in enumerate(r['rows']):
                display=f"{row['name']}（SKU {row['label']}，货号 {row['code'] or '未填'}）" if q['group']=='sku' else row['label'] or '未分类'
                fid=f'{qid}.row{i+1}'
                if i in detailed_indices:add(fid,('排行' if q['group'] not in ('day','month') else '趋势记录')+str(i+1),f"{display}，{r['metric_label']} {formatted(row['value'],metric)}"+
                    (f"，占本期指标净值 {row['share']*100:.2f}%" if row['share'] is not None else ''))
                rows.append({'object':display,'value':formatted(row['value'],metric),'fact_id':fid})
            tables.append({'title':r['title'],'query_id':qid,'columns':[{'key':'object','label':{'sku':'商品','category':'类目','brand':'品牌','day':'日期','month':'年月'}.get(q['group'],'对象')},
                           {'key':'value','label':r['metric_label']}],'rows':rows})
            valid=[(i,row) for i,row in enumerate(r['rows']) if row['value'] is not None]
            if q['group'] in ('day','month') and valid:
                hi=max(valid,key=lambda x:x[1]['value']);lo=min(valid,key=lambda x:x[1]['value'])
                add(qid+'.peak','区间峰值',facts[f'{qid}.row{hi[0]+1}']['text'])
                add(qid+'.low','区间低值',facts[f'{qid}.row{lo[0]+1}']['text'])
        for key,d in r.get('drivers',{}).items():
            if 'quantity_contribution' in d:
                add(qid+'.'+key+'.quantity_contribution','销量变动的算术贡献',formatted(d['quantity_contribution'],'revenue'))
                add(qid+'.'+key+'.price_contribution','件均价变动的算术贡献',formatted(d['price_contribution'],'revenue'))
            for direction in ('growth_products','declining_products'):
                rr=[]
                for i,row in enumerate(d[direction]):
                    fid=f'{qid}.{key}.{direction}.{i+1}'
                    obj=f"{row['name']}（SKU {row['label']}，货号 {row['code'] or '未填'}）"
                    add(fid,'商品变化贡献',f"{obj}，本期 {formatted(row['current'],metric)}，基期 {formatted(row['previous'],metric)}，差额 {formatted_delta(row['delta'],metric)}；{row['presence']}")
                    rr.append({'object':obj,'current':formatted(row['current'],metric),'previous':formatted(row['previous'],metric),'delta':formatted_delta(row['delta'],metric)})
                if rr:
                    tables.append({'title':({'yoy':'同比','yoy2':'前年同比','mom':'环比'}[key])+('增长贡献' if direction=='growth_products' else '下降贡献'),'query_id':r['id'],
                                  'columns':[{'key':'object','label':'商品'},{'key':'current','label':'本期'},{'key':'previous','label':'基期'},{'key':'delta','label':'变化量'}],'rows':rr})
    by_id={r['id']:r for r in results}
    for i,pair in enumerate(plan.comparisons):
        a,b=by_id[pair.left],by_id[pair.right];metric=a['spec']['metric']
        same_days=a['coverage']['expected_days']==b['coverage']['expected_days']
        complete=a['coverage']['complete'] and b['coverage']['complete']
        av,bv=a['value'],b['value']
        if pair.basis=='daily_average':
            av=av/a['coverage']['expected_days'] if av is not None and complete else None
            bv=bv/b['coverage']['expected_days'] if bv is not None and complete else None
        add(f'C{i+1}.left',pair.title+'左侧数值',formatted(av,metric))
        add(f'C{i+1}.right',pair.title+'右侧数值',formatted(bv,metric))
        delta=av-bv if av is not None and bv is not None and complete else None
        add(f'C{i+1}.delta',pair.title+'差额',formatted_delta(delta,metric))
        rate=delta/abs(bv) if delta is not None and bv else None
        add(f'C{i+1}.rate',pair.title+'相对变化率',f'{rate*100:+.2f}%' if rate is not None else '不可计算（数据不完整或基数为零）')
        if not same_days:add(f'C{i+1}.days','比较区间天数',f"左侧 {a['coverage']['expected_days']} 天，右侧 {b['coverage']['expected_days']} 天；总额比较需留意天数差异，日均比较需完整覆盖")
    return facts,tables
