# -*- coding: utf-8 -*-
"""ห้องอัดเสียงครู — โคลนเสียงของครูมาพากย์คู่มือ guide.html (ทำงานในเครื่องทั้งหมด ไม่ส่งเสียงออกไปไหน)

    python tools/voice_studio/studio.py          เปิดที่ http://127.0.0.1:8765

ลำดับงานในหน้าเว็บ
  1. อัดตัวอย่างเสียง — อ่านประโยคที่กำหนด 5–8 วินาที ระบบวัดเสียงดัง/เสียงรบกวน/เสียงแตกให้
  2. ทดลองโคลน — พิมพ์ข้อความอะไรก็ได้ ฟังเทียบ ปรับความเร็ว เลือกตัวอย่างเสียงที่ดีที่สุด
  3. อัดคู่มือทั้งชุด — สร้างทุกประโยคในบทพากย์ ฟังทีละประโยค สร้างใหม่ หรืออัดด้วยเสียงจริงแทนก็ได้
  4. เผยแพร่ — ประโยคที่ผ่านแล้วถูกคัดลอกไป guide-audio/ เป็นเสียงชุด "self" ในคู่มือ

ที่เก็บ
  ตัวอย่างเสียงต้นฉบับ + งานร่าง: D:\\KruSpace\\ข้อมูล\\เสียงครู\\  (นอก git — ห้ามขึ้น GitHub เด็ดขาด
    เพราะรีโพเป็นสาธารณะ ใครได้ไฟล์ตัวอย่างไปก็โคลนเสียงครูได้)
  ไฟล์ที่เผยแพร่: app\\guide-audio\\self-*.mp3 (เฉพาะเสียงที่สร้างแล้ว ไม่มีตัวอย่างต้นฉบับ)
"""
import base64, hashlib, http.server, io, json, os, re, shutil, subprocess, sys, threading, time, urllib.parse, webbrowser

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, '..', '..'))
ROOT = os.path.dirname(APP)
DATA = os.environ.get('KRU_VOICE_DATA', os.path.join(ROOT, 'ข้อมูล', 'เสียงครู'))
ENGINE = os.environ.get('KRU_VOICE_ENGINE', os.path.join(ROOT, 'voice-engine'))
VPY = os.path.join(ENGINE, '.venv', 'Scripts' if os.name == 'nt' else 'bin', 'python.exe' if os.name == 'nt' else 'python')
SCRIPT = os.path.join(APP, 'tools', 'guide_voice', 'script.json')
AUDIO = os.environ.get('KRU_VOICE_AUDIO', os.path.join(APP, 'guide-audio'))   # เปลี่ยนได้ตอนทดสอบ ไม่ให้แตะไฟล์จริง
PORT = int(os.environ.get('KRU_VOICE_PORT', '8765'))
STATE = os.path.join(DATA, 'studio.json')
VOICE_KEY = 'self'

# ประโยคสำหรับอัดตัวอย่างเสียง — มีสระ วรรณยุกต์ และพยัญชนะควบกล้ำครบ ยาวพออ่านได้ 5–8 วินาที
# น้ำเสียงเหมือนตอนสอน ตัวอย่างเสียงแบบไหน เสียงที่โคลนออกมาก็แบบนั้น
READING = [
    'สวัสดีครับนักเรียนทุกคน วันนี้เราจะมาเรียนเรื่องใหม่กัน ตั้งใจฟังให้ดีนะ',
    'ก่อนเริ่มเรียน ครูขอเช็กชื่อก่อน ใครยังไม่มา ให้เพื่อนช่วยบอกครูด้วย',
    'งานชิ้นนี้ส่งภายในวันศุกร์หน้า ถ้ามีข้อสงสัยตรงไหน ถามครูได้ตลอดเวลา',
    'เปิดแอปครูสเปซ เลือกห้องเรียนและรายวิชา แล้วกดบันทึกคะแนนได้เลย',
    'ผลการเรียนภาคนี้ดีขึ้นมาก ครูภูมิใจในความพยายามของทุกคนจริง ๆ',
    'ถ้าคะแนนเก็บยังไม่ครบ ระบบจะเตือนเป็นสีแดง ให้ตรวจก่อนส่งผลการเรียน',
    'การทดลองวันนี้ ให้แบ่งกลุ่มละห้าคน ช่วยกันจดบันทึกผลอย่างละเอียด',
    'เรียนจบบทนี้แล้ว กลับไปทบทวนที่บ้าน สัปดาห์หน้าจะมีสอบย่อยสั้น ๆ',
]
DEFAULTS = {'label': 'เสียงครู (AI)', 'ref_id': '', 'engine': 'f5', 'model': 'v1', 'speed': 1.0, 'cfg': 2.0, 'step': 32, 'seed': 7}

