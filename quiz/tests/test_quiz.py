import importlib.util, json, tempfile, threading, unittest, urllib.request
from pathlib import Path

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('quiz_server',root/'server.py')
quiz=importlib.util.module_from_spec(spec);spec.loader.exec_module(quiz)

class QuizTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();quiz.STATE=Path(self.tmp.name)/'quiz.json'
        quiz.state={'questions':[], 'index':0, 'selected':-1, 'revealed':False,'visible':False,'revision':0}
    def tearDown(self): self.tmp.cleanup()
    def test_selection_reveal_and_roundtrip(self):
        quiz.update({'action':'save','value':{'index':None,'question':{'title':'Вопрос','options':['Первый','Второй'],'correct':1}}})
        quiz.update({'action':'visible','value':True}); quiz.update({'action':'select','value':0}); quiz.update({'action':'reveal'})
        s=quiz.validate(json.loads(quiz.STATE.read_text()))
        self.assertEqual((s['selected'],s['revealed'],s['questions'][0]['correct'],s['visible']),(0,True,1,True))
        with self.assertRaises(ValueError): quiz.update({'action':'select','value':1})
        quiz.update({'action':'reset'}); self.assertEqual(quiz.state['selected'],-1)
    def test_validation_rollback(self):
        with self.assertRaises(ValueError): quiz.update({'action':'save','value':{'index':None,'question':{'title':'Вопрос','options':['Один'],'correct':0}}})
        self.assertEqual(quiz.state['questions'],[])
    def test_http_session_and_overlay(self):
        server=quiz.Server(('127.0.0.1',0),quiz.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            with urllib.request.urlopen(base+'/overlay.html') as response: self.assertIn('ХОККЕЙНЫЙ КВИЗ',response.read().decode())
            with urllib.request.urlopen(base+'/api/session') as response: token=json.load(response)['token']
            body=json.dumps({'action':'save','value':{'index':None,'question':{'title':'Тест','options':['А','Б'],'correct':0}}}).encode()
            request=urllib.request.Request(base+'/api/command',data=body,headers={'Content-Type':'application/json','X-Quiz-Token':token})
            with urllib.request.urlopen(request) as response: self.assertEqual(json.load(response)['questions'][0]['title'],'Тест')
        finally: server.shutdown();server.server_close();thread.join()
if __name__=='__main__': unittest.main()
