from decimal import Decimal
from copy import deepcopy
import pytest
from app.engine import evaluate
from app.modules.split.rules import allocate, split_ticket, build_publication
from app.errors import BusinessError

@pytest.fixture
def split():
    return evaluate()['split']

def ticket(split, no):
    return next(t for t in split['tickets'] if t['ticket']==no)

def test_summary_real(split):
    assert split['summary']=={'tickets':5,'publishable':4,'households':8,'excluded':5}

def test_household_amounts_real(split):
    t=ticket(split,'00016')
    assert t['payable']=='1238.61' and t['provisional_total']=='1236.15' and t['difference']=='2.46'
    rows={h['household']:h for h in t['households']}
    assert rows['张海']['provisional']=='805.65' and rows['张海']['share']=='1.60' and rows['张海']['final']=='807.25'
    assert rows['李河']['provisional']=='430.50' and rows['李河']['share']=='0.86' and rows['李河']['final']=='431.36'
    assert rows['李河']['basis']=='P1603、P1604'

def test_full_coverage_every_ticket(split):
    for t in split['tickets']:
        if t['publishable']:
            assert sum(Decimal(h['final']) for h in t['households'])==Decimal(t['payable'])
            assert t['covered']

def test_missing_est_excluded(split):
    t=ticket(split,'00016')
    hit=[e for e in t['excluded'] if e['id']=='P1605']
    assert hit and hit[0]['code']=='MISSING_EST'
    assert all('P1605' not in h['basis'] for h in t['households'])

def test_returned_excluded(split):
    t=ticket(split,'00017')
    assert [e['code'] for e in t['excluded']]==['RETURNED']
    assert sum(Decimal(h['final']) for h in t['households'])==Decimal('1250.30')

def test_attribution_conflict_blocks_ticket(split):
    t=ticket(split,'00018')
    assert not t['publishable'] and t['block_code']=='NO_VALID_PACKAGES'
    assert [e['code'] for e in t['excluded']]==['ATTRIBUTION_CONFLICT','ATTRIBUTION_CONFLICT']

def test_tail_traceable_real(split):
    t=ticket(split,'00019')
    assert t['tail']=='0.01' and t['tail_household']=='王湾'
    rows={h['household']:h for h in t['households']}
    assert rows['王湾']['tail']=='0.01' and rows['王湾']['final']=='507.00'
    assert rows['张海']['tail']=='0.00' and rows['李河']['tail']=='0.00'

def test_duplicate_package_counted_once(split):
    assert split['counts']['duplicate']==1
    t=ticket(split,'00020')
    assert len(t['households'])==1 and t['households'][0]['packages']==1
    assert t['households'][0]['final']==t['payable']=='1285.35'

def test_orphan_unknown_ticket(split):
    assert [(o['id'],o['code']) for o in split['orphans']]==[('P9901','UNKNOWN_TICKET')]

def test_allocate_tail_to_largest():
    members=[{'household':n,'provisional':Decimal('100.00'),'weight':Decimal(10)} for n in 'abc']
    shares,tail,idx,mode=allocate(Decimal('300.01'),members)
    assert shares==[Decimal('0.00')]*3 and tail==Decimal('0.01') and idx==0
    assert sum(shares)+tail==Decimal('0.01')

def test_allocate_negative_diff_exact():
    members=[{'household':'a','provisional':Decimal('333.33'),'weight':Decimal(1)},
             {'household':'b','provisional':Decimal('666.67'),'weight':Decimal(2)}]
    shares,tail,idx,mode=allocate(Decimal('990.00'),members)
    assert sum(shares)+tail==Decimal('-10.00')
    assert idx==1

def test_allocate_zero_provisional_fallback():
    members=[{'household':'a','provisional':Decimal('0.00'),'weight':Decimal(3)},
             {'household':'b','provisional':Decimal('0.00'),'weight':Decimal(1)}]
    shares,tail,idx,mode=allocate(Decimal('100.00'),members)
    assert mode=='按估重比例分摊'
    assert sum(shares)+tail==Decimal('100.00')

def test_split_ticket_coverage_invariant():
    pkgs=[{'id':'X1','household':'甲','amount':'10.01','est_kg':'1','baskets':1,'line':2,'flag_label':'正常','price':'10.01'},
          {'id':'X2','household':'乙','amount':'20.02','est_kg':'2','baskets':1,'line':3,'flag_label':'正常','price':'10.01'}]
    result=split_ticket(Decimal('50.00'),pkgs)
    assert result['covered']
    assert sum(Decimal(h['final']) for h in result['households'])==Decimal('50.00')

def test_clean_split_all_covered(clean):
    s=clean['split']
    assert s['summary']['excluded']==0 and s['summary']['publishable']==2
    for t in s['tickets']:
        assert sum(Decimal(h['final']) for h in t['households'])==Decimal(t['payable'])

def test_legacy_split_empty():
    s=evaluate({'dataset':'legacy'})['split']
    assert s['summary']['tickets']==0 and s['tickets']==[]

def test_split_does_not_touch_ticket_balance(sample):
    assert sample['balance']['quarantined']==8 and sample['balance']['amount']=='23708.91'

def test_build_publication_blocked(sample):
    with pytest.raises(BusinessError) as error:
        build_publication(sample,'00018')
    assert error.value.code=='SPLIT_BLOCKED'

def test_build_publication_unknown(sample):
    with pytest.raises(BusinessError) as error:
        build_publication(sample,'00999')
    assert error.value.code=='UNKNOWN_REFERENCE'