lock = threading.RLock()
os.makedirs(os.path.join(DATA, 'refs'), exist_ok=True)
os.makedirs(os.path.join(DATA, 'lines'), exist_ok=True)
os.makedirs(os.path.join(DATA, 'trials'), exist_ok=True)


def load_state():
    try:
        s = json.load(io.open(STATE, encoding='utf-8'))
    except Exception:
        s = {}
    s.setdefault('settings', {}); s.setdefault('refs', []); s.setdefault('lines', {}); s.setdefault('published', {})
    for k, v in DEFAULTS.items():
        s['settings'].setdefault(k, v)
    return s


def save_state():
    tmp = STATE + '.part'
    io.open(tmp, 'w', encoding='utf-8').write(json.dumps(state, ensure_ascii=False, indent=1))
    os.replace(tmp, STATE)


state = load_state()
batch = {'running': False, 'done': 0, 'total': 0, 'current': '', 'errors': [], 'stop': False}


def script_lines():
    d = json.load(io.open(SCRIPT, encoding='utf-8'))
    return [{'key': k, 'plain': v['plain'], 'say': v['say']} for k, v in d.items() if not k.startswith('_')]


def say_hash(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:10]


# ---------------------------------------------------------------- เครื่องยนต์เสียง (โปรเซสลูกค้างไว้)
class Engine:
    def __init__(self):
        self.p = None; self.n = 0; self.info = {}; self.lock = threading.Lock()

    def python(self):
        return VPY if os.path.exists(VPY) else sys.executable   # ยังไม่ติดตั้ง venv = ใช้ได้แค่เสียงทดสอบ

    def start(self):
        if self.p and self.p.poll() is None:
            return
        self.p = subprocess.Popen([self.python(), '-u', os.path.join(HERE, 'engine_worker.py')], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=open(os.path.join(DATA, 'engine.log'), 'a', encoding='utf-8'),
                                  text=True, encoding='utf-8', bufsize=1)
        self.p.stdout.readline()                                  # บรรทัด ready

    def call(self, req, timeout=600):
        with self.lock:
            self.start()
            self.n += 1; req['id'] = self.n
            self.p.stdin.write(json.dumps(req, ensure_ascii=False) + '\n'); self.p.stdin.flush()
            t0 = time.time()
            while True:
                line = self.p.stdout.readline()
                if not line:
                    self.p = None
                    raise RuntimeError('เครื่องยนต์เสียงหยุดทำงาน ดู %s' % os.path.join(DATA, 'engine.log'))
                try:
                    res = json.loads(line)
                except ValueError:
                    continue                                       # ข้อความพิมพ์ปนจากไลบรารี ข้ามไป
                if res.get('id') == req['id']:
                    if not res.get('ok'):
                        raise RuntimeError(res.get('error') or 'สร้างเสียงไม่สำเร็จ')
                    return res
                if time.time() - t0 > timeout:
                    raise RuntimeError('รอนานเกินไป')

    def ping(self):
        try:
            self.info = self.call({'op': 'ping'}, 120)
        except Exception as e:
            self.info = {'ok': False, 'error': str(e)}
        self.info['venv'] = os.path.exists(VPY)
        return self.info


engine = Engine()


def ref_by_id(rid):
    return next((r for r in state['refs'] if r['id'] == rid), None)


def generate(text, out, seed=None, engine_name=None):
    st = state['settings']
    eng = engine_name or st['engine']
    if eng == 'f5':
        ref = ref_by_id(st['ref_id'])
        if not ref:
            raise RuntimeError('ยังไม่ได้เลือกตัวอย่างเสียง — อัดและเลือกในขั้นที่ 1 ก่อน')
        req = {'op': 'gen', 'engine': 'f5', 'model': st['model'], 'ref_audio': os.path.join(DATA, 'refs', ref['file']),
               'ref_text': ref['text'], 'text': text, 'speed': st['speed'], 'cfg': st['cfg'], 'step': st['step'],
               'seed': st['seed'] if seed is None else seed, 'out': out}
    else:
        req = {'op': 'gen', 'engine': 'preview', 'text': text, 'out': out}
    return engine.call(req)


