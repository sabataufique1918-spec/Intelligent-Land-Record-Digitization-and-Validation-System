"""Synthetic land-record text lines for fine-tuning Tesseract's Hindi LSTM model.

Writes <out>/<name>.tif + .gt.txt + .box (tesstrain line format). Usage:
    python synth_lines.py OUT_DIR COUNT SEED [--fonts f1,f2] [--exclude f1,f2]
Needs: pip install uharfbuzz freetype-py (into WORK/pylib or the venv), Devanagari .ttf fonts in WORK/fonts
and hin.lstm-unicharset in WORK (see train.sh). WORK defaults to ./work next to this script.
"""
import random
import sys
import unicodedata
from pathlib import Path

import os

HERE = Path(os.environ.get("OCR_FT_WORK", Path(__file__).parent / "work"))
sys.path.insert(0, str(HERE / "pylib"))

import cv2  # noqa: E402
import freetype  # noqa: E402
import numpy as np  # noqa: E402
import uharfbuzz as hb  # noqa: E402

CHARSET = {line.split(" ")[0] for line in (HERE / "hin.lstm-unicharset").read_text("utf-8").splitlines()[1:] if line}
CHARSET.add(" ")

FONT_DIR = HERE / "fonts"
FONTS = sorted(FONT_DIR.glob("*.ttf")) + [Path("C:/Windows/Fonts/Nirmala.ttc")]
HANDWRITING = {"Kalam-Regular", "Kalam-Light", "Kalam-Bold", "Amita-Regular"}

FIRST = ("राम श्याम मोहन सोहन रमेश सुरेश महेश दिनेश गणेश कमला सीता गीता सावित्री पार्वती लक्ष्मी "
         "भगवान किशन हरि गोपाल जगदीश ओमप्रकाश रामप्रसाद शिवराम बद्रीनारायण प्रेमचंद हीरालाल "
         "मोतीलाल कन्हैयालाल भंवरलाल नारायण रघुनाथ विजय अजय संजय राजेन्द्र सत्यनारायण मांगीलाल "
         "गंगाराम धन्नालाल रामस्वरूप शांति मीरा उर्मिला सरोज कैलाश मुकेश राकेश अशोक प्रकाश "
         "रामचन्द्र लालचंद फूलचंद छोटेलाल बाबूलाल मदनलाल नंदकिशोर गोविन्द बलराम हनुमान").split()
LAST = ("शर्मा वर्मा सिंह यादव पटेल गुप्ता मीणा जाट चौधरी तिवारी पाण्डेय मिश्रा त्रिपाठी "
        "राठौड़ चौहान सोलंकी जैन अग्रवाल माहेश्वरी गुर्जर कुमावत प्रजापति सैनी माली "
        "कुशवाहा राजपूत ठाकुर दुबे श्रीवास्तव खान कुरैशी अंसारी").split()
PLACES = ("रामपुर सीतापुर बड़गांव शिवपुरी गोपालपुरा किशनगढ़ चांदपुर नयागांव बसंतपुर मोहनपुरा "
          "उदयपुर जयपुर अजमेर कोटा भीलवाड़ा चित्तौड़गढ़ बूंदी टोंक भोपाल इंदौर सागर रीवा "
          "ग्वालियर लखनऊ कानपुर वाराणसी प्रयागराज गोरखपुर पटना गया आगरा मथुरा अलीगढ़ बरेली "
          "मेरठ झांसी हमीरपुर सिरोही पाली नागौर बीकानेर जोधपुर गिर्वा मावली वल्लभनगर").split()
TERMS = ("खसरा खाता खतौनी जमाबंदी रकबा हेक्टेयर बीघा बिस्वा एकड़ भूमि स्वामी काश्तकार "
         "खातेदार नामांतरण दाखिल खारिज पटवारी तहसीलदार गिरदावर राजस्व ग्राम तहसील जिला "
         "सिंचित असिंचित बंजर चरागाह लगान मौजा हल्का बंदोबस्त विक्रय पत्र रजिस्ट्री दिनांक "
         "संवत मुकदमा अर्जी हुजूर बाबत जायदाद हिस्सा वारिस इंतकाल फौती बैनामा रहन गिरवी "
         "कब्जा काबिज मालगुजारी नकल रिपोर्ट मिसल आदेश न्यायालय कलेक्टर उपखण्ड अधिकारी "
         "सहायक भू अभिलेख निरीक्षक नक्शा सीमा मेड़ कुआं नलकूप फसल गेहूं चना सरसों मक्का").split()
