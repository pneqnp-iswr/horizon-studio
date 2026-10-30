"""Generate original Horizon Studio app icon, without game assets."""
from pathlib import Path
from PIL import Image, ImageDraw


def build_icon(output: Path) -> Path:
    image = Image.new('RGBA', (256, 256), (8, 13, 22, 255))
    d = ImageDraw.Draw(image)
    d.rounded_rectangle((8, 8, 248, 248), radius=49,
                        fill=(18, 30, 45), outline=(85, 213, 244), width=7)
    top = [(128,49),(207,93),(128,139),(49,93)]
    d.polygon(top, fill=(101,233,255))
    d.polygon([(49,93),(128,139),(128,216),(49,170)], fill=(37,118,175))
    d.polygon([(128,139),(207,93),(207,170),(128,216)], fill=(56,170,210))
    d.line(top+[top[0]], fill=(189,251,255), width=4)
    d.line([(128,139),(128,216)], fill=(11,59,90), width=4)
    d.polygon([(128,80),(161,99),(128,117),(95,99)], fill=(12,55,86))
    d.line([(104,99),(123,111),(154,94)], fill=(135,250,190), width=7)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    return output


if __name__ == '__main__':
    print(build_icon(Path(__file__).resolve().parent.parent / 'assets' / 'horizon-studio.ico'))