# บทพากย์เขียนคำอังกฤษเป็นอักษรอังกฤษ (ให้เสียง Edge อ่านแบบที่คนพูดจริง) แต่ F5-TTS-THAI เทรนด้วยข้อความไทย
# อ่านอักษรอังกฤษเพี้ยน จึงแปลงเป็นคำอ่านไทยก่อนสร้างเสียงครู — เพิ่มคำใหม่ที่นี่เมื่อบทพากย์มีคำอังกฤษเพิ่ม
CLONE_TH = [('Google Sheet', 'กูเกิล ชีต'), ('KruSpace', 'ครูสเปซ'), ('Google', 'กูเกิล'), ('Excel', 'เอ็กเซล'), ('Chrome', 'โครม'),
            ('SGS', 'เอส จี เอส'), ('CSV', 'ซี เอส วี'), ('DPA', 'ดี พี เอ'), ('Enter', 'เอ็นเทอร์'), ('Ctrl', 'คอนโทรล'),
            ('Shift', 'ชิฟต์'), ('F5', 'เอฟ ห้า'), (' V ', ' วี '), (' B', ' บี')]


def clone_text(say):
    import re as _re
    t = ' ' + say + ' '
    for en, th in CLONE_TH:
        t = t.replace(en, th)
    t = _re.sub(r'\s+', ' ', t).strip()
    if _re.search(r'[A-Za-z0-9]', t):
        raise RuntimeError('บทพากย์มีอักษรอังกฤษ/ตัวเลขที่ยังไม่มีคำอ่านไทย: ' + t + ' — เพิ่มใน CLONE_TH ใน studio.py')
    return t


def gen_line(key, seed=None):
    line = next((l for l in script_lines() if l['key'] == key), None)
    if not line:
        raise RuntimeError('ไม่พบประโยคนี้ในบทพากย์')
    seed = state['settings']['seed'] if seed is None else seed
    name = '%s_%s_%d.mp3' % (key, say_hash(line['say']), seed)
    out = os.path.join(DATA, 'lines', name)
    res = generate(clone_text(line['say']) if state['settings']['engine'] == 'f5' else line['say'], out, seed)
    with lock:
        old = state['lines'].get(key, {})
        state['lines'][key] = {'file': name, 'seed': seed, 'src': state['settings']['engine'], 'say': say_hash(line['say']),
                               'status': 'draft', 'dur': res.get('dur'), 'ref': state['settings']['ref_id'], 'prev': old.get('file')}
        save_state()
    return state['lines'][key]


def run_batch(only_missing):
    lines = script_lines()
    todo = [l for l in lines if not only_missing or not fresh(l)]
    batch.update(running=True, done=0, total=len(todo), current='', errors=[], stop=False)
    for l in todo:
        if batch['stop']:
            break
        batch['current'] = l['plain'][:60]
        try:
            gen_line(l['key'])
        except Exception as e:
            batch['errors'].append('%s: %s' % (l['plain'][:40], e))
        batch['done'] += 1
    batch.update(running=False, current='')


def fresh(line):
    """ประโยคนี้มีเสียงที่ตรงกับบทพากย์ปัจจุบันแล้วหรือยัง (แก้บทแล้วต้องสร้างใหม่)"""
    rec = state['lines'].get(line['key'])
    return bool(rec and rec.get('say') == say_hash(line['say']) and os.path.exists(os.path.join(DATA, 'lines', rec['file'])))


