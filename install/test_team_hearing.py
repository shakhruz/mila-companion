#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TEAM-HEARING-1006: ворота кормильца — кому из ботов подаём сообщение. python3 install/test_team_hearing.py"""
import importlib.util, sys
import os
spec=importlib.util.spec_from_file_location('f',os.path.join(os.path.dirname(os.path.abspath(__file__)),'companion-feeder.py'))
f=importlib.util.module_from_spec(spec); spec.loader.exec_module(f)
f.log=lambda *a:None
OWN='milak_content_bot'; OURS={'milak_traffic_bot','milak_content_bot','safi_admin_bot'}
def g(user,txt='x',reply=None,chat='-1'):
    m={'user':user,'chat_id':chat}
    if reply: m['reply_to_user']=reply
    return f.gate_message({'content':txt},m,OWN,OURS)
assert g('shakhruz')                                   # человек
assert not g('milak_traffic_bot','привет всем')        # бот не адресован
assert g('milak_traffic_bot','@Milak_Content_Bot глянь')   # упоминание
assert g('milak_traffic_bot','ответ',reply='milak_content_bot',chat='-2')  # reply
assert not g('random_bot','@milak_content_bot hi')     # чужой бот
assert not g('milak_content_bot','@milak_content_bot') # сам себе
f._pair_hits.clear()
r=[g('milak_traffic_bot','@milak_content_bot') for _ in range(22)]
assert r==[True]*20+[False]*2, r
f._pair_hits.clear(); import os; os.environ['COMPANION_BOT_PAIR_MAX']='2'
assert [g('milak_traffic_bot','@milak_content_bot') for _ in range(3)]==[True,True,False]
e=f.envelope({'content':'t'},{'chat_id':1,'message_id':2,'user':'a_bot','reply_quote':'я'*2500})
assert 'я'*2500 in e
print('ALL OK')