PHRASES = [
    "प्रमाणित किया जाता है कि", "उपरोक्त भूमि का नामांतरण स्वीकार किया जाता है",
    "मौके पर काबिज है", "रिपोर्ट पेश है", "आवश्यक कार्यवाही हेतु प्रस्तुत", "नकल जमाबंदी",
    "सही प्रतिलिपि", "हस्ताक्षर पटवारी", "मोहर तहसीलदार", "आदेश दिनांक", "विक्रय पत्र के आधार पर",
    "फौती के आधार पर वारिसान के नाम", "भूमि का कब्जा", "खातेदारी अधिकार", "राजस्व रिकार्ड में दर्ज",
    "हल्का पटवारी की रिपोर्ट", "जांच कर रिपोर्ट करें", "प्रार्थी निवेदन करता है कि",
    "सेवा में श्रीमान", "महोदय", "सादर निवेदन है कि", "कृपया उचित कार्यवाही करें", "आपका आभारी रहूंगा",
]
RELATION = ["पुत्र", "पुत्री", "पत्नी", "पुत्र श्री", "पत्नी श्री", "पुत्री श्री", "निवासी", "जाति", "उम्र"]
DEV = str.maketrans("0123456789", "०१२३४५६७८९")


def num(lo=1, hi=999):
    s = str(random.randint(lo, hi))
    return s.translate(DEV) if random.random() < 0.55 else s


def area():
    s = f"{random.randint(0, 12)}.{random.randint(0, 9999):04d}"[: random.choice([4, 5, 6])]
    return s.translate(DEV) if random.random() < 0.55 else s


def date():
    d, m, y = random.randint(1, 28), random.randint(1, 12), random.randint(1940, 2026)
    sep = random.choice(["-", "/", "."])
    s = f"{d:02d}{sep}{m:02d}{sep}{y}" if random.random() < .7 else f"{d}{sep}{m}{sep}{str(y)[2:]}"
    return s.translate(DEV) if random.random() < 0.55 else s


def person():
    return f"{random.choice(FIRST)} {random.choice(RELATION)} {random.choice(FIRST)} {random.choice(LAST)}"


TEMPLATES = [
    lambda: f"खसरा नं. {num()}/{num(1, 9)} रकबा {area()} हेक्टेयर",
    lambda: f"खाता संख्या {num()} ग्राम {random.choice(PLACES)} तहसील {random.choice(PLACES)}",
    lambda: f"जिला {random.choice(PLACES)} ({random.choice(['राज.', 'म.प्र.', 'उ.प्र.', 'बिहार'])})",
    lambda: f"{person()} निवासी {random.choice(PLACES)}",
    lambda: f"नाम खातेदार : {random.choice(FIRST)} {random.choice(LAST)}",
    lambda: f"दिनांक {date()} को {random.choice(PHRASES)}",
    lambda: f"{random.choice(PHRASES)} {random.choice(TERMS)} {random.choice(TERMS)}",
    lambda: f"क्र. {num(1, 99)} {random.choice(TERMS)} {num()} {random.choice(TERMS)} {area()}",
    lambda: f"कुल रकबा {area()} {random.choice(['हेक्टेयर', 'बीघा', 'एकड़'])} लगान ₹ {num(1, 9999)}",
    lambda: f"नामांतरण संख्या {num()} दिनांक {date()}",
    lambda: " ".join(random.choice(TERMS + FIRST + PLACES) for _ in range(random.randint(3, 8))),
    lambda: f"{random.choice(PHRASES)}। {random.choice(PHRASES)}",
    lambda: f"मौजा {random.choice(PLACES)} हल्का {random.choice(PLACES)} नं. {num(1, 99)}",
    lambda: f"{num()} {num()} {area()} {random.choice(TERMS)} {date()}",
    lambda: f"संवत {random.randint(1990, 2082)} {random.choice(TERMS)} {random.choice(['सिंचित', 'असिंचित', 'बंजर'])}",
]


def line_text():
    t = unicodedata.normalize("NFC", random.choice(TEMPLATES)())
    return " ".join(t.split())


def allowed(text):
    return all(ch in CHARSET for ch in text)


_faces: dict = {}


def render(text, font_path, px):
    key = (str(font_path), px)
    if key not in _faces:
        blob = hb.Blob.from_file_path(str(font_path))
        face = hb.Face(blob, 0)
        _faces[key] = (hb.Font(face), freetype.Face(str(font_path)))
    hbfont, ft = _faces[key]
    ft.set_pixel_sizes(0, px)
    hbfont.scale = (px * 64, px * 64)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf, {})
    width = sum(p.x_advance for p in buf.glyph_positions) // 64 + px * 2
    height = px * 3
    canvas = np.zeros((height, width), np.uint8)
    x, base = px, int(px * 1.9)
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        ft.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER)
        g = ft.glyph
        bm = g.bitmap
        if bm.width and bm.rows:
            arr = np.array(bm.buffer, np.uint8).reshape(bm.rows, bm.pitch)[:, : bm.width]
            gx = x + pos.x_offset // 64 + g.bitmap_left
            gy = base - pos.y_offset // 64 - g.bitmap_top
            y0, x0 = max(0, gy), max(0, gx)
            y1, x1 = min(height, gy + bm.rows), min(width, gx + bm.width)
            if y1 > y0 and x1 > x0:
                canvas[y0:y1, x0:x1] = np.maximum(canvas[y0:y1, x0:x1], arr[y0 - gy:y1 - gy, x0 - gx:x1 - gx])
        x += pos.x_advance // 64
    rows = np.where(canvas.max(axis=1) > 0)[0]
    cols = np.where(canvas.max(axis=0) > 0)[0]
    if not len(rows):
        return None
    return canvas[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]