def publish():
    """คัดลอกประโยคที่ผ่านแล้ว (อนุมัติ/อัดเสียงจริง) ไป guide-audio แล้วเพิ่มชุด self ใน index.json
    ประโยคที่ยังไม่ผ่าน คู่มือจะใช้เสียงชายแทนไปก่อน ไม่เงียบ"""
    idx_path = os.path.join(AUDIO, 'index.json')
    idx = json.load(io.open(idx_path, encoding='utf-8'))
    mapping, used = {}, set()
    for l in script_lines():
        rec = state['lines'].get(l['key'])
        if not rec or rec.get('status') not in ('approved', 'recorded') or not fresh(l):
            continue
        src = os.path.join(DATA, 'lines', rec['file'])
        name = 'self-' + hashlib.md5(open(src, 'rb').read()).hexdigest()[:12] + '.mp3'   # ชื่อตามเนื้อไฟล์ แคชเก่าไม่ค้าง
        dst = os.path.join(AUDIO, name)
        if not os.path.exists(dst):
            shutil.copyfile(src, dst)
        mapping[l['key']] = name; used.add(name)
    for f in os.listdir(AUDIO):                                   # ไฟล์ self ชุดเก่าที่ไม่ใช้แล้ว
        if f.startswith('self-') and f.endswith('.mp3') and f not in used:
            os.remove(os.path.join(AUDIO, f))
    if mapping:
        idx[VOICE_KEY] = mapping
        idx.setdefault('_voices', {})[VOICE_KEY] = {'label': state['settings']['label']}
    else:
        idx.pop(VOICE_KEY, None)
        (idx.get('_voices') or {}).pop(VOICE_KEY, None)
    io.open(idx_path, 'w', encoding='utf-8').write(json.dumps(idx, ensure_ascii=False, indent=0))
    with lock:
        state['published'] = {'at': time.strftime('%Y-%m-%d %H:%M'), 'count': len(mapping)}
        save_state()
    return {'count': len(mapping), 'total': len(script_lines())}


def snapshot():
    lines = []
    for l in script_lines():
        rec = dict(state['lines'].get(l['key']) or {})
        rec.update(l); rec['fresh'] = fresh(l)
        lines.append(rec)
    try:
        male = json.load(io.open(os.path.join(AUDIO, 'index.json'), encoding='utf-8')).get('male', {})
    except Exception:
        male = {}
    for l in lines:
        l['male'] = male.get(l['key'], '')                     # ไว้ฟังเทียบกับเสียงชายเดิม
    return {'settings': state['settings'], 'refs': state['refs'], 'reading': READING, 'lines': lines, 'batch': batch,
            'published': state['published'], 'engine': engine.info, 'data': DATA}


def save_wav_b64(b64, path):
    raw = base64.b64decode(b64.split(',')[-1])
    if raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
        raise RuntimeError('ไฟล์เสียงที่ส่งมาไม่ใช่ WAV')
    open(path, 'wb').write(raw)


