"""Check real session state transitions without contacting Ring or reading credentials."""
import json,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from server import Hub

starts=[];closes=[];active=set();max_active=0;fail=False
class FakeFeed:
    def __init__(self,source):
        global max_active
        self.source=source;starts.append(source);active.add(id(self));max_active=max(max_active,len(active))
    def next_frame(self):
        time.sleep(.02)
        if fail:raise ConnectionError('Ring test interruption')
        return b'fixture'
    def close(self):active.remove(id(self));closes.append(self.source)
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
def wait(check):
    deadline=time.monotonic()+3
    while not check():
        assert time.monotonic()<deadline,'Timed out'
        time.sleep(.02)
with tempfile.TemporaryDirectory() as temp:
    settings=Path(temp)/'hub.json';settings.write_text(json.dumps({'source':'ring_side','detection':True}))
    with patch('server.RingFeed',FakeFeed),patch.object(Hub,'detect_loop',lambda self:None):
        hub=Hub({},settings,Path('unused'))
        assert hub.snapshot()['ring']['selected'] and not hub.snapshot()['ring']['active']
        time.sleep(.1);assert not starts,'A restart must not start Ring without a user action'
        hub.control({'ring_action':'start'});wait(lambda:hub.frame_id>0)
        assert len(starts)==1
        for _ in range(8):hub.snapshot();hub.get_frame(-1)
        assert len(starts)==1,'All viewers share the same Ring connection'
        generation=hub.ring_generation
        hub.control({'detection':False});assert hub.ring_generation==generation
        hub.control({'detection':True});assert hub.ring_generation==generation
        hub.control({'source':'ring_back'});hub.snapshot();wait(lambda:starts[-1]=='ring_back')
        hub.control({'source':'ring_side'});hub.control({'source':'ring_front'});hub.snapshot()
        wait(lambda:starts[-1]=='ring_front')
        assert hub.snapshot()['ring']['session_seconds']==120
        hub.control({'ring_action':'stop'});wait(lambda:not active)
        s=hub.snapshot();assert not s['ring']['active'] and not s['live'] and not s['people'] and not s['vehicles']
        count=len(starts)
        for _ in range(5):hub.snapshot();time.sleep(.05)
        assert len(starts)==count,'Polling must not restart stopped Ring sessions'
        hub.control({'ring_action':'start'});hub.snapshot();wait(lambda:len(starts)>count)
        with hub.condition:hub.ring_deadline=time.monotonic()-1
        assert not hub.snapshot()['ring']['active'];wait(lambda:not active)
        count=len(starts);hub.control({'ring_action':'start'});hub.snapshot();wait(lambda:len(starts)>count)
        with hub.condition:hub.last_view=time.monotonic()-7
        wait(lambda:not active);assert not hub.ring_active
        count=len(starts);hub.control({'ring_action':'start'});hub.snapshot();wait(lambda:len(starts)>count)
        fail=True;wait(lambda:not active and not hub.ring_active);fail=False
        count=len(starts)
        for _ in range(5):hub.snapshot();time.sleep(.05)
        assert len(starts)==count,'Errors must not cause endless Ring stream renewals'
        hub.control({'source':'phone'})
        try:hub.control({'ring_action':'start'})
        except ValueError:pass
        else:raise AssertionError('Ring actions must require a Ring camera')
        for action in ('restart',True,[],None):
            try:hub.control({'ring_action':action})
            except ValueError:pass
            else:raise AssertionError('Invalid Ring action accepted')
        assert max_active==1
        assert len(starts)==len(closes)
result={'passed':True,'shared_single_stream':True,'restart_requires_start':True,'detection_toggle_preserves_stream':True,'source_switch_closes_old_stream':True,'stop_expiry_idle_error_clear_and_stop':True,'no_automatic_renewal':True,'front_door_limit_seconds':120,'all_feed_instances_closed':len(closes)}
print(json.dumps(result,indent=2))
