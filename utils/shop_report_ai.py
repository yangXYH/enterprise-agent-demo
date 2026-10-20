"""Grounded AI answers for the shop-report chat.

The query planner is deterministic (the question space of a shop-month table
is small), so every answer is built from the same parameterized queries the
shop-report page shows.  The AI writer then writes the narrative from facts
that only carry placeholder references — every number is inserted from the
computed fact registry, never copied by the model — and a validation pass
rejects drafts that invent figures or omit the requested conclusion.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from fastapi.concurrency import run_in_threadpool

from utils import shop_report_service as service
from utils import shop_report_query_service as query
from utils.operating_analysis_ai import _client, AI_SEMAPHORE, close_client
from openai import APITimeoutError, APIConnectionError, RateLimitError

Progress = "Callable[[str, str | None], Awaitable[None]]"  # noqa: F821
NUMBER_RE = re.compile(r'\d|[零一二三四五六七八九十百千万亿两]+(?:倍|成|元|件|单|百分点|百分比|%)')
PLACEHOLDER_RE = re.compile(r'\{\{([A-Za-z0-9_.-]+)\}\}')


class Section(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=80)
    paragraphs: list[str] = Field(default_factory=list, max_length=5)
    bullets: list[str] = Field(default_factory=list, max_length=8)


class Draft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sections: list[Section] = Field(min_length=1, max_length=9)
    limitations: list[str] = Field(default_factory=list, max_length=6)


class Review(BaseModel):
    model_config = ConfigDict(extra='forbid')
    relevant: bool
    complete: bool
    grounded: bool
    actionable: bool
    issues: list[str] = Field(default_factory=list, max_length=8)


def _json(text: str):
    cleaned = (text or '').strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = min((i for i in (cleaned.find('{'), cleaned.find('[')) if i >= 0), default=-1)
        if start < 0:
            raise ValueError('模型未返回可解析的结构')
        opener = cleaned[start]
        closer = '}' if opener == '{' else ']'
        depth = 0
        quoted = False
        escape = False
        for i, ch in enumerate(cleaned[start:], start):
            if quoted:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    quoted = False
            elif ch == '"':
                quoted = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return json.loads(cleaned[start:i + 1])
        raise ValueError('模型返回的结构不完整')


def _model() -> str:
    return os.getenv('SHOP_REPORT_AI_MODEL') or os.getenv('OPERATING_AI_MODEL', 'deepseek-v4-flash')


def _writer_timeout() -> float:
    # The ARK endpoint can take well over a minute to first token; give the
    # narrative writer a generous window while keeping the fallback draft ready.
    return max(60, min(180, float(os.getenv('SHOP_REPORT_AI_TIMEOUT_SECONDS', '120'))))


def _review_enabled() -> bool:
    return os.getenv('SHOP_REPORT_AI_REVIEW_ENABLED', '0').strip().lower() in ('1', 'true', 'yes', 'on')


async def _complete(system: str, payload: dict, max_tokens: int = 2800, timeout: float | None = None):
    client = _client()
    result = await client.chat.completions.create(
        model=_model(),
        messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
        temperature=0, max_tokens=max_tokens, **({'timeout': timeout} if timeout else {}),
    )
    return _json(result.choices[0].message.content or '')


def _bounded_draft(payload):
    if not isinstance(payload, dict):
        return Draft.model_validate(payload)
    result = dict(payload)
    sections = []
    for raw in (result.get('sections') or [])[:9]:
        if not isinstance(raw, dict):
            continue
        section = dict(raw)
        for key, limit in (('paragraphs', 5), ('bullets', 8)):
            value = section.get(key, [])
            section[key] = value[:limit] if isinstance(value, list) else []
        sections.append(section)
    result['sections'] = sections
    limitations = result.get('limitations', [])
    result['limitations'] = limitations[:6] if isinstance(limitations, list) else []
    return Draft.model_validate(result)


WRITER_SYSTEM = '''你是严谨、细致、有效的店铺盈利与费用经营分析师。只输出符合给定JSON Schema的对象。
第一部分必须直接回答用户问题；排行问题直接说出店铺、渠道和金额，不得只说“可查看排行”。之后按问题需要解释比较、趋势、费用结构、变化原因、需验证证据和具体行动。
所有金额、百分比、月份、店铺名、费用项必须使用事实占位符，例如 {{Q1.value}} 或 {{Q1.row1}}，禁止自行抄写、计算或改写数字。占位符必须来自facts，且一个占位符只能出现一次。
数据事实来自店铺报表快照（DEMO_BAGS 经营分析看板的店铺维度费用明细）。统一口径：毛利=收入-产品成本；费用合计=SUM(费用字段)；产品净利润=毛利-费用合计；项目净利=产品净利润-房租分摊。人工未计入，source.labor_included=false；品牌返款符号等口径以页面为准。
区分数据库已证明的数值、算术分解的变化贡献、需要额外资料验证的原因假设。若数据为暂估（成本或费用待补、仅有费用、利润暂估），必须明确说明：暂估结果不能当作确定结论，“仅有费用”不等于经营亏损，净利为空的店铺不要猜测其盈亏。日期和店铺范围要以{{...scope}}事实为准。
费用待补时按已录费用输出暂估产品净利润和项目净利，注明费用补齐后重算；成本缺失或收入来源冲突时，毛利和净利不计算。
已按用户授权用均价补入的成本可以计算毛利和净利，但必须明确称为“成本暂估”，不能说实际成本全部匹配；实际成本补齐后重算。费用是否待补分别说明。
事实占位符展开后已包含完整对象、单位和标点；不要在占位符前后重复单位、金额、店铺名或同义改述。引用逐店比较事实时直接承接其结论。
标题不要写阿拉伯数字。篇幅由问题复杂度决定：简单问题直接但有证据；比较、原因分析要详细完整。'''

REVIEW_SYSTEM = '''你是店铺报表回答审查器。只输出JSON Schema对象。逐项检查：
一、是否直接回答原问题和全部answer_requirements，尤其是否给出用户问的店铺或金额；
二、数值结论是否与提供事实完全一致，是否避免把暂估或“仅有费用”写成确定盈亏；
三、是否把假设写成事实、混淆收入/毛利/净利口径，或给出无关模板建议；
四、若用户要求分析或建议，建议是否具体对应证据并说明需补充什么资料；若只要求一个事实或排行，直接给出完整证据即可将actionable设为true。
任一关键问题都必须将相应布尔值设为false，并给出可执行修复说明。'''


def _facts_payload(facts: dict) -> list[dict]:
    return [{'id': f['id'], 'label': f['label'], 'text': f['text']} for f in facts.values()]


_CN_MONTHS = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二']


def _cn_title(text: str) -> str:
    """把标题里的“2026年9月”转成“九月”，回退草稿标题不能含阿拉伯数字。"""
    def repl(match):
        month = int(match.group(1))
        return (_CN_MONTHS[month] if 1 <= month <= 12 else str(month)) + '月'
    return re.sub(r'20\d{2}年(\d{1,2})月', repl, text)


async def _write(question_text, plan, results, facts, prior_errors=None):
    payload = {
        'question': question_text,
        'interpreted_question': plan.normalized_question,
        'intent': plan.intent,
        'answer_requirements': plan.answer_requirements,
        'facts': _facts_payload(facts),
        'query_shapes': [{'id': r['id'], 'title': r['title'], 'group': r['spec']['group'],
                          'metric': r['metric_label'], 'row_count': r['group_count'],
                          'has_comparisons': bool(r['comparisons'])} for r in results],
        'previous_review_issues': prior_errors or [],
        'output_schema': Draft.model_json_schema(),
    }
    return _bounded_draft(await _complete(WRITER_SYSTEM, payload, 2800, _writer_timeout()))


async def _review(question_text, plan, draft, facts):
    used = set(PLACEHOLDER_RE.findall(_draft_text(draft)))
    payload = {
        'question': question_text,
        'interpreted_question': plan.normalized_question,
        'answer_requirements': plan.answer_requirements,
        'draft': draft.model_dump(),
        'referenced_facts': [facts[x] for x in used if x in facts],
        'output_schema': Review.model_json_schema(),
    }
    return Review.model_validate(await _complete(REVIEW_SYSTEM, payload, 900))


def _draft_text(draft: Draft) -> str:
    return '\n'.join([s.title + '\n' + '\n'.join(s.paragraphs + s.bullets) for s in draft.sections] + draft.limitations)


def _validate_draft(draft: Draft, facts: dict, plan):
    errors = []
    used = []
    for s in draft.sections:
        for value in [s.title, *s.paragraphs, *s.bullets]:
            ids = PLACEHOLDER_RE.findall(value)
            used.extend(ids)
            stripped = PLACEHOLDER_RE.sub('', value)
            if '{{' in stripped or '}}' in stripped:
                errors.append('存在无效事实占位符')
            if NUMBER_RE.search(stripped):
                errors.append('正文含未经核对的数字：' + stripped[:80])
            for fid in ids:
                if fid not in facts:
                    errors.append('引用了不存在的事实：' + fid)
    for value in draft.limitations:
        for fid in PLACEHOLDER_RE.findall(value):
            if fid not in facts:
                errors.append('限制说明引用了不存在的事实：' + fid)
        if NUMBER_RE.search(PLACEHOLDER_RE.sub('', value)):
            errors.append('限制说明含未经核对的数字')
    for q in plan.queries:
        if q.group == 'total' and q.id + '.value' not in used:
            errors.append('没有回答查询的核心数值：' + q.id)
        if q.group in ('shop', 'month', 'fee') and q.id + '.row1' in facts and q.id + '.row1' not in used:
            errors.append('没有直接说出第一项：' + q.id)
        if q.shop_id and q.id + '.object' in facts and q.id + '.object' not in used and plan.intent in ('lookup', 'comparison'):
            errors.append('没有说明精确查询对应的店铺：' + q.id)
    if not draft.sections[0].paragraphs and not draft.sections[0].bullets:
        errors.append('第一部分没有直接回答用户')
    if errors:
        raise ValueError('；'.join(dict.fromkeys(errors))[:1600])
    return list(dict.fromkeys(used))


def _render(text: str, facts: dict) -> str:
    rendered = PLACEHOLDER_RE.sub(lambda m: facts[m.group(1)]['text'], text)
    return rendered.replace(' 元 元', ' 元').replace('。）。', '）。')


def _render_draft(draft: Draft, facts: dict) -> dict:
    sections = []
    used = []
    for s in draft.sections:
        ids = []
        for text in s.paragraphs + s.bullets:
            ids.extend(PLACEHOLDER_RE.findall(text))
        used.extend(ids)
        sections.append({'title': _render(s.title, facts),
                         'paragraphs': [_render(x, facts) for x in s.paragraphs],
                         'bullets': [_render(x, facts) for x in s.bullets]})
    return {'sections': sections, 'limitations': [_render(x, facts) for x in draft.limitations],
            'fact_ids': list(dict.fromkeys(used))}


def _fallback_draft(plan, results, facts, degraded=True):
    sections = []
    # 概览类问题：把收入/毛利/费用/净利等合并成一段「经营概览」，避免逐条断着出。
    if plan.intent == 'overview' and results:
        bullets = ['{{' + results[0]['id'] + '.scope}}']
        if results[0]['id'] + '.object' in facts:
            bullets.append('{{' + results[0]['id'] + '.object}}')
        for r in results:
            qid = r['id']
            if r['spec']['group'] == 'total' and (r['value'] is not None or (qid + '.value') in facts):
                bullets.append(r['metric_label'] + '：{{' + qid + '.value}}')
            elif r['rows']:
                for i in range(min(3, len(r['rows']))):
                    bullets.append('{{' + f'{qid}.row{i + 1}' + '}}')
        sections.append(Section(title='直接结论 · 经营概览', bullets=bullets[:8]))
        return _fallback_tail(plan, results, facts, sections, degraded)
    for index, r in enumerate(results):
        q = r['spec']
        qid = r['id']
        direct = ['{{' + qid + '.scope}}']
        if qid + '.object' in facts:
            direct.append('{{' + qid + '.object}}')
        if r['rows']:
            for i in range(min(5, len(r['rows']))):
                fid = f'{qid}.row{i + 1}'
                if q['group'] == 'fee':
                    direct.append(r['rows'][i]['label'] + '：{{' + fid + '}}')
                else:
                    direct.append('{{' + fid + '}}')
        elif qid + '.value' in facts:
            direct.append('{{' + qid + '.value}}')
        for kind in r['comparisons']:
            name = {'mom': '上期', 'yoy': '去年同期'}[kind]
            p = lambda suffix: '{{' + f'{qid}.{kind}.{suffix}' + '}}'
            direct.append(name + '（' + p('period') + '）：' + p('value') + '；变化率 ' + p('rate'))
        title = _cn_title(r.get('title', '指标结果')).strip() or '指标结果'
        sections.append(Section(title=('直接结论 · ' if index == 0 else '') + title, bullets=direct[:8]))
    return _fallback_tail(plan, results, facts, sections, degraded)


def _fallback_tail(plan, results, facts, sections, degraded):
    if plan.intent == 'comparison' and 'C1.delta' in facts:
        sections.append(Section(title='差额对比', bullets=['差额：{{C1.delta}}；相对变化率：{{C1.rate}}']))
    analysis = []
    for r in results:
        qid = r['id']
        for row in r.get('rows', []):
            for kind in row.get('per_comparisons') or {}:
                fid = f'{qid}.row{row_index(r, row) + 1}.{kind}'
                if fid in facts:
                    analysis.append('{{' + fid + '}}')
        if r['spec']['group'] in ('month', 'shop') and qid + '.peak' in facts:
            analysis.append('峰值：{{' + qid + '.peak}}')
            analysis.append('低值：{{' + qid + '.low}}')
    for offset in range(0, len(analysis), 8):
        sections.append(Section(title='变化定位' if offset == 0 else '更多变化证据', bullets=analysis[offset:offset + 8]))
    limitation = ('模型解读暂未完成；上方直接结论和数据表仍来自店铺报表快照计算，可以核对使用。' if degraded else
                  '本回答由服务端按店铺报表统一口径直接查询并计算；原因判断仍需结合活动、投放、库存等业务资料。')
    return Draft(sections=sections, limitations=[limitation])


def row_index(r, row):
    return r['rows'].index(row)


def _direct_preview(plan, results, facts):
    lines = ['数据查询已经完成，先给出已核对的直接结论。']
    for r in results:
        qid = r['id']
        lines.extend(['', r['title']])
        for fid in (qid + '.scope', qid + '.value', qid + '.object'):
            if fid in facts:
                lines.append(facts[fid]['text'])
        for row in r['rows'][:3]:
            fid = f'{qid}.row{r["rows"].index(row) + 1}'
            if fid in facts:
                lines.append(facts[fid]['text'])
        for kind, comp in r.get('comparisons', {}).items():
            name = {'mom': '上期', 'yoy': '去年同期'}[kind]
            parts = []
            for suffix in ('period', 'value', 'rate'):
                fid = f'{qid}.{kind}.{suffix}'
                if fid in facts:
                    parts.append(facts[fid]['text'])
            if parts:
                lines.append(name + '：' + '；'.join(parts))
    lines.extend(['', '详细分析正在继续生成…'])
    return '\n'.join(lines)


async def _stream_preview(text, progress):
    if not progress:
        return
    step = max(24, min(96, len(text) // 10 or 24))
    for end in range(step, len(text) + step, step):
        await progress('正在流式生成详细分析', text[:min(end, len(text))])
        if end < len(text):
            await asyncio.sleep(.1)


def _highlights(results):
    cards = []
    for r in results:
        q = r['spec']
        if q['group'] in ('shop', 'month') and r['rows']:
            row = r['rows'][0]
            label = r['title'] + ('第一名' if q['order'] == 'desc' else '最低')
            cards.append({'label': label, 'value': row['label'], 'note': query.formatted(row['value'], q['metric'])})
        elif q['group'] == 'fee' and r['rows']:
            cards.append({'label': r['title'] + '最大项', 'value': r['rows'][0]['label'],
                          'note': query.formatted(r['rows'][0]['value'], 'total_fees')})
        elif r['value'] is not None:
            cards.append({'label': r['title'], 'value': query.formatted(r['value'], q['metric']), 'note': r['metric_label']})
        for kind, comp in r['comparisons'].items():
            cards.append({'label': r['title'] + {'mom': '环比', 'yoy': '同比'}[kind],
                          'value': f"{comp['rate']:+.2f}%" if comp['rate'] is not None else '不可完整比较',
                          'note': '无数据' if not comp['available'] else query.formatted(comp['value'], q['metric'])})
    return cards[:8]


def _table_specs(tables):
    output = []
    for table in tables:
        rows = table['rows']
        if len(rows) > 50:
            rows = rows[:6] + rows[-6:]
        output.append({**table, 'rows': rows, 'total_rows': len(table['rows'])})
    return output


def _partial_limitation(results) -> str | None:
    for r in results:
        s = r['summary']
        if s.get('expense_only'):
            return '统计范围内包含“仅有费用”的店铺月份，其经营利润不可计算，不能据此判断亏损。'
        if s.get('source_conflict'):
            return '统计范围内有店铺月份收入来源存在冲突，毛利与净利需核对收入来源后计算。'
        if s.get('cost_partial'):
            return '统计范围内有店铺月份成本待补，毛利与净利需补全 SKU 成本后计算。'
        if s.get('cost_estimated'):
            return '包含按同店同月均价暂估的产品成本，毛利与净利均为暂估；实际成本及缺失费用补齐后重算，未计人工。'
        if s.get('fees_partial'):
            return '产品净利润与项目净利按当前已录费用暂估，费用补齐后重算；未计人工。'
        if s.get('provisional'):
            return '统计范围内包含利润暂估的店铺月份，结果以当前已录数据计算，不能当作最终经营结果。'
    return None


async def analyze(question_text: str, filters: dict | None = None, history: list | None = None, progress: Progress | None = None):
    async with AI_SEMAPHORE:
        return await _analyze_locked(question_text, filters, history, progress)


async def _analyze_locked(question_text, filters, history, progress):
    meta = await run_in_threadpool(service.metadata)
    if not meta.get('months'):
        raise ValueError('请先导入店铺报表数据')
    started = time.monotonic()
    trace = []

    async def stage(name, partial_answer=None):
        trace.append({'stage': name, 'elapsed_ms': round((time.monotonic() - started) * 1000)})
        if progress:
            await progress(name, partial_answer)

    await stage('正在理解问题')
    plan = await run_in_threadpool(query.deterministic_plan, question_text, meta, filters, history)
    if plan.intent == 'clarification':
        return {'answer': plan.clarification,
                'report': {'intent': 'clarification', 'understood_as': question_text, 'sections': [],
                           'limitations': [], 'highlights': [], 'tables': [], 'charts': [], 'knowledge_sources': [],
                           'audit': {'answer_requirements': [], 'used_fact_ids': [], 'review': None, 'repair_count': 0, 'mode': 'deterministic'}},
                'evidence': None, 'knowledge': [], 'model': '确定性经营查询', 'trace': trace,
                'retrieval': {'candidate_count': 0, 'selected_count': 0, 'method': '店铺报表快照查询'}}

    await stage('正在查询并核对店铺数据')
    d = await run_in_threadpool(service.load)
    results = []
    for spec in plan.queries:
        results.append(await run_in_threadpool(query.execute, d, spec))
    facts, tables = await run_in_threadpool(query.facts_for, results, plan, meta)

    await stage('正在生成详细分析')
    preview_task = asyncio.create_task(_stream_preview(_direct_preview(plan, results, facts), progress))
    review = None
    repair_count = 0
    try:
        try:
            draft = await _write(question_text, plan, results, facts)
            _validate_draft(draft, facts, plan)
        except (ValueError, ValidationError, KeyError) as e:
            repair_count += 1
            draft = await _write(question_text, plan, results, facts, [str(e)[:1200]])
            _validate_draft(draft, facts, plan)
        if _review_enabled():
            await stage('正在校验回答完整性')
            review = await _review(question_text, plan, draft, facts)
            if not all((review.relevant, review.complete, review.grounded, review.actionable)):
                repair_count += 1
                draft = await _write(question_text, plan, results, facts, review.issues)
                _validate_draft(draft, facts, plan)
                review = await _review(question_text, plan, draft, facts)
                if not all((review.relevant, review.complete, review.grounded, review.actionable)):
                    raise ValueError('回答完整性校验未通过，请换一种更明确的问法重试')
    except (APITimeoutError, APIConnectionError, RateLimitError, ValueError, ValidationError, KeyError):
        review = None
        draft = _fallback_draft(plan, results, facts)
        _validate_draft(draft, facts, plan)
    finally:
        await preview_task

    rendered = _render_draft(draft, facts)
    limitation = _partial_limitation(results)
    limitations = rendered['limitations']
    if limitation and limitation not in limitations:
        limitations = limitations + [limitation]
    report = {
        'intent': plan.intent,
        'understood_as': plan.normalized_question,
        'sections': rendered['sections'],
        'limitations': limitations,
        'highlights': _highlights(results),
        'tables': _table_specs(tables),
        'charts': [],
        'knowledge_sources': [],
        'audit': {'answer_requirements': plan.answer_requirements,
                  'used_fact_ids': rendered['fact_ids'],
                  'review': review.model_dump() if review else None,
                  'repair_count': repair_count, 'mode': plan.execution},
    }
    answer = '\n\n'.join(s['title'] + '\n' + '\n'.join(s['paragraphs'] + s['bullets']) for s in report['sections'])
    if report['limitations']:
        answer += '\n\n说明\n' + '\n'.join(report['limitations'])
    evidence = None
    if results:
        evidence = {'filters': results[0]['spec'], 'query_results': results}
    await stage('回答已完成')
    return {'answer': answer, 'report': report, 'evidence': evidence, 'knowledge': [],
            'model': '确定性店铺查询' if plan.execution == 'deterministic' else _model(),
            'trace': trace,
            'retrieval': {'candidate_count': 0, 'selected_count': len(results),
                          'method': '店铺报表快照参数化查询 + 事实占位校验' + (' + 回答审查' if review else '')}}