# ---------------------------------------------------------------- เว็บ
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def file(self, path, ctype):
        if not os.path.isfile(path):
            return self.send(404, {'error': 'ไม่พบไฟล์'})
        self.send(200, open(path, 'rb').read(), ctype)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p = urllib.parse.unquote(u.path)
        if p in ('/', '/index.html'):
            return self.file(os.path.join(HERE, 'studio.html'), 'text/html; charset=utf-8')
        if p == '/api/state':
            return self.send(200, snapshot())
        m = re.fullmatch(r'/media/(refs|lines|trials)/([\w.\-]+)', p)
        if m:
            ext = m.group(2).rsplit('.', 1)[-1]
            return self.file(os.path.join(DATA, m.group(1), m.group(2)), 'audio/wav' if ext == 'wav' else 'audio/mpeg')
        m = re.fullmatch(r'/guide-audio/([\w.\-]+\.mp3)', p)
        if m:
            return self.file(os.path.join(AUDIO, m.group(1)), 'audio/mpeg')
        self.send(404, {'error': 'ไม่พบ'})

    def do_POST(self):
        # เปิดให้เฉพาะหน้าเว็บของห้องอัดเสียงเอง เว็บอื่นในเบราว์เซอร์เดียวกันยิงคำสั่งเข้ามาไม่ได้
        origin = self.headers.get('Origin', '')
        if origin and origin not in ('http://127.0.0.1:%d' % PORT, 'http://localhost:%d' % PORT):
            return self.send(403, {'error': 'ไม่อนุญาต'})
        n = int(self.headers.get('Content-Length') or 0)
        try:
            body = json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            self.send(200, self.route(urllib.parse.urlparse(self.path).path, body))
        except Exception as e:
            self.send(400, {'error': str(e)})

    def route(self, p, b):
        st = state['settings']
        if p == '/api/ping':
            return engine.ping()
        if p == '/api/settings':
            with lock:
                for k in ('label', 'ref_id', 'engine', 'model'):
                    if k in b:
                        st[k] = str(b[k])
                for k, lo, hi in (('speed', 0.6, 1.4), ('cfg', 1.0, 4.0)):
                    if k in b:
                        st[k] = min(hi, max(lo, float(b[k])))
                for k, lo, hi in (('step', 16, 64), ('seed', 0, 999999)):
                    if k in b:
                        st[k] = min(hi, max(lo, int(b[k])))
                save_state()
            return {'ok': True}
        if p == '/api/ref':
            rid = time.strftime('%Y%m%d-%H%M%S')
            save_wav_b64(b['wav'], os.path.join(DATA, 'refs', rid + '.wav'))
            with lock:
                state['refs'].append({'id': rid, 'file': rid + '.wav', 'text': b['text'].strip(), 'dur': b.get('dur'), 'checks': b.get('checks') or {}})
                if not st['ref_id']:
                    st['ref_id'] = rid
                save_state()
            return {'ok': True, 'id': rid}
        if p == '/api/ref/delete':
            with lock:
                r = ref_by_id(b['id'])
                if r:
                    state['refs'].remove(r)
                    try:
                        os.remove(os.path.join(DATA, 'refs', r['file']))
                    except OSError:
                        pass
                    if st['ref_id'] == r['id']:
                        st['ref_id'] = state['refs'][-1]['id'] if state['refs'] else ''
                save_state()
            return {'ok': True}
        if p == '/api/try':
            text = b['text'].strip()
            if not text:
                raise RuntimeError('พิมพ์ข้อความก่อน')
            name = 'try_%s_%s_%d.mp3' % (st['ref_id'] or st['engine'], say_hash(text + json.dumps(st, sort_keys=True)), int(b.get('seed', st['seed'])))
            out = os.path.join(DATA, 'trials', name)
            if not os.path.exists(out):
                generate(text, out, int(b.get('seed', st['seed'])))
            return {'ok': True, 'url': '/media/trials/' + name}
        if p == '/api/line/gen':
            return gen_line(b['key'], b.get('seed'))
        if p == '/api/line/record':
            line = next((l for l in script_lines() if l['key'] == b['key']), None)
            if not line:
                raise RuntimeError('ไม่พบประโยคนี้')
            base = '%s_%s_rec%s' % (b['key'], say_hash(line['say']), time.strftime('%H%M%S'))
            wav = os.path.join(DATA, 'lines', base + '.wav')
            save_wav_b64(b['wav'], wav)
            try:
                res = engine.call({'op': 'wav2mp3', 'src': wav, 'out': os.path.join(DATA, 'lines', base + '.mp3')})
            except RuntimeError as e:
                if 'lameenc' in str(e) or 'numpy' in str(e):
                    raise RuntimeError('แปลงเสียงเป็น mp3 ต้องติดตั้งเครื่องยนต์เสียงก่อน — รัน python tools/voice_studio/setup_engine.py')
                raise
            with lock:
                state['lines'][b['key']] = {'file': base + '.mp3', 'src': 'record', 'say': say_hash(line['say']), 'status': 'recorded', 'dur': res.get('dur')}
                save_state()
            return state['lines'][b['key']]
        if p == '/api/line/status':
            with lock:
                rec = state['lines'].get(b['key'])
                if rec:
                    rec['status'] = b['status'] if b['status'] in ('draft', 'approved', 'recorded', 'rejected') else rec['status']
                    save_state()
            return {'ok': True}
        if p == '/api/approve-all':
            with lock:
                n = 0
                for l in script_lines():
                    rec = state['lines'].get(l['key'])
                    if rec and rec.get('status') == 'draft' and fresh(l):
                        rec['status'] = 'approved'; n += 1
                save_state()
            return {'ok': True, 'count': n}
        if p == '/api/batch':
            if batch['running']:
                raise RuntimeError('กำลังสร้างอยู่แล้ว')
            threading.Thread(target=run_batch, args=(bool(b.get('only_missing', True)),), daemon=True).start()
            return {'ok': True}
        if p == '/api/batch/stop':
            batch['stop'] = True
            return {'ok': True}
        if p == '/api/publish':
            return publish()
        raise RuntimeError('ไม่รู้จัก ' + p)


def main():
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), H)   # ผูกกับเครื่องนี้เท่านั้น เครื่องอื่นในวง LAN เข้าไม่ได้
    url = 'http://127.0.0.1:%d/' % PORT
    print('ห้องอัดเสียงครู:', url)
    print('ข้อมูลเสียง:', DATA)
    print('เครื่องยนต์:', VPY if os.path.exists(VPY) else 'ยังไม่ติดตั้ง (ใช้ได้แค่เสียงทดสอบ) — รัน setup_engine.py')
    threading.Thread(target=engine.ping, daemon=True).start()
    if '--no-browser' not in sys.argv:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