def degrade(ink, rng):
    """ink: 0..255 coverage. Returns a grayscale scan-like image (dark text on light paper)."""
    pad = rng.randint(6, 20)
    ink = cv2.copyMakeBorder(ink, pad, pad, pad + rng.randint(0, 20), pad + rng.randint(0, 20), cv2.BORDER_CONSTANT, 0)
    if rng.random() < 0.35:  # pen thickness
        k = np.ones((2, 2), np.uint8)
        ink = cv2.dilate(ink, k) if rng.random() < 0.6 else cv2.erode(ink, k)
    h, w = ink.shape
    if rng.random() < 0.5:  # slight rotation / shear like a hand-written or skewed line
        ang = rng.uniform(-1.5, 1.5)
        shear = rng.uniform(-0.15, 0.15) if rng.random() < 0.4 else 0
        m = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        m[0, 1] += shear
        ink = cv2.warpAffine(ink, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
    paper = rng.uniform(190, 250)
    inkcol = rng.uniform(0, 90)
    img = paper - (paper - inkcol) * (ink.astype(np.float32) / 255.0)
    # uneven paper / stains
    if rng.random() < 0.6:
        grad = cv2.resize(np.random.default_rng(rng.randint(0, 1 << 30)).uniform(-25, 10, (3, 6)).astype(np.float32),
                          (w, h), interpolation=cv2.INTER_CUBIC)
        img += grad
    if rng.random() < 0.3:  # table rules / underline
        for _ in range(rng.randint(1, 2)):
            y = rng.choice([rng.randint(0, 4), h - rng.randint(1, 5), rng.randint(int(h * 0.85), h - 1)])
            cv2.line(img, (0, y), (w, y + rng.randint(-2, 2)), float(inkcol + 30), rng.randint(1, 3))
    if rng.random() < 0.15:  # vertical table border cut into the line
        x = rng.choice([rng.randint(0, 5), w - rng.randint(1, 6)])
        cv2.line(img, (x, 0), (x, h), float(inkcol + 30), rng.randint(1, 3))
    img += np.random.default_rng(rng.randint(0, 1 << 30)).normal(0, rng.uniform(2, 14), img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    if rng.random() < 0.5:
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.4, 1.3))
    if rng.random() < 0.5:  # low-resolution scan / phone photo
        f = rng.uniform(0.35, 0.8)
        small = cv2.resize(img, (max(8, int(w * f)), max(8, int(h * f))), interpolation=cv2.INTER_AREA)
        img = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    if rng.random() < 0.4:
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(25, 80)])
        img = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    return img


def box_lines(text, width, height):
    """Same as tesstrain's generate_line_box.py."""
    out = []
    for i in range(1, len(text)):
        ch, prev = text[i], text[i - 1]
        if unicodedata.combining(ch):
            out.append(f"{prev + ch} 0 0 {width} {height} 0")
        elif not unicodedata.combining(prev):
            out.append(f"{prev} 0 0 {width} {height} 0")
    if not unicodedata.combining(text[-1]):
        out.append(f"{text[-1]} 0 0 {width} {height} 0")
    out.append(f"\t {width} {height} {width + 1} {height + 1} 0")
    return "\n".join(out) + "\n"


def main():
    out, count, seed = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    fonts = FONTS
    if "--fonts" in sys.argv:
        names = sys.argv[sys.argv.index("--fonts") + 1].split(",")
        fonts = [f for f in FONTS if f.stem in names]
    if "--exclude" in sys.argv:
        names = sys.argv[sys.argv.index("--exclude") + 1].split(",")
        fonts = [f for f in fonts if f.stem not in names]
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    random.seed(seed)
    made = 0
    while made < count:
        text = line_text()
        if not allowed(text):
            continue
        font = rng.choice(fonts + [f for f in fonts if f.stem in HANDWRITING])  # weight handwriting-like fonts x2
        px = rng.randint(28, 56)
        try:
            ink = render(text, font, px)
        except Exception:
            continue
        if ink is None or ink.shape[1] < 40:
            continue
        img = degrade(ink, rng)
        name = f"syn_{seed}_{made:05d}"
        cv2.imwrite(str(out / f"{name}.tif"), img)
        (out / f"{name}.gt.txt").write_text(text + "\n", "utf-8")
        (out / f"{name}.box").write_text(box_lines(text, img.shape[1], img.shape[0]), "utf-8")
        made += 1
    print(out, made)


if __name__ == "__main__":
    main()
