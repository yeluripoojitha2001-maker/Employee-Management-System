import qrcode

data = "http://10.86.93.31:5000/qr_attendance?user=test"

qr = qrcode.QRCode(
    version=1,
    box_size=10,
    border=5
)

qr.add_data(data)
qr.make(fit=True)

img = qr.make_image(fill="black", back_color="white")
img.save("static/qr.png")

print("QR Code Created Successfully")