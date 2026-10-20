<script setup lang="ts">
import { ElButton, ElDatePicker, ElInput, ElSelect, ElOption } from 'element-plus'
import type { OperatingFilters, OperatingData } from './operatingCharts'
const model = defineModel<OperatingFilters>({ required: true })
defineProps<{ meta: OperatingData; loading: boolean; showMetric?: boolean }>()
defineEmits<{ query: []; reset: [] }>()
</script>

<template>
  <form class="filter-form" @submit.prevent="$emit('query')">
    <label class="period"><span>查询日期</span><el-date-picker v-model="model.range" type="daterange" value-format="YYYY-MM-DD" :clearable="false" start-placeholder="开始日期" end-placeholder="结束日期" /></label>
    <label><span>品牌</span><el-select v-model="model.brand" clearable filterable placeholder="全部品牌" aria-label="品牌筛选"><el-option v-for="b in meta.brands || []" :key="b" :label="b" :value="b" /></el-select></label>
    <label class="keyword"><span>商品查询</span><el-input v-model="model.keyword" clearable placeholder="SKU / 货号 / 商品名称" aria-label="商品筛选" /></label>
    <label v-if="showMetric"><span>图表指标</span><el-select v-model="model.metric" aria-label="图表指标"><el-option v-for="(name, key) in meta.metrics" :key="key" :label="String(name)" :value="key" /></el-select></label>
    <div class="actions"><el-button @click="$emit('reset')">重置</el-button></div>
  </form>
</template>

<style scoped>
.filter-form{display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap}.filter-form label{display:flex;flex-direction:column;gap:8px;flex:1;min-width:145px}.filter-form label>span{font-size:12px;color:light-dark(#64748b, var(--text-secondary))}.filter-form .period{flex:2;min-width:300px}.filter-form .keyword{flex:1.5;min-width:205px}.period :deep(.el-date-editor){width:100%;box-sizing:border-box}.actions{display:flex;gap:8px}.actions .el-button+.el-button{margin-left:0}
</style>
