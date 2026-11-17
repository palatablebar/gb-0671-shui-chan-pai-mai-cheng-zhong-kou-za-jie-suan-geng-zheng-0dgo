import csv, io
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from app.coerce import number, money
from app.config import SENTINELS
from app.errors import BusinessError

FIELDS=['id','ticket','household','baskets','est_kg','price','flag']
FLAGS={'正常':'normal','补筐':'supplement','退运':'returned','normal':'normal','supplement':'supplement','returned':'returned'}
FLAG_LABELS={'normal':'正常','supplement':'补筐','returned':'退运'}
CENT=Decimal('.01')

def exclude(row, code, detail):
    return {'line':row.get('_line',0),'id':row.get('id',''),'ticket':row.get('ticket','').strip(),
            'household':row.get('household','').strip(),'code':code,'detail':detail,
            'raw':{k:v for k,v in row.items() if not k.startswith('_')}}

def read_packages(raw):
    """解析拼车货包CSV。所有问题行转为排除证据，不丢弃任何原始记录。"""
    text=None
    for encoding in ('utf-8-sig','gb18030'):
        try: text=raw.decode(encoding);break
        except UnicodeDecodeError: continue
    if text is None: raise BusinessError('BAD_ENCODING','拼车货包文件编码无法识别')
    counts={'input':0,'blank':0,'repeated_header':0,'duplicate':0}
    if not text.strip(): return [],[],counts
    stream=csv.reader(io.StringIO(text,newline=''),strict=True)
    try:
        original=next(stream,None)
        if original is None: return [],[],counts
        if [v.strip() for v in original]!=FIELDS: raise BusinessError('BAD_HEADER','拼车货包字段或顺序不匹配')
        rows=[];excluded=[]
        for cells in stream:
            line=stream.line_num
            counts['input']+=1
            if not cells or not any(v.strip() for v in cells): counts['blank']+=1;continue
            if cells==original: counts['repeated_header']+=1;continue
            row=dict(zip(FIELDS,cells));row['_line']=line
            if len(cells)!=len(FIELDS):
                excluded.append(exclude(row,'COLUMN_COUNT',f'需要{len(FIELDS)}列，实际{len(cells)}列'));continue
            if not row.get('id','').strip():
                excluded.append(exclude(row,'MISSING_ID','货包编号不能为空'));continue
            row['id']=row['id'].strip();rows.append(row)
    except csv.Error:
        raise BusinessError('BROKEN_CSV','拼车货包CSV引号或末行损坏')
    by_id=defaultdict(list)
    for row in rows: by_id[row['id']].append(row)
    unique=[]
    for pid,group in by_id.items():
        identities={tuple((k,v) for k,v in r.items() if k!='_line') for r in group}
        if len(identities)>1:
            for r in group: excluded.append(exclude(r,'ATTRIBUTION_CONFLICT','同一货包编号归属不同，全部排除，不进入可发布金额'))
        else:
            unique.append(group[0]);counts['duplicate']+=len(group)-1
    return unique,excluded,counts

def validate(pkg, known_tickets, blocked_tickets):
    """返回 (有效货包, None) 或 (None, 排除证据)。缺估重、归属冲突、退运、票未生效均不进入可发布金额。"""
    flag=FLAGS.get(pkg.get('flag','').strip())
    if flag is None: return None,exclude(pkg,'BAD_FLAG','货包类型须为 正常/补筐/退运')
    if flag=='returned': return None,exclude(pkg,'RETURNED','整筐退运，不进入可发布金额')
    ticket=pkg.get('ticket','').strip()
    if not ticket: return None,exclude(pkg,'MISSING_VALUE','票号缺失')
    if ticket in blocked_tickets: return None,exclude(pkg,'BLOCKED_TICKET','车票在上游被阻断，无生效应付')
    if ticket not in known_tickets: return None,exclude(pkg,'UNKNOWN_TICKET','车票号不存在或未生效')
    household=pkg.get('household','').strip()
    if not household: return None,exclude(pkg,'MISSING_VALUE','户名缺失')
    est_text=pkg.get('est_kg','').strip()
    if est_text.upper() in SENTINELS or est_text in SENTINELS:
        return None,exclude(pkg,'MISSING_EST','缺估重，不进入可发布金额')
    try:
        est=number(est_text)
        if est<=0: raise BusinessError('INVALID_RANGE','估重须为正数')
        price=number(pkg['price'])
        if price<0: raise BusinessError('INVALID_RANGE','单价须非负')
        baskets=number(pkg['baskets'])
        if baskets<0 or baskets%1: raise BusinessError('INVALID_RANGE','筐数须为非负整数')
    except BusinessError as error:
        return None,exclude(pkg,error.code,error.message)
    return {'id':pkg['id'],'ticket':ticket,'household':household,'baskets':int(baskets),
            'est_kg':format(est,'f'),'price':format(price,'f'),'flag':flag,'flag_label':FLAG_LABELS[flag],
            'line':pkg['_line'],'amount':money(est*price)},None

