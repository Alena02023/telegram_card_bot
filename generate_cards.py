from PIL import Image, ImageDraw, ImageFont
import os

os.makedirs("cards", exist_ok=True)

WIDTH = 800
HEIGHT = 1200

for number in range(1, 46):
    image = Image.new("RGB", (WIDTH, HEIGHT), (245, 240, 230))
    draw = ImageDraw.Draw(image)

    # Рамки карты
    draw.rounded_rectangle(
        (35, 35, WIDTH - 35, HEIGHT - 35),
        radius=35,
        outline=(60, 60, 60),
        width=6
    )

    draw.rounded_rectangle(
        (65, 65, WIDTH - 65, HEIGHT - 65),
        radius=25,
        outline=(150, 140, 125),
        width=2
    )

    try:
        big_font = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc",
            150
        )
        title_font = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc",
            55
        )
        small_font = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc",
            32
        )
    except:
        big_font = ImageFont.load_default()
        title_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # Заголовок
    title = "DEMO CARD"

    title_box = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_box[2] - title_box[0]

    draw.text(
        ((WIDTH - title_width) / 2, 180),
        title,
        fill=(70, 70, 70),
        font=title_font
    )

    # Большой номер
    number_text = str(number)

    number_box = draw.textbbox(
        (0, 0),
        number_text,
        font=big_font
    )

    number_width = number_box[2] - number_box[0]
    number_height = number_box[3] - number_box[1]

    draw.text(
        (
            (WIDTH - number_width) / 2,
            (HEIGHT - number_height) / 2 - 80
        ),
        number_text,
        fill=(40, 40, 40),
        font=big_font
    )

    # Нижняя надпись
    bottom = f"CARD {number} / 45"

    bottom_box = draw.textbbox(
        (0, 0),
        bottom,
        font=small_font
    )

    bottom_width = bottom_box[2] - bottom_box[0]

    draw.text(
        ((WIDTH - bottom_width) / 2, 950),
        bottom,
        fill=(100, 100, 100),
        font=small_font
    )

    image.save(f"cards/card_{number}.png")

print("Готово! Создано 45 изображений.")