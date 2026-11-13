local calls, callbacks, responses, loaded, warnings = {}, {}, {}, {}, {}
obslua = {
 LOG_WARNING=1, LOG_INFO=2,
 obs_data_create_from_json=function(raw) return {raw=raw,token=raw:match('"token":"([^"]+)"'),running=raw:find('"running":true')~=nil} end,
 obs_data_get_string=function(d,k) return d[k] or '' end,
 obs_data_get_bool=function(d,k) return d[k] or false end,
 obs_data_get_int=function(d,k) return d[k] or 8765 end,
 obs_data_release=function() end,
 obs_hotkey_register_frontend=function(name,title,cb) callbacks[name]=cb; return name end,
 obs_data_get_array=function(d,k) return d.raw or d[k] end,
 obs_hotkey_load=function(id,a) loaded[id]=a end,
 obs_data_array_release=function() end,
 script_log=function(level,msg) warnings[#warnings+1]=msg end,
 obs_hotkey_save=function(id) return {id} end,
 obs_data_set_array=function(d,k,a) d[k]=a end,
 obs_data_set_bool=function(d,k,v) d[k]=v end,
 obs_hotkey_unregister=function() end
}
io.popen=function(cmd)
 calls[#calls+1]=cmd
 return {read=function() return table.remove(responses,1) or error('Unexpected HTTP request') end,close=function() end}
end
dofile(arg[1])
script_load({port=8765})
assert(loaded['smo.home_plus']:find('"control":true'))
responses={'{"token":"abc"}\n200','{}\n200'}
callbacks['smo.home_plus'](true)
assert(calls[2]:find('"side":"home","delta":1',1,true))
callbacks['smo.home_plus'](true)
assert(#calls==2,'Held key must not repeat')
callbacks['smo.home_plus'](false)
responses={'{"running":true}\n200','{}\n200'}
callbacks['smo.clock'](true)
assert(calls[#calls]:find('"action":"pause"',1,true))
callbacks['smo.clock'](false)
responses={'{"running":false}\n200','{}\n200'}
callbacks['smo.clock'](true)
assert(calls[#calls]:find('"action":"start"',1,true))
responses={'{}\n403','{"token":"new"}\n200','{}\n200'}
callbacks['smo.away_plus'](true)
assert(calls[#calls]:find('X-Scoreboard-Token: new',1,true))
local id_before=calls[#calls-2]:match('"id":"([^"]+)"')
assert(id_before==calls[#calls]:match('"id":"([^"]+)"'),'Auth retry uses same ID')
responses={'\n000'}
callbacks['smo.away_minus'](true)
assert(#warnings==1,'Missing server reports error without retry')
local settings={}
script_save(settings)
assert(settings.bindings_saved)
script_unload()
print('PASS: default global bindings, score command, clock toggle, held keys, token renewal, ambiguous failure, saved bindings')
