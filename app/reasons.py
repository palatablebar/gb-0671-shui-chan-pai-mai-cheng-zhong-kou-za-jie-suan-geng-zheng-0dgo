REASONS = {
    'COLUMN_COUNT':'列数错误', 'MISSING_ID':'编号缺失', 'DUPLICATE_CONFLICT':'重复编号冲突',
    'MISSING_VALUE':'数值缺失', 'BAD_NUMBER':'数值格式错误', 'BAD_TIME':'时间格式错误',
    'BAD_UNIT':'单位不受支持', 'UNKNOWN_REFERENCE':'引用对象不存在', 'INVALID_RANGE':'范围错误',
    'VERSION_CONFLICT':'版本冲突', 'EMPTY_FILE':'空文件', 'BLANK_FILE':'全空行',
    'HEADER_ONLY':'仅有表头', 'STALE_VERSION':'复核版本已更新', 'NOT_FOUND':'批次不存在',
    'MISSING_EST':'缺估重不进入可发布金额', 'ATTRIBUTION_CONFLICT':'归属冲突',
    'RETURNED':'整筐退运', 'UNKNOWN_TICKET':'车票号不存在或未生效', 'BLOCKED_TICKET':'车票被阻断',
    'NO_VALID_PACKAGES':'没有有效货包', 'BAD_FLAG':'货包类型无效', 'SPLIT_BLOCKED':'拆账被阻断',
    'COVERAGE_BROKEN':'户级合计未覆盖车票应付',
}
def reject(state, record, code, detail):
    state['quarantine'].append({'line':record.get('_line',0),'id':record.get('id',''),
       'code':code,'detail':detail,'raw':{k:v for k,v in record.items() if not k.startswith('_')}})
