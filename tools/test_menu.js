// 提取 MENUS 和 renderMenuItem 测试
const fs = require('fs');
const html = fs.readFileSync('C:/demo-project/frontend/public/ecommerce-dashboard.html', 'utf-8');

// 提取 MENUS 数组
const menusMatch = html.match(/let MENUS=(\[[\s\S]*?\]);\s*\n\s*const ROUTE_TO_MAIN/);
const menusStr = menusMatch[1];
eval('var MENUS = ' + menusStr);

console.log('MENUS[0]:', JSON.stringify(MENUS[0], null, 2));
console.log('hasKids:', !!(MENUS[0].children && MENUS[0].children.length));
console.log('children:', MENUS[0].children);
