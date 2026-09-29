# -*- coding: utf-8 -*-
"""ติดตั้งเครื่องยนต์โคลนเสียง (F5-TTS-THAI) สำหรับห้องอัดเสียงครู — รันครั้งเดียว

    python tools/voice_studio/setup_engine.py           ติดตั้ง
    python tools/voice_studio/setup_engine.py --check   ตรวจอย่างเดียว

ทำอะไรบ้าง (ใช้เน็ตรวมราว 4–5 GB ครั้งแรก):
  1. ติดตั้ง uv (ตัวจัดการ Python) ให้ Python ที่ใช้อยู่
  2. สร้าง venv Python 3.11 ที่ D:\\KruSpace\\voice-engine\\.venv (นอกรีโพ — ไฟล์ใหญ่ห้ามขึ้น GitHub)
     เหตุที่ต้องเป็น 3.11: torch/numpy ที่ F5-TTS-THAI ต้องใช้ ยังไม่มีสำหรับ Python 3.14 ที่เครื่องใช้อยู่
  3. torch 2.4.1 + CUDA 12.4 (~2.5 GB) แล้ว f5-tts-th lameenc edge-tts
     (ไม่ใช้ 2.4.0 — บน Windows ขาด libomp140 ทำให้ import torch ไม่ได้: fbgemm.dll WinError 126)
  4. น้ำหนักโมเดล (~1.3 GB) จะโหลดจาก Hugging Face เองตอนสร้างเสียงครั้งแรก
"""
import json, os, subprocess, sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))          # D:\KruSpace
ENGINE = os.environ.get('KRU_VOICE_ENGINE', os.path.join(ROOT, 'voice-engine'))
VENV = os.path.join(ENGINE, '.venv')
VPY = os.path.join(VENV, 'Scripts', 'python.exe') if os.name == 'nt' else os.path.join(VENV, 'bin', 'python')


def run(args, **kw):
    print('>', ' '.join(args), flush=True)
    r = subprocess.run(args, **kw)
    if r.returncode:
        sys.exit('ล้มเหลวที่ขั้นนี้ (รหัส %d) — ดูข้อความด้านบน' % r.returncode)


def check():
    if not os.path.exists(VPY):
        print('ยังไม่มี venv ที่', VENV)
        return False
    p = subprocess.run([VPY, os.path.join(HERE, 'engine_worker.py')], input=json.dumps({'id': 1, 'op': 'ping'}) + '\n',
                       capture_output=True, text=True, encoding='utf-8')
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    info = json.loads(lines[-1]) if lines else {}
    print('Python ใน venv:', json.loads(lines[0]).get('python') if lines else '?')
    print('GPU (CUDA):', info.get('gpu') or ('ใช้ไม่ได้' if not info.get('cuda') else '?'))
    print('F5-TTS-THAI:', 'พร้อม' if info.get('f5') else 'ยังไม่ติดตั้ง')
    if p.stderr.strip():
        print(p.stderr.strip()[-800:])
    return bool(info.get('f5'))


def main():
    if '--check' in sys.argv:
        sys.exit(0 if check() else 1)
    os.makedirs(ENGINE, exist_ok=True)
    run([sys.executable, '-m', 'pip', 'install', '--user', '--quiet', 'uv'])
    uv = [sys.executable, '-m', 'uv']
    if not os.path.exists(VPY):
        run(uv + ['venv', '--python', '3.11', VENV])
    run(uv + ['pip', 'install', '--python', VPY, 'torch==2.4.1', 'torchaudio==2.4.1',
              '--index-url', 'https://download.pytorch.org/whl/cu124'])
    run(uv + ['pip', 'install', '--python', VPY, 'f5-tts-th', 'lameenc', 'edge-tts', 'numpy<=1.26.4'])
    print('\nตรวจหลังติดตั้ง')
    ok = check()
    print('\nพร้อมแล้ว เปิดห้องอัดเสียงด้วย  python tools/voice_studio/studio.py' if ok else '\nยังไม่พร้อม ดูข้อความด้านบน')


if __name__ == '__main__':
    main()
