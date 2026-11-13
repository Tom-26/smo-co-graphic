obs = obslua
local folder, source_name = '', ''
local source, handler = nil, nil
local copying, pending, clips, current, want_next, next_at = nil, {}, {}, '', false, 0
local warned = {}
local function log(msg) obs.script_log(obs.LOG_INFO, '[Highlights] '..msg) end
local function warn(msg) obs.script_log(obs.LOG_WARNING, '[Highlights] '..msg) end
local function once(key,msg) if not warned[key] then warned[key]=true; warn(msg) end end
local function join(dir,name) return dir:gsub('[\\/]+$','') .. '/' .. name end
local function video(name) local ext=name:match('%.([^%.]+)$'); return ext and ({mp4=true,mkv=true,mov=true,flv=true,ts=true,m3u8=false,webm=true})[ext:lower()] == true end

-- LuaJIT FFI: Windows directory scan uses Unicode Win32 APIs; never invokes a shell.
local win
local okffi, ffi = pcall(require,'ffi')
if okffi and ffi.os == 'Windows' then
  local ok, err = pcall(function()
    ffi.cdef[[
      typedef unsigned short SMO_WCHAR; typedef void* SMO_HANDLE; typedef unsigned long SMO_DWORD;
      typedef struct { SMO_DWORD dwLowDateTime; SMO_DWORD dwHighDateTime; } SMO_FILETIME;
      typedef struct { SMO_DWORD dwFileAttributes; SMO_FILETIME ftCreationTime, ftLastAccessTime, ftLastWriteTime; SMO_DWORD nFileSizeHigh, nFileSizeLow, dwReserved0, dwReserved1; SMO_WCHAR cFileName[260]; SMO_WCHAR cAlternateFileName[14]; } SMO_FIND_DATA;
      int MultiByteToWideChar(unsigned int, unsigned long, const char*, int, SMO_WCHAR*, int);
      int WideCharToMultiByte(unsigned int, unsigned long, const SMO_WCHAR*, int, char*, int, const char*, int*);
      SMO_HANDLE FindFirstFileW(const SMO_WCHAR*, SMO_FIND_DATA*);
      int FindNextFileW(SMO_HANDLE, SMO_FIND_DATA*); int FindClose(SMO_HANDLE);
      SMO_HANDLE CreateFileW(const SMO_WCHAR*, SMO_DWORD, SMO_DWORD, void*, SMO_DWORD, SMO_DWORD, SMO_HANDLE);
      int ReadFile(SMO_HANDLE, void*, SMO_DWORD, SMO_DWORD*, void*);
      int WriteFile(SMO_HANDLE, const void*, SMO_DWORD, SMO_DWORD*, void*);
      int CloseHandle(SMO_HANDLE); SMO_DWORD GetFileAttributesW(const SMO_WCHAR*);
      int MoveFileW(const SMO_WCHAR*, const SMO_WCHAR*); int DeleteFileW(const SMO_WCHAR*);
      SMO_DWORD GetLastError(void);
    ]]
    local k=ffi.load('kernel32')
    local function wide(s)
      local n=k.MultiByteToWideChar(65001,0,s,-1,nil,0);if n==0 then return nil end
      local w=ffi.new('SMO_WCHAR[?]',n); if k.MultiByteToWideChar(65001,0,s,-1,w,n)==0 then return nil end;return w
    end
    local function utf8(w)
      local n=k.WideCharToMultiByte(65001,0,w,-1,nil,0,nil,nil);if n==0 then return nil end
      local b=ffi.new('char[?]',n);if k.WideCharToMultiByte(65001,0,w,-1,b,n,nil,nil)==0 then return nil end;return ffi.string(b)
    end
    local invalid=ffi.cast('SMO_HANDLE',-1)
    local bit=require('bit')
    local function fail() return 'код Windows '..tonumber(k.GetLastError()) end
    local function openfile(path,write)
      local wp=wide(path);if not wp then return nil,'некорректный Unicode-путь' end
      local h=k.CreateFileW(wp,write and 0x40000000 or 0x80000000,write and 1 or 7,nil,write and 1 or 3,0x80,nil)
      if h==invalid then return nil,fail() end
      local f={handle=h}
      function f:read(n) local buf=ffi.new('char[?]',n);local count=ffi.new('SMO_DWORD[1]');if k.ReadFile(self.handle,buf,n,count,nil)==0 then return nil,fail() end;if count[0]==0 then return nil end;return ffi.string(buf,count[0]) end
      function f:write(data) local count=ffi.new('SMO_DWORD[1]');if k.WriteFile(self.handle,data,#data,count,nil)==0 or count[0]~=#data then return nil,fail() end;return true end
      function f:close() if self.handle==nil then return true end;local good=k.CloseHandle(self.handle)~=0;self.handle=nil;if not good then return nil,fail() end;return true end
      return f
    end
    win={wide=wide,k=k,open=openfile,exists=function(path)local w=wide(path);return w and k.GetFileAttributesW(w)~=0xffffffff end,
      remove=function(path)local w=wide(path);return w and k.DeleteFileW(w)~=0 end,
      rename=function(a,b)local wa,wb=wide(a),wide(b);if not wa or not wb then return nil,'Unicode' end;if k.MoveFileW(wa,wb)==0 then return nil,fail() end;return true end,
      scan=function(dir)
      local path=wide(join(dir,'*'));if not path then return nil,'Не удалось преобразовать путь в Unicode' end
      local entry=ffi.new('SMO_FIND_DATA[1]');local h=k.FindFirstFileW(path,entry)
      if h==ffi.cast('SMO_HANDLE',-1) then return nil,'Не удалось открыть папку' end
      local result={}
      repeat local name=utf8(entry[0].cFileName);if name and bit.band(tonumber(entry[0].dwFileAttributes),16)==0 and video(name) then result[#result+1]=join(dir,name) end until k.FindNextFileW(h,entry)==0
      k.FindClose(h);table.sort(result);return result
    end}
  end)
  if not ok then warn('Windows API недоступен: '..tostring(err));win=nil end
end

local function scan()
  if folder=='' then return {} end
  if win then local rows,err=win.scan(folder);if rows then return rows end;once('scan',err..': '..folder);return {} end
  local f=io.open(join(folder,'smo-highlights-index.txt'),'r'); if not f then return {} end
  local rows={};for name in f:lines() do if name:match('^smo_%d+_%d+%.[%w]+$') and video(name) then local path=join(folder,name);local x=io.open(path,'rb');if x then x:close();rows[#rows+1]=path end end end;f:close();table.sort(rows);return rows
end
local function append_index(name)
  if win then return end
  local f,err=io.open(join(folder,'smo-highlights-index.txt'),'a');if not f then warn('Не удалось обновить индекс: '..tostring(err));return end
  local ok,e=f:write(name..'\n');f:close();if not ok then warn('Не удалось записать индекс: '..tostring(e)) end
end
local function is_busy()
  if not source then return false end
  local v=obs.obs_source_media_get_state(source)
  return v==obs.OBS_MEDIA_STATE_PLAYING or v==obs.OBS_MEDIA_STATE_OPENING or v==obs.OBS_MEDIA_STATE_BUFFERING or v==obs.OBS_MEDIA_STATE_PAUSED
end
local function select_next()
  clips=scan();if #clips==0 then once('empty','Нет видео в папке повторов.');return end
  warned.empty=nil;local index=0;for i,path in ipairs(clips) do if path==current then index=i;break end end
  local path=clips[(index % #clips)+1]
  if not source or not obs.obs_source_active(source) or is_busy() then return end
  if path==current then obs.obs_source_media_restart(source);log('Повторное воспроизведение: '..path);return end
  local data=obs.obs_data_create();obs.obs_data_set_bool(data,'is_local_file',true);obs.obs_data_set_bool(data,'looping',false);obs.obs_data_set_string(data,'local_file',path);obs.obs_source_update(source,data);obs.obs_data_release(data)
  current=path;log('Воспроизведение: '..path)
end
local function media_ended() want_next=true;next_at=os.time() end
local function activated() if source and not is_busy() then want_next=true;next_at=os.time() end end
local function disconnect()
  if handler then obs.signal_handler_disconnect(handler,'media_ended',media_ended);obs.signal_handler_disconnect(handler,'activate',activated);handler=nil end
  if source then obs.obs_source_release(source);source=nil end
end
local function connect()
  disconnect();current='';want_next=false;if source_name=='' then return end
  source=obs.obs_get_source_by_name(source_name);if not source then once('source','Источник не найден: '..source_name);return end
  if obs.obs_source_get_id(source)~='ffmpeg_source' then warn('Нужен источник типа «Источник медиа»: '..source_name);obs.obs_source_release(source);source=nil;return end
  warned.source=nil;handler=obs.obs_source_get_signal_handler(source);obs.signal_handler_connect(handler,'media_ended',media_ended);obs.signal_handler_connect(handler,'activate',activated)
  if obs.obs_source_active(source) and not is_busy() then want_next=true;next_at=os.time() end
end
local function open_read(path) if win then return win.open(path,false) end;return io.open(path,'rb') end
local function open_write(path) if win then return win.open(path,true) end;return io.open(path,'wb') end
local function exists(path) if win then return win.exists(path) end;local f=io.open(path,'rb');if not f then return false end;f:close();return true end
local function remove(path) if win then return win.remove(path) end;return os.remove(path) end
local function rename(a,b) if win then return win.rename(a,b) end;return os.rename(a,b) end
local function start_copy(path)
  local ext=path:match('%.([^%.\\/]+)$');if not ext or not video(path) then warn('Формат повтора не поддерживается: '..path);return end
  local input,err=open_read(path);if not input then warn('Не удалось открыть повтор: '..tostring(err));return end
  local stamp=os.time();local n=1;local target,name
  repeat name=string.format('smo_%d_%04d.%s',stamp,n,ext:lower());target=join(folder,name);if not exists(target) and not exists(target..'.part') then break end;n=n+1 until n>9999
  if n>9999 then input:close();warn('Не удалось подобрать имя файла');return end
  local output,e=open_write(target..'.part');if not output then input:close();warn('Не удалось записать в папку: '..tostring(e));return end
  copying={input=input,output=output,target=target,part=target..'.part',name=name};log('Копируется повтор: '..path)
end
local function step_copy()
  if not copying then if #pending==0 then return end;start_copy(table.remove(pending,1));if not copying then return end end
  local c=copying;local chunk,read_error=c.input:read(1024*1024)
  if read_error then c.input:close();c.output:close();remove(c.part);copying=nil;warn('Ошибка чтения: '..tostring(read_error));return end
  if chunk then local ok,err=c.output:write(chunk);if not ok then c.input:close();c.output:close();remove(c.part);copying=nil;warn('Ошибка записи: '..tostring(err)) end;return end
  c.input:close();local ok,err=c.output:close();if not ok then remove(c.part);warn('Ошибка завершения копирования: '..tostring(err));copying=nil;return end
  local moved,e=rename(c.part,c.target);if not moved then warn('Не удалось завершить копирование: '..tostring(e));copying=nil;return end
  append_index(c.name);log('Повтор добавлен: '..c.target);copying=nil;clips=scan()
  if source and obs.obs_source_active(source) and not is_busy() then want_next=true;next_at=os.time() end
end
local function tick()
  step_copy()
  if want_next and os.time()>=next_at then want_next=false;select_next() end
end
local function event(e)
  if e==obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED then
    if folder=='' then warn('Выберите папку для повторов в настройках скрипта');return end
    if type(obs.obs_frontend_get_last_replay)~='function' then once('version','Требуется OBS Studio 29 или новее');return end
    local path=obs.obs_frontend_get_last_replay();if not path or path=='' then warn('OBS не сообщил путь сохранённого повтора');return end
    pending[#pending+1]=path
  end
end
function script_description() return 'Копирует сохранённые повторы и циклически воспроизводит их через отдельный источник медиа. OBS 29+.' end
function script_properties()
  local p=obs.obs_properties_create();obs.obs_properties_add_path(p,'folder','Папка для копий',obs.OBS_PATH_DIRECTORY,'',nil)
  local list=obs.obs_properties_add_list(p,'source','Источник медиа для нарезки',obs.OBS_COMBO_TYPE_LIST,obs.OBS_COMBO_FORMAT_STRING)
  obs.obs_property_list_add_string(list,'Выберите источник','');local sources=obs.obs_enum_sources();if sources then for _,s in ipairs(sources) do if obs.obs_source_get_id(s)=='ffmpeg_source' then local name=obs.obs_source_get_name(s);obs.obs_property_list_add_string(list,name,name) end end;obs.source_list_release(sources) end
  return p
end
function script_update(settings)
  local new_folder=obs.obs_data_get_string(settings,'folder') or '';local new_source=obs.obs_data_get_string(settings,'source') or ''
  if folder~=new_folder and (copying or #pending>0) then warn('Не меняйте папку во время копирования: ожидайте завершения.');return end
  local folder_changed=folder~=new_folder;folder=new_folder
  if source_name~=new_source or not source then source_name=new_source;connect()
  elseif folder_changed and source and obs.obs_source_active(source) and not is_busy() then want_next=true;next_at=os.time() end
end
function script_load(settings) obs.obs_frontend_add_event_callback(event);obs.timer_add(tick,40) end
function script_unload() obs.timer_remove(tick);obs.obs_frontend_remove_event_callback(event);disconnect();if copying then copying.input:close();copying.output:close();remove(copying.part);copying=nil end end
