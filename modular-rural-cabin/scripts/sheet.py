import sys, glob, os
from PIL import Image, ImageDraw
out, cols = sys.argv[1], int(sys.argv[2])
files = sys.argv[3:]
T = (360, 280)
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (T[0] * cols, T[1] * rows), "white")
for i, f in enumerate(files):
    im = Image.open(f).convert("RGB").resize(T, Image.LANCZOS)
    ImageDraw.Draw(im).text((5, 5), os.path.basename(f)[:-6], fill="black")
    sheet.paste(im, ((i % cols) * T[0], (i // cols) * T[1]))
sheet.save(out, quality=86)
