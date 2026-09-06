#!/usr/bin/env python3
"""從來源圖產生應用程式圖示資產（去背 + 多尺寸 PNG + 多尺寸 ICO）。

這**不是**建置步驟。產物已提交進 repo，Windows 端拿到專案直接用
Qt Creator 開啟即可建置，不需要安裝 Python 影像套件。

只有在要換掉圖示本身時才需要執行這支腳本：

    pip install pillow
    python3 tools/make_app_icon.py

輸入  resources/icons/src/app_icon_original.png
輸出  resources/icons/app_icon_{16,24,32,48,64,128,256}.png
      resources/icons/PPS2_0DevTool.ico

去背方式：從影像四邊開始做連通區域填充，只有「與邊界連通」且顏色接近
背景色的像素會被去掉。刻意不用「夠亮就設為透明」的全域門檻 —— 圖案內含
白色的閃光符號與墨鏡反光，全域門檻會把它們打成透明破洞，在深色背景下漏底。

ICO 容器自己組，不用 Pillow 的 ICO 輸出 —— 它會把所有尺寸都寫成 PNG
項目，而小尺寸的 PNG 項目並非所有 Windows 介面都吃得下。

邊緣：原圖圖案外緣是抗鋸齒像素（介於圖案色與背景色之間）。硬性二值化會
留下一圈白邊，在深色工作列上非常明顯。因此依「與背景色的接近程度」換算出
部分 alpha，並反預乘還原出原始前景色。
"""

import io
import struct
from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "resources" / "icons" / "src" / "app_icon_original.png"
OUT_DIR = ROOT / "resources" / "icons"
ICO_PATH = OUT_DIR / "PPS2_0DevTool.ico"

SIZES = [16, 24, 32, 48, 64, 128, 256]

# 與背景色的歐氏距離門檻。
# 距離 <= INNER 視為純背景（alpha 0）；INNER..OUTER 之間依比例給部分 alpha；
# > OUTER 不算背景，填充不越過。
TOL_INNER = 18
TOL_OUTER = 110


def background_color(px, w, h):
    """以四角為樣本推定背景色。"""
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    return tuple(sum(c[i] for c in corners) // len(corners) for i in range(3))


def distance(c, bg):
    dr = c[0] - bg[0]
    dg = c[1] - bg[1]
    db = c[2] - bg[2]
    return (dr * dr + dg * dg + db * db) ** 0.5


def unpremultiply(c, bg, alpha):
    """觀察到的顏色 C = a*F + (1-a)*BG，反推前景色 F。"""
    a = alpha / 255.0
    out = []
    for i in range(3):
        v = (c[i] - (1.0 - a) * bg[i]) / a
        out.append(max(0, min(255, int(round(v)))))
    return tuple(out)


def remove_background(img):
    w, h = img.size
    px = img.load()
    bg = background_color(px, w, h)

    # 從四邊的每個邊界像素起算，廣度優先走訪顏色夠接近背景的連通區域。
    seen = bytearray(w * h)
    queue = deque()

    def push(x, y):
        if 0 <= x < w and 0 <= y < h and not seen[y * w + x]:
            if distance(px[x, y], bg) <= TOL_OUTER:
                seen[y * w + x] = 1
                queue.append((x, y))

    for x in range(w):
        push(x, 0)
        push(x, h - 1)
    for y in range(h):
        push(0, y)
        push(w - 1, y)

    outside = []
    while queue:
        x, y = queue.popleft()
        outside.append((x, y))
        push(x + 1, y)
        push(x - 1, y)
        push(x, y + 1)
        push(x, y - 1)

    span = float(TOL_OUTER - TOL_INNER)
    for x, y in outside:
        c = px[x, y]
        d = distance(c, bg)
        if d <= TOL_INNER:
            px[x, y] = (c[0], c[1], c[2], 0)
            continue
        alpha = int(round(255.0 * (d - TOL_INNER) / span))
        alpha = max(0, min(255, alpha))
        if alpha == 0:
            px[x, y] = (c[0], c[1], c[2], 0)
        else:
            r, g, b = unpremultiply(c, bg, alpha)
            px[x, y] = (r, g, b, alpha)

    return img, bg, len(outside)


def encode_bmp(frame):
    """把一張 RGBA 影像編成 ICO 內用的 DIB（BITMAPINFOHEADER + XOR + AND）。

    ICO 裡的 BMP 有兩個非直覺處：高度要寫成兩倍（XOR 點陣圖加上 AND 遮罩），
    以及列由下往上排。AND 遮罩在 32bpp 下由 alpha 取代，因此整片填 0。
    """
    w, h = frame.size
    px = frame.load()

    xor = bytearray()
    for y in range(h - 1, -1, -1):
        for x in range(w):
            r, g, b, a = px[x, y]
            xor += bytes((b, g, r, a))

    # 1bpp 遮罩，每列補齊到 4 位元組邊界。
    row_bytes = ((w + 31) // 32) * 4
    and_mask = bytes(row_bytes * h)

    header = struct.pack(
        "<IiiHHIIiiII",
        40,                     # biSize
        w,                      # biWidth
        h * 2,                  # biHeight（XOR + AND）
        1,                      # biPlanes
        32,                     # biBitCount
        0,                      # biCompression = BI_RGB
        len(xor) + len(and_mask),
        0, 0, 0, 0,
    )
    return header + bytes(xor) + and_mask


def encode_png(frame):
    buf = io.BytesIO()
    frame.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def write_ico(frames, path):
    """寫出多尺寸 ICO：256 用 PNG 壓縮，其餘用 BMP。

    Pillow 的 ICO 輸出會把**所有**尺寸都寫成 PNG 項目。PNG 項目在 256 尺寸
    是 Windows Vista 之後的標準作法，但小尺寸並非所有 Windows 介面都吃得下，
    因此這裡自己組容器而不用 Image.save(format="ICO")。
    反過來若 256 也用未壓縮 BMP，光那一個項目就要 256KB。
    """
    entries = []
    for frame in frames:
        size = frame.size[0]
        data = encode_png(frame) if size >= 256 else encode_bmp(frame)
        entries.append((size, data))

    offset = 6 + 16 * len(entries)
    header = struct.pack("<HHH", 0, 1, len(entries))
    directory = b""
    payload = b""
    for size, data in entries:
        byte_size = 0 if size >= 256 else size  # 256 在目錄中記為 0
        directory += struct.pack(
            "<BBBBHHII", byte_size, byte_size, 0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)

    path.write_bytes(header + directory + payload)


def main():
    if not SRC.exists():
        raise SystemExit("找不到來源圖：%s" % SRC)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    img = Image.open(SRC).convert("RGBA")
    if img.size != (256, 256):
        print("提醒：來源圖不是 256x256（實際 %dx%d），仍會照樣產生。" % img.size)

    master, bg, cleared = remove_background(img)
    print("背景色推定為 RGB%s，去背影響 %d 個像素。" % (bg, cleared))

    frames = []
    for size in SIZES:
        frame = master if size == 256 else master.resize((size, size), Image.LANCZOS)
        out = OUT_DIR / ("app_icon_%d.png" % size)
        frame.save(out, format="PNG", optimize=True)
        frames.append(frame)
        print("寫出 %s" % out.relative_to(ROOT))

    write_ico(frames, ICO_PATH)
    print("寫出 %s（%d 個尺寸，%d bytes）"
          % (ICO_PATH.relative_to(ROOT), len(SIZES), ICO_PATH.stat().st_size))


if __name__ == "__main__":
    main()
