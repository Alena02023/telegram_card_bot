import json
import re
from pathlib import Path

from docx import Document


DOCX_FILE = Path("Следы праматери (расшифравка карт) 2.docx")
OUTPUT_FILE = Path("cards.json")
CARDS_FOLDER = Path("cards")


# Проверяем, что Word-файл существует
if not DOCX_FILE.exists():
    raise FileNotFoundError(
        f"Не найден файл: {DOCX_FILE}\n"
        "Проверьте, что DOCX лежит рядом с bot.py."
    )


# Читаем документ
document = Document(DOCX_FILE)

lines = []

for paragraph in document.paragraphs:
    # Иногда номер и начало текста находятся
    # внутри одного абзаца на разных строках.
    for line in paragraph.text.splitlines():
        line = line.strip()

        if line:
            lines.append(line)


# Находим карты №1–45
cards = {}
current_card = None

for line in lines:
    match = re.match(r"^(\d{1,2})\s+(.+)$", line)

    if match:
        number = int(match.group(1))

        if 1 <= number <= 45:
            current_card = number

            cards[number] = {
                "number": number,
                "title": match.group(2).strip(),
                "description_parts": [],
            }

            continue

    if current_card is not None:
        cards[current_card]["description_parts"].append(line)


# Проверяем, что найдены абсолютно все карты
expected_numbers = set(range(1, 46))
found_numbers = set(cards.keys())

if found_numbers != expected_numbers:
    missing = sorted(expected_numbers - found_numbers)

    raise ValueError(
        "Не удалось найти все 45 карт.\n"
        f"Отсутствуют номера: {missing}"
    )


# Формируем итоговые данные
result = {}

for number in range(1, 46):
    card = cards[number]

    description = "\n\n".join(
        card["description_parts"]
    ).strip()

    image_path = CARDS_FOLDER / f"card_{number}.jpg"

    # Проверяем наличие картинки
    if not image_path.exists():
        raise FileNotFoundError(
            f"Не найдена картинка: {image_path}"
        )

    result[str(number)] = {
        "number": number,
        "title": card["title"],
        "description": description,
        "image": image_path.as_posix(),
    }


# Создаём cards.json
with OUTPUT_FILE.open(
    "w",
    encoding="utf-8",
) as file:
    json.dump(
        result,
        file,
        ensure_ascii=False,
        indent=2,
    )


# Показываем результат
print()
print("===================================")
print("ГОТОВО")
print("===================================")
print()

print(f"Создан файл: {OUTPUT_FILE}")
print(f"Количество карт: {len(result)}")

print()
print("Первые карты:")

for number in range(1, 6):
    print(
        f'{number} — {result[str(number)]["title"]}'
    )

print()
print("Последние карты:")

for number in range(41, 46):
    print(
        f'{number} — {result[str(number)]["title"]}'
    )

print()
print("Все изображения найдены.")
print("===================================")