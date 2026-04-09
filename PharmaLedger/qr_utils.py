import qrcode, os

def generate_qr(uid):
    os.makedirs("static/qr",exist_ok=True)
    img = qrcode.make(uid)
    img.save(f"static/qr/{uid}.png")
