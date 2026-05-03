from PIL import Image, ImageDraw, ImageFilter
import math
import random

W, H = 1024, 1536
random.seed(20260501)


def lerp(a, b, t):
    return int(a + (b - a) * t)


def mix(c1, c2, t):
    return tuple(lerp(c1[i], c2[i], t) for i in range(3))


img = Image.new("RGB", (W, H), "#f4efe7")
draw = ImageDraw.Draw(img)

# Quiet golden-hour sky.
top = (230, 238, 236)
mid = (245, 226, 196)
bottom = (238, 204, 165)
for y in range(H):
    t = y / H
    if t < 0.56:
        c = mix(top, mid, t / 0.56)
    else:
        c = mix(mid, bottom, (t - 0.56) / 0.44)
    draw.line([(0, y), (W, y)], fill=c)

# Soft sun glow.
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
cx, cy = 735, 420
for r in range(360, 20, -8):
    alpha = int(46 * (1 - r / 360) ** 1.7)
    gd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 210, 144, alpha))
img = Image.alpha_composite(img.convert("RGBA"), glow)
draw = ImageDraw.Draw(img)

# Distant layered mountains.
mountain_layers = [
    ((171, 189, 184, 118), 612, 130, 0.80),
    ((137, 164, 161, 150), 675, 155, 0.70),
    ((101, 134, 136, 180), 750, 190, 0.62),
]
for color, base, amp, freq in mountain_layers:
    pts = [(0, H)]
    for x in range(-20, W + 40, 16):
        y = base
        y -= amp * math.sin((x * freq + 55) / 150)
        y -= amp * 0.45 * math.sin((x * freq + 180) / 71)
        pts.append((x, int(y)))
    pts += [(W, H)]
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon(pts, fill=color)
    layer = layer.filter(ImageFilter.GaussianBlur(1.2))
    img = Image.alpha_composite(img, layer)

draw = ImageDraw.Draw(img)

# Hazy valley band and path.
draw.rectangle((0, 725, W, 1020), fill=(231, 216, 188, 105))
path = [(265, H), (760, H), (622, 858), (448, 858)]
draw.polygon(path, fill=(207, 181, 147, 210))
draw.polygon([(350, H), (680, H), (575, 860), (490, 860)], fill=(226, 205, 174, 160))

# Crowd silhouettes: present but softened, not chaotic.
crowd = Image.new("RGBA", (W, H), (0, 0, 0, 0))
cd = ImageDraw.Draw(crowd)
palette = [
    (72, 82, 84, 145),
    (112, 92, 75, 138),
    (82, 107, 111, 128),
    (150, 126, 91, 126),
]
for i in range(150):
    yy = random.randint(830, 1235)
    center_bias = 1 - abs((yy - 1020) / 420)
    x_mid = W / 2 + random.uniform(-270, 270) * (0.55 + center_bias)
    xx = int(max(70, min(W - 70, x_mid + random.gauss(0, 70))))
    scale = 0.45 + (yy - 830) / 520
    body_h = int(34 * scale)
    body_w = int(13 * scale)
    head = max(3, int(6 * scale))
    col = random.choice(palette)
    cd.ellipse((xx - head, yy - body_h - head * 2, xx + head, yy - body_h), fill=col)
    cd.rounded_rectangle(
        (xx - body_w, yy - body_h, xx + body_w, yy + int(body_h * 0.36)),
        radius=max(2, int(4 * scale)),
        fill=col,
    )
crowd = crowd.filter(ImageFilter.GaussianBlur(0.45))
img = Image.alpha_composite(img, crowd)
draw = ImageDraw.Draw(img)

# Foreground quiet observer.
person = Image.new("RGBA", (W, H), (0, 0, 0, 0))
pd = ImageDraw.Draw(person)
px, py = 364, 1275
pd.ellipse((px - 31, py - 226, px + 31, py - 164), fill=(45, 54, 55, 240))
pd.rounded_rectangle((px - 16, py - 169, px + 16, py - 136), radius=7, fill=(41, 51, 53, 240))
pd.polygon(
    [
        (px - 58, py - 142),
        (px + 58, py - 142),
        (px + 82, py + 70),
        (px + 28, py + 92),
        (px, py + 50),
        (px - 30, py + 92),
        (px - 84, py + 70),
    ],
    fill=(38, 49, 52, 244),
)
pd.polygon([(px - 30, py + 78), (px - 86, py + 206), (px - 35, py + 220), (px + 4, py + 92)], fill=(34, 45, 48, 240))
pd.polygon([(px + 28, py + 78), (px + 84, py + 208), (px + 35, py + 221), (px - 4, py + 92)], fill=(34, 45, 48, 240))
pd.line((px - 55, py - 120, px - 104, py + 42), fill=(36, 47, 50, 228), width=18)
pd.line((px + 55, py - 120, px + 101, py + 38), fill=(36, 47, 50, 228), width=18)
pd.line((px - 24, py - 135, px + 37, py - 122), fill=(196, 169, 127, 92), width=8)
person = person.filter(ImageFilter.GaussianBlur(0.25))
img = Image.alpha_composite(img, person)

# Foreground vignette and film grain.
vignette = Image.new("RGBA", (W, H), (0, 0, 0, 0))
vd = ImageDraw.Draw(vignette)
for r in range(0, 500, 8):
    alpha = int(32 * (r / 500) ** 2)
    vd.rounded_rectangle((r, r, W - r, H - r), radius=36, outline=(71, 52, 36, alpha), width=10)
vignette = vignette.filter(ImageFilter.GaussianBlur(28))
img = Image.alpha_composite(img, vignette)

grain = Image.new("RGBA", (W, H), (0, 0, 0, 0))
pixels = grain.load()
for _ in range(65000):
    x = random.randrange(W)
    y = random.randrange(H)
    v = random.choice([-1, 1])
    a = random.randint(4, 11)
    shade = 255 if v > 0 else 55
    pixels[x, y] = (shade, shade, shade, a)
img = Image.alpha_composite(img, grain)

out = "output/imagegen/may-day-crowd-calm-cover-local.png"
img.convert("RGB").save(out, quality=95)
print(out)
