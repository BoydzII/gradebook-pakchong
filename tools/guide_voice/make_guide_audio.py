# -*- coding: utf-8 -*-
"""อัดเสียงพากย์คู่มือ guide.html ด้วยเสียง neural ภาษาไทย แล้วเขียน guide-audio/index.json

วิธีใช้ (จากโฟลเดอร์ app):
    python -m pip install edge-tts
    python tools/guide_voice/make_guide_audio.py                 # อัดเฉพาะบรรทัดที่ยังไม่มีไฟล์ ทั้งเสียงชายและหญิง
    python tools/guide_voice/make_guide_audio.py --force         # อัดใหม่ทั้งหมด

อัดสองเสียงจากบทเดียวกัน (ชาย = Niwat, หญิง = Premwadee) ผู้ชมเลือกเสียงได้ในหน้าคู่มือ
บทพากย์ไม่มีคำลงท้าย ค่ะ/ครับ เพราะเสียง neural ออกเสียงหางเสียงเพี้ยน และจะได้ใช้บทเดียวกันทั้งสองเสียง
index.json = { "male": {คีย์: ไฟล์}, "female": {คีย์: ไฟล์} } + เสียงชุดอื่นที่มีอยู่แล้ว (เช่น "self" จากห้องอัดเสียงครู) เก็บไว้ตามเดิม

ทำไมแยกบทพากย์ (script.json) ออกจากคำบรรยายบนจอ:
คำบรรยายเขียนให้ตาอ่าน มีตัวย่อ ลูกศร จุดคั่น (ปพ.5 • ☰ →) ถ้าให้เครื่องอ่านตรง ๆ จะอ่านผิดและหยุดเป็นช่วง ๆ
บทพากย์จึงเขียนเป็นภาษาพูดแยกไว้ แต่ผูกกับคำบรรยายด้วยแฮชของข้อความบนจอ (plain) —
ถ้าแก้คำบรรยายใน guide.html แล้วไม่แก้บทพากย์ สคริปต์นี้จะแจ้งว่าไม่ตรง และหน้าเว็บจะใช้เสียงของเครื่องแทนไปก่อน
ชื่อไฟล์ = แฮชของบทพากย์ แก้บทแล้วอัดใหม่ ชื่อไฟล์จะเปลี่ยน แคชเก่าบนเครื่องผู้ใช้จึงไม่ค้าง
"""
import asyncio, io, json, os, sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(APP, 'guide-audio')
VOICES = {'male': 'th-TH-NiwatNeural', 'female': 'th-TH-PremwadeeNeural'}
RATE = '+0%'
for i, a in enumerate(sys.argv):
    if a == '--rate': RATE = sys.argv[i + 1]
FORCE = '--force' in sys.argv


def say_key(text):
    """FNV-1a 32 บิตทีละ code point — ต้องตรงกับ sayKey() ใน guide.html"""
    h = 0x811c9dc5
    for ch in text:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return '%08x' % h


async def main():
    import edge_tts
    script = json.load(io.open(os.path.join(HERE, 'script.json'), encoding='utf-8'))
    os.makedirs(OUT, exist_ok=True)
    index, bad, made = {g: {} for g in VOICES}, [], 0
    for key, row in script.items():
        if key.startswith('_'):
            continue
        if say_key(row['plain']) != key:
            bad.append(key + ' : ข้อความบนจอ (plain) ไม่ตรงกับคีย์')
            continue
        for gender, voice in VOICES.items():
            file = say_key(voice + '|' + RATE + '|' + row['say']) + '.mp3'
            path = os.path.join(OUT, file)
            # ไฟล์ว่างจากรอบที่เน็ตหลุดกลางทาง ถือว่ายังไม่มี ไม่งั้นจะค้างเป็นเสียงเงียบตลอดไป
            if FORCE or not os.path.exists(path) or os.path.getsize(path) < 1024:
                for attempt in range(3):
                    try:
                        await edge_tts.Communicate(row['say'], voice, rate=RATE).save(path)
                        break
                    except Exception as e:
                        if os.path.exists(path): os.remove(path)
                        if attempt == 2: raise
                        await asyncio.sleep(2)
                made += 1
            index[gender][key] = file
    # เสียงชุดอื่นที่ไม่ได้มาจากสคริปต์นี้ (เช่นเสียงครูจากห้องอัดเสียง = "self" และชื่อปุ่ม "_voices") ต้องเก็บไว้ตามเดิม
    try:
        old = json.load(io.open(os.path.join(OUT, 'index.json'), encoding='utf-8'))
    except Exception:
        old = {}
    others = {k: v for k, v in old.items() if k not in VOICES}
    # ไฟล์ที่ไม่มีบทไหนใช้แล้ว ลบทิ้ง ไม่ให้โฟลเดอร์บวม (ไฟล์ของเสียงชุดอื่นไม่แตะ)
    used = set(f for m in index.values() for f in m.values())
    keep = set(f for k, m in others.items() if not k.startswith('_') and isinstance(m, dict) for f in m.values())
    removed = [f for f in os.listdir(OUT) if f.endswith('.mp3') and f not in used and f not in keep and not f.startswith('self-')]
    for f in removed:
        os.remove(os.path.join(OUT, f))
    io.open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8').write(json.dumps(dict(index, **others), ensure_ascii=False, indent=0))
    size = sum(os.path.getsize(os.path.join(OUT, f)) for f in used)
    print('เสียง %s • %d บรรทัด • อัดใหม่ %d • ลบไฟล์เก่า %d • รวม %.1f MB' % ('/'.join(VOICES.values()), len(index['male']), made, len(removed), size / 1048576))
    if bad:
        print('ไม่ตรง %d บรรทัด:' % len(bad)); [print('  ' + b) for b in bad]
        sys.exit(1)

asyncio.run(main())
