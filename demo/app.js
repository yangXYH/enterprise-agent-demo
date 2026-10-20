/* Offline demo: no framework, API, network request or build step is needed. */
(() => {
  'use strict';
  const data = window.DEMO_DATA;
  if (!data) { document.getElementById('content').textContent = '测试数据未加载，请保留 demo 目录并重新打开根目录 index.html。'; return; }
  const pages = {
    overview: ['◫', '经营总览', 'BUSINESS OVERVIEW', '把业务数据放在一起，让每一次决策都有依据。'],
    reports: ['▤', '店铺报表', 'SHOP PERFORMANCE', '从收入到费用，查看测试店铺的经营表现。'],
    inventory: ['▦', '库存预警', 'INVENTORY MONITOR', '识别库存缺口，查看安全库存与在途补货。'],
    people: ['♧', '人事管理', 'PEOPLE & ORGANIZATION', '在一个视图里了解测试团队与人员结构。'],
    support: ['◉', '客服看板', 'CUSTOMER EXPERIENCE', '用测试指标观察服务效率与问题解决情况。'],
    projects: ['◇', 'AI 项目看板', 'PROJECT WORKSPACE', '记录演示项目进展，修改仅保存在当前浏览器。'],
    assistant: ['✧', '数据问答', 'BUSINESS ASSISTANT', '向当前测试数据提问，查看可核对的计算结果。'],
  };
  const state = { page: 'overview', month: data.months.at(-1), channel: '', search: '', department: '', stock: '', messages: [] };
  const projectKey = 'enterprise-agent-demo-projects-v1';
  const storage = {
    read(key) { try { return localStorage.getItem(key); } catch { return null; } },
    write(key, value) { try { localStorage.setItem(key, value); } catch { toast('浏览器未允许本地存储，修改仅在本次打开期间保留。'); } },
  };
  let projects = structuredClone(data.projects);
  try {
    const saved = JSON.parse(storage.read(projectKey) || 'null');
    if (Array.isArray(saved) && saved.every(p => typeof p.id === 'string' && typeof p.name === 'string' && typeof p.owner === 'string' && Number.isFinite(p.progress) && p.progress >= 0 && p.progress <= 100 && typeof p.status === 'string')) projects = saved;
  } catch { /* Invalid local demo state falls back to the generated fixtures. */ }
  const money = value => Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const integer = value => Number(value).toLocaleString('zh-CN');
  const sum = (rows, key) => rows.reduce((total, row) => total + Number(row[key] || 0), 0);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const channelName = key => ({ self: '自营渠道', pop: '平台渠道', store: '线下渠道' }[key] || key);
  const shopName = id => data.shops.find(shop => shop.shop_id === id)?.shop_name || id;
  const period = () => state.month === 'all' ? '2026 年 1—9 月' : state.month.replace('-', ' 年 ') + ' 月';
  const snapshot = () => data.rows.filter(row => (state.month === 'all' || row.month === state.month) && (!state.channel || row.channel === state.channel));
  const shortMoney = value => value >= 10000 ? (value / 10000).toFixed(2) : money(value);
  const metric = (title, value, unit, hint, icon = '↗', detail = '') => `<article class="metric"><div class="metric-top">${esc(title)}<span class="metric-icon">${icon}</span></div><div class="metric-value number">${esc(value)}<small>${esc(unit)}</small></div><div class="metric-bottom">${detail ? `<strong>${esc(detail)}</strong>` : ''}${esc(hint)}</div></article>`;
  const pill = (text, kind = '') => `<span class="tag ${kind}">${esc(text)}</span>`;
  const search = placeholder => `<input class="search" id="table-search" aria-label="${esc(placeholder)}" placeholder="⌕  ${esc(placeholder)}" value="${esc(state.search)}">`;
  const channelSelect = () => `<select id="channel-filter" aria-label="渠道筛选"><option value="">全部渠道</option>${['self', 'pop', 'store'].map(value => `<option value="${value}" ${state.channel === value ? 'selected' : ''}>${channelName(value)}</option>`).join('')}</select>`;
  const table = (headers, rows) => `<div class="table-wrap"><table><thead><tr>${headers.map(h => `<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.length ? rows.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${headers.length}" class="empty">没有符合筛选条件的测试记录</td></tr>`}</tbody></table></div>`;
  let toastTimer;
  function toast(message) {
    const box = document.getElementById('toast'); box.textContent = message; box.classList.add('show');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => box.classList.remove('show'), 3000);
  }
  function trendChart() {
    const series = data.months.map(month => {
      const rows = data.rows.filter(row => row.month === month && (!state.channel || row.channel === state.channel));
      return { month, revenue: sum(rows, 'revenue'), profit: sum(rows, 'net_profit') };
    });
    const width = 640, height = 220, left = 45, top = 15, bottom = 188, right = 622;
    const max = Math.ceil(Math.max(...series.map(p => p.revenue)) / 200000) * 200000;
    const x = index => left + index * (right - left) / (series.length - 1);
    const y = value => bottom - value / max * (bottom - top);
    const points = key => series.map((p, i) => `${x(i)},${y(p[key])}`).join(' ');
    return `<svg class="chart" role="img" aria-label="2026年1至9月测试营收与项目净利趋势" viewBox="0 0 ${width} ${height}">
      <defs><linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#6aab8e" stop-opacity=".17"/><stop offset="1" stop-color="#6aab8e" stop-opacity="0"/></linearGradient></defs>
      ${[0, 1, 2, 3, 4].map(i => `<line class="chart-grid" x1="${left}" y1="${y(max * i / 4)}" x2="${right}" y2="${y(max * i / 4)}"/><text x="0" y="${y(max * i / 4) + 4}">${max * i / 4 / 10000}万</text>`).join('')}
      <polygon fill="url(#area-fill)" points="${left},${bottom} ${points('revenue')} ${right},${bottom}"/>
      <polyline points="${points('revenue')}" fill="none" stroke="#4d9879" stroke-width="2.5" stroke-linejoin="round"/>
      <polyline points="${points('profit')}" fill="none" stroke="#b6c9a7" stroke-width="2.5" stroke-linejoin="round"/>
      ${series.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.revenue)}" r="3" fill="#4d9879"><title>${p.month} 营收 ${money(p.revenue)} 元</title></circle><text x="${x(i)}" y="210" text-anchor="middle">${i + 1}月</text>`).join('')}</svg>`;
  }
  function shopSummaries() {
    return data.shops.filter(shop => !state.channel || shop.channel === state.channel).map(shop => {
      const rows = snapshot().filter(row => row.shop_id === shop.shop_id);
      return { ...shop, revenue: sum(rows, 'revenue'), cost: sum(rows, 'costG'), fees: sum(rows, 'total_fees'), profit: sum(rows, 'net_profit'), quantity: sum(rows, 'quantity') };
    }).sort((a, b) => b.revenue - a.revenue);
  }
  function revenueMetrics() {
    const rows = snapshot(), revenue = sum(rows, 'revenue'), profit = sum(rows, 'net_profit');
    const previousIndex = data.months.indexOf(state.month) - 1;
    const previous = data.rows.filter(row => row.month === data.months[previousIndex] && (!state.channel || row.channel === state.channel));
    const previousRevenue = sum(previous, 'revenue');
    const change = previousRevenue ? ((revenue / previousRevenue - 1) * 100).toFixed(1) : null;
    return `<div class="metrics">${metric('测试营业收入', shortMoney(revenue), revenue >= 10000 ? '万元' : '元', change !== null ? '较上一月' : '所选期间汇总', '↗', change !== null ? `${Number(change) >= 0 ? '+' : ''}${change}%` : '')}${metric('测试项目净利', shortMoney(profit), profit >= 10000 ? '万元' : '元', '收入 − 成本 − 已录费用', '◈')}${metric('测试净利率', revenue ? (profit / revenue * 100).toFixed(1) : '0.0', '%', '未包含人工与税费', '◷')}${metric('成交商品件数', integer(sum(rows, 'quantity')), '件', `${new Set(rows.map(r => r.shop_id)).size} 家测试店铺`, '▦')}</div>`;
  }
  function overview() {
    const summaries = shopSummaries(), revenue = sum(snapshot(), 'revenue');
    return `${revenueMetrics()}<div class="grid-main"><section class="panel"><div class="panel-header"><div><h2>营收与项目净利趋势</h2><p class="panel-subtitle">2026 年 1—9 月 · 按月汇总测试数据</p></div><span class="pill">单位：人民币</span></div>${trendChart()}<div class="legend"><span><i style="background:#4d9879"></i>营业收入</span><span><i style="background:#b6c9a7"></i>项目净利</span></div></section><section class="panel"><div class="panel-header"><div><h2>销售渠道分布</h2><p class="panel-subtitle">${period()} · 收入占比</p></div><span class="pill">3 个渠道</span></div>${['self', 'pop', 'store'].map((key, i) => { const value = sum(snapshot().filter(row => row.channel === key), 'revenue'), ratio = revenue ? value / revenue * 100 : 0; return `<div class="channel-item"><span class="channel-icon">${['自', '平', '线'][i]}</span><div class="channel-body"><div class="channel-label"><span>${channelName(key)}</span><b>${ratio.toFixed(1)}%</b></div><div class="progress"><span style="width:${ratio}%"></span></div></div></div>`; }).join('')}<div class="channel-foot">金额基于同一组测试明细计算，可在店铺报表逐项核对。</div></section></div><section class="panel"><div class="panel-header"><div><h2>店铺表现</h2><p class="panel-subtitle">当前期间 · 按测试营业收入降序排列</p></div><a class="button" href="#reports">查看完整报表 ↗</a></div>${table(['店铺名称', '经营渠道', '营业收入 / 元', '项目净利 / 元', '净利率', '数据状态'], summaries.map(s => [esc(s.shop_name), pill(channelName(s.channel), 'neutral'), money(s.revenue), `<span class="positive">${money(s.profit)}</span>`, (s.profit / s.revenue * 100).toFixed(1) + '%', pill('测试数据')]))}</section><section class="insight"><span class="insight-icon">✧</span><div><h3>数据观察</h3><p>${period()}，${esc(summaries[0]?.shop_name || '')}的测试营收最高。当前共有 ${data.inventory.filter(i => i.stock < i.safety).length} 个 SKU 低于安全库存，可前往库存看板查看补货缺口。</p></div><a class="button" href="#assistant">向数据提问 ↗</a></section>`;
  }
  function reports() {
    const rows = shopSummaries().filter(shop => shop.shop_name.includes(state.search));
    return `${revenueMetrics()}<section class="panel"><div class="panel-header"><div><h2>测试店铺损益表</h2><p class="panel-subtitle">${period()} · 全部金额单位为元</p></div><div class="table-tools">${channelSelect()}${search('搜索测试店铺')}</div></div>${table(['测试店铺', '渠道', '营业收入', '商品成本', '已录费用', '项目净利', '净利率'], rows.map(s => [esc(s.shop_name), pill(channelName(s.channel), 'neutral'), money(s.revenue), money(s.cost), money(s.fees), `<b class="positive">${money(s.profit)}</b>`, (s.profit / s.revenue * 100).toFixed(1) + '%']))}<p class="panel-foot">计算口径：项目净利 = 营业收入 − 商品成本 − 推广 / 平台 / 物流 / 仓储费用。本演示未计入人工与税费。</p></section>`;
  }
  function inventoryRows() {
    return data.inventory.filter(row => `${row.sku}${row.name}${row.warehouse}`.toLowerCase().includes(state.search.toLowerCase()) && (!state.stock || (state.stock === 'low' ? row.stock < row.safety : row.stock >= row.safety)));
  }
  function inventory() {
    const low = data.inventory.filter(row => row.stock < row.safety);
    return `<div class="metrics">${metric('测试 SKU', data.inventory.length, '个', '全部为虚构测试商品', '▦')}${metric('当前可用库存', integer(sum(data.inventory, 'stock')), '件', '测试库存明细汇总', '◇')}${metric('低于安全库存', low.length, '个', '可用库存低于 100 件', '↧')}${metric('在途补货', sum(data.inventory, 'onway'), '件', '在途库存单独统计', '→')}</div><section class="panel"><div class="panel-header"><div><h2>库存明细与预警</h2><p class="panel-subtitle">数量由测试数据生成器固定生成</p></div><div class="table-tools"><select id="stock-filter" aria-label="库存状态筛选"><option value="">全部状态</option><option value="low" ${state.stock === 'low' ? 'selected' : ''}>低库存预警</option><option value="normal" ${state.stock === 'normal' ? 'selected' : ''}>库存正常</option></select>${search('搜索测试商品 / SKU')}</div></div>${table(['SKU', '测试商品', '仓库', '可用库存', '安全库存', '在途', '状态'], inventoryRows().map(i => [esc(i.sku), esc(i.name), esc(i.warehouse), integer(i.stock), integer(i.safety), integer(i.onway), pill(i.stock < i.safety ? '待补货' : '正常', i.stock < i.safety ? 'warn' : '')]))}</section>`;
  }
  function employeeRows() {
    return data.employees.filter(row => `${row.name}${row.id}${row.position}`.includes(state.search) && (!state.department || row.department === state.department));
  }
  function people() {
    return `<div class="metrics">${metric('测试员工', data.employees.length, '人', '测试员工01—测试员工24', '♧')}${metric('部门数量', new Set(data.employees.map(e => e.department)).size, '个', '产品 / 运营 / 客服 / 人事', '▦')}${metric('试用期员工', data.employees.filter(e => e.status === '试用期').length, '人', '固定生成的测试状态', '◷')}${metric('示例企业', 2, '家', '示例科技 / 示例传媒', '◇')}</div><section class="panel"><div class="panel-header"><div><h2>测试员工花名册</h2><p class="panel-subtitle">未包含身份证、银行账户或可拨打的电话号码</p></div><div class="table-tools"><select id="department-filter" aria-label="部门筛选"><option value="">全部部门</option>${[...new Set(data.employees.map(e => e.department))].map(d => `<option ${state.department === d ? 'selected' : ''}>${esc(d)}</option>`).join('')}</select>${search('搜索测试员工 / 工号')}</div></div>${table(['测试工号', '姓名', '所属企业', '部门', '岗位', '入职日期', '状态', '测试联系方式'], employeeRows().map(e => [esc(e.id), `<b>${esc(e.name)}</b>`, esc(e.company), esc(e.department), esc(e.position), e.joined, pill(e.status, e.status === '试用期' ? 'warn' : ''), esc(e.contact)]))}<p class="panel-foot">共 ${employeeRows().length} 条筛选结果。所有人员资料均为虚构，联系方式为不可拨打的测试标识。</p></section>`;
  }
  function support() {
    const total = sum(data.support, 'questions'), solved = sum(data.support, 'solved');
    return `<div class="metrics">${metric('测试接待问题', integer(total), '个', '5 位测试客服的固定记录', '◉')}${metric('问题解决率', (solved / total * 100).toFixed(1), '%', '已解决问题 / 接待问题', '✓')}${metric('平均响应', (sum(data.support, 'response') / data.support.length).toFixed(2), '秒', '测试客服的算术平均', '◷')}${metric('平均满意度', (sum(data.support, 'satisfaction') / data.support.length).toFixed(2), '%', '测试指标，不代表真实服务结果', '☆')}</div><section class="panel"><div class="panel-header"><div><h2>测试客服服务表现</h2><p class="panel-subtitle">固定演示快照 · 与月份筛选无关</p></div>${search('搜索测试客服')}</div>${table(['客服姓名', '测试账号', '接待问题', '已解决', '解决率', '平均响应 / 秒', '满意度'], data.support.filter(row => `${row.name}${row.account}`.includes(state.search)).map(row => [esc(row.name), esc(row.account), integer(row.questions), integer(row.solved), (row.solved / row.questions * 100).toFixed(1) + '%', row.response.toFixed(2), pill(row.satisfaction.toFixed(2) + '%')]))}</section>`;
  }
  function projectView() {
    return `<div class="metrics">${metric('演示项目', projects.length, '个', '支持本地添加与进度更新', '◇')}${metric('进行中', projects.filter(p => p.status === '进行中').length, '个', '演示项目状态', '◷')}${metric('已完成', projects.filter(p => p.progress === 100).length, '个', '进度已达到 100%', '✓')}${metric('平均进度', projects.length ? (sum(projects, 'progress') / projects.length).toFixed(0) : '0', '%', '当前浏览器本地记录', '↗')}</div><div class="panel-header"><div><h2>AI 应用试点</h2><p class="panel-subtitle">示例项目不会调用模型或影响原后端</p></div><div><button class="button" id="reset-projects">重置演示项目</button> <button class="button primary" id="add-project">＋ 添加测试项目</button></div></div><div class="page-grid">${projects.map(p => `<article class="project-card"><div>${pill(p.status, p.status === '待评审' ? 'warn' : '')}</div><h3>${esc(p.name)}</h3><p>负责人 ${esc(p.owner)} <span style="float:right">${p.progress}%</span></p><div class="progress"><span style="width:${p.progress}%"></span></div><button class="button" data-advance="${esc(p.id)}" ${p.progress === 100 ? 'disabled' : ''}>${p.progress === 100 ? '项目已完成' : '推进进度 +10%'}</button></article>`).join('')}</div>`;
  }
  const questions = ['本月销售额和净利是多少？', '哪家测试店铺的营收最高？', '哪些商品需要补货？', '测试团队有多少人？'];
  function answer(question) {
    const rows = snapshot(), source = `\n\n来源：${period()}的本地测试数据（固定公式生成）。`;
    if (/库存|补货|缺货|sku/i.test(question)) {
      const low = data.inventory.filter(i => i.stock < i.safety);
      return `测试库存中有 ${low.length} 个 SKU 低于安全库存：\n${low.map(i => `• ${i.sku} ${i.name}：可用 ${i.stock} 件，安全库存 ${i.safety} 件，在途 ${i.onway} 件；考虑在途后仍缺 ${Math.max(0, i.safety - i.stock - i.onway)} 件。`).join('\n')}\n\n来源：本地测试库存快照，与月份筛选无关。补货建议仅演示算术缺口。`;
    }
    if (/人|员工|部门|团队/.test(question)) return `示例团队有 ${data.employees.length} 位测试员工，分布在 ${new Set(data.employees.map(e => e.department)).size} 个部门，其中 ${data.employees.filter(e => e.status === '试用期').length} 位为测试试用期员工。\n\n来源：本地虚构花名册，不包含真实个人信息。`;
    if (/最高|排行|排名|哪家/.test(question)) return `${period()}，测试店铺按营收排序：\n${shopSummaries().map((s, i) => `${i + 1}. ${s.shop_name}：营收 ${money(s.revenue)} 元，项目净利 ${money(s.profit)} 元。`).join('\n')}${source}`;
    if (/销售|营收|收入|利润|净利|经营/.test(question)) {
      const revenue = sum(rows, 'revenue'), cost = sum(rows, 'costG'), fees = sum(rows, 'total_fees'), profit = sum(rows, 'net_profit');
      return `${period()}，测试营业收入为 ${money(revenue)} 元，商品成本 ${money(cost)} 元，已录费用 ${money(fees)} 元，项目净利 ${money(profit)} 元，净利率 ${(revenue ? profit / revenue * 100 : 0).toFixed(1)}%。\n\n口径：项目净利 = 收入 − 商品成本 − 已录费用，未计人工与税费。${source}`;
    }
    return '当前离线演示支持营收、净利、店铺排行、库存缺口和员工统计。请从右侧示例问题开始。\n\n回答由本地规则和测试数据计算产生，未调用外部大模型；完整源码中的 AI 接口需要另行配置。';
  }
  function assistant() {
    return `<div class="question-layout"><section class="panel chat-window"><div class="panel-header"><div><h2>与测试数据对话</h2><p class="panel-subtitle">当前分析期间：${period()} · 本地规则演示</p></div><span class="pill">零网络请求</span></div><div class="chat-log">${state.messages.length ? state.messages.map(message => `<div class="message ${message.role === 'user' ? 'user' : ''}">${esc(message.text)}</div>`).join('') : '<div class="message">你好，我可以基于本地测试数据计算营收、净利、店铺排名和库存缺口。你想先了解什么？</div>'}</div><form id="question-form" class="chat-input"><input id="question-input" class="search" aria-label="输入测试数据问题" placeholder="例如：本月销售额和净利是多少？" maxlength="300" required><button class="button primary">发送 ↗</button></form></section><aside class="panel"><h2>试试这样问</h2><p class="panel-subtitle">每个答案都可回到报表核对</p>${questions.map((q, i) => `<button class="question-button" data-question="${i}">${q} ↗</button>`).join('')}<ul class="knowledge-list"><li>数据来源：demo/data.js</li><li>人员与金额均为虚构测试数据</li><li>不会发送数据到外部服务</li><li>完整项目保留 Vue + FastAPI 集成源码</li></ul></aside></div>`;
  }
  const views = { overview, reports, inventory, people, support, projects: projectView, assistant };
  function render() {
    const page = pages[state.page];
    document.getElementById('navigation').innerHTML = Object.entries(pages).map(([key, value]) => `<a href="#${key}" class="${state.page === key ? 'active' : ''}" ${state.page === key ? 'aria-current="page"' : ''}><span class="nav-icon" aria-hidden="true">${value[0]}</span><span class="nav-label">${value[1]}</span></a>`).join('');
    document.getElementById('breadcrumb').textContent = page[1];
    document.getElementById('page-title').textContent = page[1];
    document.getElementById('eyebrow').textContent = page[2];
    document.getElementById('page-description').textContent = page[3];
    document.getElementById('month-filter').hidden = !['overview', 'reports', 'assistant'].includes(state.page);
    document.getElementById('content').innerHTML = views[state.page]();
    document.getElementById('table-search')?.addEventListener('input', event => {
      const position = event.target.selectionStart; state.search = event.target.value; render();
      const field = document.getElementById('table-search'); field?.focus(); field?.setSelectionRange(position, position);
    });
    [['channel-filter', 'channel'], ['department-filter', 'department'], ['stock-filter', 'stock']].forEach(([id, key]) => document.getElementById(id)?.addEventListener('change', event => { state[key] = event.target.value; render(); }));
    document.getElementById('question-form')?.addEventListener('submit', event => { event.preventDefault(); ask(document.getElementById('question-input').value); });
    document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => ask(questions[Number(button.dataset.question)])));
    document.querySelectorAll('[data-advance]').forEach(button => button.addEventListener('click', () => {
      const project = projects.find(p => p.id === button.dataset.advance); project.progress = Math.min(100, project.progress + 10); project.status = project.progress === 100 ? '已完成' : '进行中'; saveProjects(); render();
    }));
    document.getElementById('add-project')?.addEventListener('click', () => {
      const name = prompt('输入新的测试项目名称（仅保存在当前浏览器）：', '测试 AI 新项目');
      if (!name?.trim()) return;
      projects.push({ id: `DEMO-${Date.now()}`, name: name.trim().slice(0, 60), owner: '测试员工01', progress: 0, status: '待评审' }); saveProjects(); render();
    });
    document.getElementById('reset-projects')?.addEventListener('click', () => { projects = structuredClone(data.projects); saveProjects(); render(); toast('已恢复默认测试项目'); });
  }
  function saveProjects() { storage.write(projectKey, JSON.stringify(projects)); }
  function ask(question) {
    const text = question.trim().slice(0, 300); if (!text) return;
    state.messages.push({ role: 'user', text }, { role: 'assistant', text: answer(text) });
    if (state.messages.length > 20) state.messages.splice(0, 2);
    render(); document.getElementById('question-input')?.focus();
  }
  function exportData() {
    let rows;
    if (state.page === 'people') rows = employeeRows();
    else if (state.page === 'inventory') rows = inventoryRows();
    else if (state.page === 'support') rows = data.support.filter(row => `${row.name}${row.account}`.includes(state.search));
    else if (state.page === 'projects') rows = projects;
    else rows = snapshot().filter(row => state.page !== 'reports' || shopName(row.shop_id).includes(state.search));
    if (!rows.length) return toast('当前筛选结果为空');
    const keys = Object.keys(rows[0]);
    const csvCell = value => { const text = String(value ?? ''); return '"' + (/^[=+@\-\t\r]/.test(text) ? "'" : '') + text.replaceAll('"', '""') + '"'; };
    const csv = '\ufeff' + [keys, ...rows.map(row => keys.map(key => typeof row[key] === 'object' ? JSON.stringify(row[key]) : row[key]))].map(row => row.map(csvCell).join(',')).join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = `test-${state.page}-${state.month}.csv`; document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000); toast(`已导出 ${rows.length} 条测试记录`);
  }
  const month = document.getElementById('month-filter');
  month.innerHTML = '<option value="all">2026 年 · 全部期间</option>' + [...data.months].reverse().map(value => `<option value="${value}">${value.replace('-', ' 年 ')} 月</option>`).join('');
  month.value = state.month;
  month.addEventListener('change', event => { state.month = event.target.value; render(); });
  document.getElementById('theme-toggle').addEventListener('click', () => { document.body.classList.toggle('dark'); storage.write('enterprise-demo-theme', document.body.classList.contains('dark') ? 'dark' : 'light'); });
  if (storage.read('enterprise-demo-theme') === 'dark') document.body.classList.add('dark');
  document.getElementById('export-button').addEventListener('click', exportData);
  function navigate() { state.page = Object.hasOwn(pages, location.hash.slice(1)) ? location.hash.slice(1) : 'overview'; state.search = ''; state.channel = ''; state.department = ''; state.stock = ''; render(); }
  window.addEventListener('hashchange', navigate); navigate();
})();
