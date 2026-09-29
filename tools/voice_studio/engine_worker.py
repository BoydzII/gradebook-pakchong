# -*- coding: utf-8 -*-
"""ตัวสร้างเสียงของห้องอัดเสียงครู — รันใน venv ของเครื่องยนต์เสียง (Python 3.11 + torch CUDA)

studio.py เปิดไฟล์นี้เป็นโปรเซสลูกค้างไว้ แล้วคุยกันทีละบรรทัด JSON ผ่าน stdin/stdout
เหตุที่แยกโปรเซส: โมเดลโหลดครั้งละ ~20 วินาทีและกิน VRAM ถ้าโหลดใหม่ทุกประโยคจะช้ามาก
และ torch ยังไม่รองรับ Python รุ่นเดียวกับที่ใช้รันเซิร์ฟเวอร์ ส่วนเซิร์ฟเวอร์ไม่ต้องพึ่งไลบรารีหนักเลย

คำสั่งที่รับ (หนึ่งบรรทัดต่อหนึ่งคำสั่ง):
  {"id":1,"op":"ping"}
  {"id":2,"op":"gen","engine":"f5","ref_audio":"...wav","ref_text":"...","text":"...",
   "speed":1.0,"cfg":2.0,"step":32,"seed":7,"out":"...mp3"}
  {"id":3,"op":"gen","engine":"preview","text":"...","voice":"th-TH-NiwatNeural","out":"...mp3"}
  {"id":4,"op":"wav2mp3","src":"...wav","out":"...mp3"}
ตอบกลับ: {"id":..,"ok":true,"dur":วินาที} หรือ {"id":..,"ok":false,"error":"..."}
"""
import asyncio, json, os, sys, traceback, wave

sys.stdout.reconfigure(encoding='utf-8')
sys.stdin.reconfigure(encoding='utf-8')
SR = 24000
_tts = {}


def say(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + '\n')
    sys.stdout.flush()


def to_mp3(samples, sr, out):
    """float32 [-1,1] → mp3 โมโน 48 kbps ขนาดใกล้ไฟล์ของเสียงชาย/หญิงเดิม เว็บคู่มือจะได้ไม่บวม"""
    import numpy as np, lameenc
    pcm = (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()
    enc = lameenc.Encoder()
    enc.set_bit_rate(48); enc.set_in_sample_rate(sr); enc.set_channels(1); enc.set_quality(2)
    data = enc.encode(pcm) + enc.flush()
    tmp = out + '.part'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, out)            # เขียนเสร็จค่อยเปลี่ยนชื่อ ไม่ทิ้งไฟล์ครึ่ง ๆ ไว้ให้เล่นเสีย
    return len(samples) / sr


def read_wav(path):
    import numpy as np
    with wave.open(path, 'rb') as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        x = np.frombuffer(w.readframes(n), dtype='<i2').astype('float32') / 32768
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def trim_silence(x, sr, pad=0.12):
    """ตัดเงียบหัวท้าย ไม่งั้นเล่นต่อกันในคู่มือจะมีช่วงเงียบยาวระหว่างขั้น"""
    import numpy as np
    if not len(x):
        return x
    win = int(sr * 0.02)
    frames = np.abs(x[: len(x) // win * win]).reshape(-1, win).max(axis=1)
    loud = np.where(frames > max(0.02, frames.max() * 0.05))[0]
    if not len(loud):
        return x
    a = max(0, loud[0] * win - int(pad * sr)); b = min(len(x), (loud[-1] + 1) * win + int(pad * sr))
    return x[a:b]


def f5(req):
    import numpy as np, torch
    from f5_tts_th.tts import TTS
    model = req.get('model', 'v1')
    if model not in _tts:
        _tts[model] = TTS(model=model)
    seed = int(req.get('seed', 7))
    torch.manual_seed(seed); np.random.seed(seed)
    wav = _tts[model].infer(ref_audio=req['ref_audio'], ref_text=req['ref_text'], gen_text=req['text'],
                            step=int(req.get('step', 32)), cfg=float(req.get('cfg', 2.0)), speed=float(req.get('speed', 1.0)))
    x = np.asarray(wav, dtype='float32').reshape(-1)
    peak = float(np.abs(x).max() or 1)
    x = trim_silence(x * min(1.0, 0.89 / peak), SR)   # ปรับระดับเสียงให้ใกล้กันทุกประโยค ไม่ดังค่อยสลับ
    return to_mp3(x, SR, req['out'])


def preview(req):
    """เสียงของ Edge — ใช้ทดสอบระบบทั้งสายก่อนติดตั้งโมเดลโคลนเสียงเสร็จ ไม่ใช่เสียงครู"""
    import edge_tts
    tmp = req['out'] + '.part'
    asyncio.run(edge_tts.Communicate(req['text'], req.get('voice', 'th-TH-NiwatNeural')).save(tmp))
    if os.path.getsize(tmp) < 1024:
        os.remove(tmp); raise RuntimeError('ไม่ได้เสียงกลับมา (เน็ตหลุด?)')
    os.replace(tmp, req['out'])
    return None


def main():
    say({'ready': True, 'python': sys.version.split()[0]})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = {}
        try:
            req = json.loads(line)
            op = req.get('op')
            if op == 'ping':
                info = {}
                try:
                    import torch
                    info = {'cuda': torch.cuda.is_available(), 'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else ''}
                except Exception as e:
                    info = {'cuda': False, 'torch_error': str(e)}
                try:
                    import f5_tts_th  # noqa: F401
                    info['f5'] = True
                except Exception:
                    info['f5'] = False
                say(dict(id=req.get('id'), ok=True, **info))
            elif op == 'gen':
                dur = f5(req) if req.get('engine') == 'f5' else preview(req)
                say({'id': req.get('id'), 'ok': True, 'dur': dur})
            elif op == 'wav2mp3':
                x, sr = read_wav(req['src'])
                say({'id': req.get('id'), 'ok': True, 'dur': to_mp3(trim_silence(x, sr), sr, req['out'])})
            else:
                say({'id': req.get('id'), 'ok': False, 'error': 'ไม่รู้จักคำสั่ง ' + str(op)})
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            say({'id': req.get('id'), 'ok': False, 'error': '%s: %s' % (type(e).__name__, e)})


if __name__ == '__main__':
    main()