def allocate(payable, members):
    """把 车票应付-暂计合计 的差额按暂计金额比例分摊到户，尾差落给份额最大的户。
    返回 (分摊列表, 尾差, 尾差户索引, 分摊方式)，保证 暂计+分摊+尾差 的合计恰好等于车票应付。"""
    total=sum((m['provisional'] for m in members),Decimal(0))
    diff=payable-total
    if total>0: basis,mode=[m['provisional'] for m in members],'按暂计金额比例分摊'
    elif sum((m['weight'] for m in members),Decimal(0))>0: basis,mode=[m['weight'] for m in members],'按估重比例分摊'
    else: basis,mode=[Decimal(1)]*len(members),'按户均摊'
    btotal=sum(basis)
    shares=[(diff*b/btotal).quantize(CENT,rounding=ROUND_HALF_UP) for b in basis]
    shares=[s if s else Decimal('0.00') for s in shares]
    tail=diff-sum(shares,Decimal(0))
    tail=tail if tail else Decimal('0.00')
    idx=max(range(len(members)),key=lambda i:basis[i]) if members else 0
    return shares,tail,idx,mode

def split_ticket(payable, packages):
    members={}
    for p in packages:
        m=members.setdefault(p['household'],{'household':p['household'],'provisional':Decimal(0),'weight':Decimal(0),'baskets':0,'evidence':[]})
        m['provisional']+=Decimal(p['amount']);m['weight']+=Decimal(p['est_kg']);m['baskets']+=p['baskets']
        m['evidence'].append({'id':p['id'],'line':p['line'],'flag':p['flag_label'],'est_kg':p['est_kg'],'price':p['price'],'amount':p['amount']})
    ordered=[members[name] for name in sorted(members)]
    shares,tail,tail_idx,mode=allocate(payable,ordered)
    households=[]
    for i,m in enumerate(ordered):
        final=m['provisional']+shares[i]+(tail if i==tail_idx else Decimal(0))
        households.append({'household':m['household'],'packages':len(m['evidence']),'baskets':m['baskets'],
            'est_kg':format(m['weight'],'f'),'provisional':money(m['provisional']),'share':money(shares[i]),
            'tail':money(tail) if i==tail_idx else '0.00','final':money(final),
            'basis':'、'.join(e['id'] for e in m['evidence']),'evidence':m['evidence']})
    provisional_total=sum((m['provisional'] for m in ordered),Decimal(0))
    covered=sum((Decimal(h['final']) for h in households),Decimal(0))==payable
    return {'households':households,'covered':covered,'mode':mode,
            'provisional_total':money(provisional_total),'difference':money(payable-provisional_total),
            'tail':money(tail),'tail_household':ordered[tail_idx]['household'] if ordered and tail else ''}

