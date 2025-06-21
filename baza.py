import pandas as pd
import sqlite3

EXCEL_PATH = "C:\\Users\\WIN\\Desktop\\Коректированный.xlsx"
DB_PATH = "words.db"

# Загружаем Excel
df = pd.read_excel(EXCEL_PATH)

# Очищаем от пустых обязательных столбцов
df = df.dropna(subset=["word_en", "word_de", "word_ru"])

# Стандартизируем формат: убираем пробелы
df['word_en'] = df['word_en'].astype(str).str.strip()
df['word_de'] = df['word_de'].astype(str).str.strip()
df['word_ru'] = df['word_ru'].astype(str).str.strip()
df['category'] = df['category'].fillna('').astype(str).str.strip()

# Подключение к базе
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Создание таблицы при необходимости
cursor.execute("""
    CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY,
    word_en TEXT NOT NULL,
    word_de TEXT NOT NULL,
    word_ru TEXT NOT NULL,
    category TEXT,
    article_de TEXT,
    freq INTEGER,
    difficulty TEXT,
    image_path TEXT,
    bg_en TEXT,
    bg_de TEXT,
    bg_ru TEXT
)
""")

# Функция для добавления колонки, если её нет
def add_column_if_not_exists(table_name, column_name, column_type):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [info[1] for info in cursor.fetchall()]
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        print(f"Добавлена колонка: {column_name}")
    else:
        print(f"Колонка уже существует: {column_name}")

# Добавляем новые колонки для фоновых изображений
add_column_if_not_exists("words", "bg_en", "TEXT")
add_column_if_not_exists("words", "bg_de", "TEXT")
add_column_if_not_exists("words", "bg_ru", "TEXT")

# Проверим, есть ли в df эти колонки, если нет - добавим с пустыми значениями, чтобы избежать ошибок
for col in ["bg_image_en", "bg_image_de", "bg_image_ru"]:
    if col not in df.columns:
        df[col] = ''

# Добавление новых слов
added = 0
skipped = 0

for _, row in df.iterrows():
    cursor.execute("""
        SELECT COUNT(*)
        FROM words
        WHERE word_en = ?
          AND word_de = ?
          AND word_ru = ?
          AND category = ?
    """, (row['word_en'], row['word_de'], row['word_ru'], row['category']))

    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO words (
    word_en, word_de, word_ru, category, article_de, freq, difficulty, image_path,
    bg_en, bg_de, bg_ru
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row['word_en'],
            row['word_de'],
            row['word_ru'],
            row['category'],
            str(row['article_de']) if pd.notna(row.get('article_de')) else '',
            int(row['freq']) if pd.notna(row.get('freq')) else 0,
            str(row['difficulty']) if pd.notna(row.get('difficulty')) else '',
            str(row['image_path']) if pd.notna(row.get('image_path')) else '',
            str(row['bg_en']) if pd.notna(row.get('bg_en')) else '',  # <--- Изменить здесь
            str(row['bg_de']) if pd.notna(row.get('bg_de')) else '',  # <--- Изменить здесь
            str(row['bg_ru']) if pd.notna(row.get('bg_ru')) else ''  # <--- Изменить здесь
        ))
        added += 1
    else:
        skipped += 1

conn.commit()
conn.close()

print(f"✅ Добавлено новых слов в базу: {added}")
print(f"⏩ Пропущено (уже есть в базе): {skipped}")