def apply(state):
    raw=state.get('split_raw')
    final_by_ticket={r['ticket']:r for r in state.get('final',[])}
    blocked={c['ticket'] for c in state.get('version_conflicts',[])}
    tickets=[];orphans=[];all_excluded=[];counts={'input':0,'blank':0,'repeated_header':0,'duplicate':0}
    if raw:
        packages,excluded,counts=read_packages(raw)
        all_excluded.extend(excluded)
        grouped=defaultdict(list)
        for pkg in packages:
            normalized,problem=validate(pkg,final_by_ticket,blocked)
            if problem: all_excluded.append(problem)
            else: grouped[normalized['ticket']].append(normalized)
        touched=set(grouped)|{e['ticket'] for e in all_excluded if e['ticket'] in final_by_ticket}
        for ticket in sorted(touched):
            payable=Decimal(final_by_ticket[ticket]['amount'])
            entry={'ticket':ticket,'payable':money(payable)}
            if grouped.get(ticket):
                entry.update(split_ticket(payable,grouped[ticket]))
                entry['publishable']=entry['covered']
                entry['block_code']='' if entry['covered'] else 'COVERAGE_BROKEN'
                entry['block_detail']='' if entry['covered'] else '户级合计未覆盖车票应付'
            else:
                entry.update({'households':[],'covered':False,'publishable':False,'mode':'',
                    'provisional_total':'0.00','difference':money(payable),'tail':'0.00','tail_household':'',
                    'block_code':'NO_VALID_PACKAGES','block_detail':'没有有效货包，不可发布'})
            entry['excluded']=[e for e in all_excluded if e['ticket']==ticket]
            tickets.append(entry)
        orphans=[e for e in all_excluded if e['ticket'] not in final_by_ticket]
    summary={'tickets':len(tickets),'publishable':sum(1 for t in tickets if t['publishable']),
             'households':sum(len(t['households']) for t in tickets),'excluded':len(all_excluded)}
    state['split']={'tickets':tickets,'orphans':orphans,'excluded':all_excluded,'counts':counts,'summary':summary}
    state['views']['split']={'title':'拼车拆账','rows':tickets,'orphans':orphans,'excluded':all_excluded,
        'metrics':{'拼车票':summary['tickets'],'可发布':summary['publishable'],'户级结果':summary['households'],'排除货包':summary['excluded']}}

def build_publication(result, ticket):
    """从批次结果中取出可发布的户级结算。不可发布时抛错，调用方保留旧版。"""
    split=result.get('split') or {}
    entry=next((t for t in split.get('tickets',[]) if t['ticket']==ticket),None)
    if entry is None: raise BusinessError('UNKNOWN_REFERENCE','该票没有拼车货包，不能发布')
    if not entry.get('publishable'): raise BusinessError('SPLIT_BLOCKED',entry.get('block_detail') or '该票暂不可发布')
    total=sum((Decimal(h['final']) for h in entry['households']),Decimal(0))
    if total!=Decimal(entry['payable']): raise BusinessError('COVERAGE_BROKEN','户级合计未覆盖车票应付，禁止发布')
    return {'run_id':result['manifest']['run_id'],'rule_version':result['manifest']['rule_version'],
        'payable':entry['payable'],'provisional_total':entry['provisional_total'],'difference':entry['difference'],
        'tail':entry['tail'],'tail_household':entry['tail_household'],'mode':entry['mode'],
        'households':[{'household':h['household'],'provisional':h['provisional'],'share':h['share'],'tail':h['tail'],
                       'final':h['final'],'packages':[e['id'] for e in h['evidence']]} for h in entry['households']],
        'excluded':[{'id':e['id'],'code':e['code']} for e in entry['excluded']]}

def signed(value):
    text=money(value)
    return '+'+text if value>0 else text

def diff_publications(previous, current):
    """逐户对比两版发布内容，发布影响留痕。"""
    old={h['household']:h['final'] for h in (previous or {}).get('households',[])}
    new={h['household']:h['final'] for h in current['households']}
    rows=[]
    for name in sorted(set(old)|set(new)):
        delta=Decimal(new.get(name,'0.00'))-Decimal(old.get(name,'0.00'))
        rows.append({'household':name,'previous':old.get(name,''),'current':new.get(name,''),'delta':signed(delta)})
    payable_delta=Decimal(current['payable'])-Decimal((previous or {}).get('payable','0.00'))
    return {'payable_delta':signed(payable_delta),'households':rows}
