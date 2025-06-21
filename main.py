import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import random
import pygame
import re
from gtts import gTTS
import tempfile
import os
import threading
from PIL import Image, ImageTk
import time # Добавьте импорт time в начале файла


try:
    pygame.mixer.init()
except Exception as e:
    print(f"Ошибка инициализации Pygame Mixer: {e}")
    messagebox.showerror("Ошибка", f"Не удалось инициализировать звуковую систему: {e}")

# Инициализация pygame
pygame.init()
pygame.mixer.init()
card_frame = None  # глобально

# === Глобальные переменные ===
current_page = 0
cards_per_page = 8
all_raw_word_data = [] # <-- Изменено: будет хранить ВСЕ словари из БД
card_widgets = [] # <-- Хранит ТОЛЬКО ВИДЖЕТЫ Flashcard на текущей странице
current_active_card = None
feedback_label = None
answer_entry = None
answer_language_label = None
search_entry = None
DB_NAME = 'words.db' # <-- Добавлено
current_filtered_data = [] # <-- Добавлено
random_active_card = None
listen_mode_language = None

# Создание базы данных
def create_database():
    conn = sqlite3.connect(DB_NAME) # Изменено
    cursor = conn.cursor()
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS words
                   (
                       id INTEGER PRIMARY KEY,
                       word_en TEXT NOT NULL,
                       word_de TEXT NOT NULL,
                       word_ru TEXT NOT NULL,
                       category TEXT,
                       article_de TEXT,
                       freq INTEGER,
                       difficulty TEXT,
                       image_path TEXT, -- Эту колонку можно оставить для общей картинки слова, но не для языковых фонов
                       bg_en TEXT,
                       bg_de TEXT,
                       bg_ru TEXT
        )
    ''')
    conn.commit()
    conn.close()


create_database()


class Flashcard(tk.Frame):
    def __init__(self, master, word_data):
        super().__init__(master, width=300, height=200, bg='white', bd=2, relief='raised', highlightthickness=0)
        self.word_shown = False
        self.pack_propagate(False)
        self.word_data = word_data
        self.languages = ['word_en', 'word_de', 'word_ru']
        self.incorrect_attempts = 0
        self.is_revealed = False
        self.language_index = 2  # Начинаем с русского языка
        self.is_flipping = False
        self.is_playing_sound = False
        self.bg_img = None  # Переменная для хранения PhotoImage
        self.is_active = False  # <--- ДОБАВЬТЕ ЭТУ СТРОКУ

        # Canvas
        self.canvas = tk.Canvas(self, width=300, height=200, highlightthickness=0)
        self.canvas.pack()

        self.show_text_btn = tk.Button(self, text="Open", command=self.show_text)
        self.show_text_btn.place(x=0, y=0)
        self.show_text_btn.lift()
        self.text_background_id = None

        # Текст
        self.text_id = self.canvas.create_text(150, 100, text='',
                                               font=('Arial', 16, 'bold'),
                                               width=280, fill='white')


        self.sound_icon = ImageTk.PhotoImage(Image.open("icon/icons8-sound-48.png").resize((24, 24)))
        self.sound_btn = tk.Button(
            self, image=self.sound_icon, command=self.speak_word, bd=0, relief='flat',
            bg='SystemButtonFace', activebackground='SystemButtonFace', highlightthickness=0, overrelief='flat',
        )
        self.sound_btn.place(x=240, y=160)

        self.image_icon = ImageTk.PhotoImage(Image.open("icon/icons8-picture-48.png").resize((24, 24)))
        self.img_btn = tk.Button(self, image=self.image_icon, command=self.choose_language_background,
                                 bg='white', bd=0, font=('Arial', 12))
        self.img_btn.place(x=20, y=160)

        # Привязки
        self.canvas.bind("<Button-1>", self.on_card_click)
        self.bind("<Enter>", lambda e: self.config(relief='sunken'))
        self.bind("<Leave>", lambda e: self.config(relief='raised'))

        self._force_russian_initial_state()

    def reset_attempts(self):
        """Сбрасывает счетчик неверных попыток для этой карточки."""
        self.incorrect_attempts = 0

    def _create_text_background(self):
        """Создает полупрозрачную подложку для текста."""
        if self.text_background_id:
            self.canvas.delete(self.text_background_id)
        self.text_background_id = self.canvas.create_rectangle(
            20, 70, 280, 130,
            fill='black',
            stipple='gray50',
            outline=''
        )
        self.canvas.tag_lower(self.text_background_id, self.text_id)
        self.show_text_btn.lift()
        self.sound_btn.lift()
        self.img_btn.lift()

    def _remove_text_background(self):
        """Удаляет полупрозрачную подложку."""
        if self.text_background_id:
            self.canvas.delete(self.text_background_id)
            self.text_background_id = None

    def current_word(self):
        try:
            word = str(self.word_data[self.languages[self.language_index]]).strip()
            current_lang_key = self.languages[self.language_index]

            if current_lang_key == 'word_de':
                article = self.word_data.get('article_de', '').strip()
                # --- НОВОЕ ИЗМЕНЕНИЕ: Используем регулярное выражение ---
                # Если в строке артикля нет ни одной буквы (латинской или русской),
                # считаем, что артикля нет.
                if not re.search(r'[a-zA-Zа-яА-ЯёЁ]', article):
                    article = '' # Считаем его пустым
                # --- КОНЕЦ НОВОГО ИЗМЕНЕНИЯ ---
                if article:
                    return f"{article} {word}"
            elif current_lang_key == 'word_en':
                word_category = self.word_data.get('category', '').strip().lower()
                if word_category == 'глагол' and not word.lower().startswith("to "):
                    return f"to {word}"
            return word
        except KeyError:
            return "[Нет слова]"

    def on_card_click(self, event):
        """Обрабатывает клик по карточке: активирует ее и переворачивает."""
        self.activate_card()
        self.flip()

    def activate_card(self):
        global current_active_card, feedback_label, answer_entry, answer_language_label

        if current_active_card is not None and current_active_card != self:
            if current_active_card.winfo_exists():  # Проверка, что виджет еще существует
                current_active_card.deactivate_card()
            else:
                current_active_card = None

        self.is_active = True
        self.config(bd=2, relief='raised', highlightthickness=8, highlightbackground='lime green', highlightcolor='lime green')
        current_active_card = self

        self.reset_attempts()

        if feedback_label is not None: feedback_label.config(text="")
        if answer_entry is not None: answer_entry.delete(0, tk.END)

        current_lang_key_on_card = self.languages[self.language_index]
        display_text = ""
        if current_lang_key_on_card == 'word_en':
            display_text = "Введите на английском:"
        elif current_lang_key_on_card == 'word_de':
            display_text = "Введите на немецком:"
        elif current_lang_key_on_card == 'word_ru':
            display_text = "Введите на русском:"
        else:
            display_text = "Введите слово:"

        if answer_language_label is not None:
            answer_language_label.config(text=display_text)

    def deactivate_card(self):
        self.is_active = False
        self.config(bd=2, relief='raised', highlightbackground='SystemButtonFace',
                    highlightcolor='SystemButtonFace')

    def on_leave_card(self, event):
        if not self.is_active:
            self.config(relief='raised')

    # УДАЛЯЕМ set_background_by_language и flip_card, так как они дублируют логику и устарели
    # def flip_card(self, event=None):
    #     pass
    # def set_background_by_language(self):
    #     pass

    def flip(self, event=None):
        if not self.is_flipping and not self.is_playing_sound:
            self.is_flipping = True
            self.language_index = (self.language_index + 1) % 3
            current_lang_key = self.languages[self.language_index]

            # ТОЛЬКО русский язык всегда виден. Английский и Немецкий скрыты при перелистывании.
            if current_lang_key == 'word_ru':
                self.word_shown = True
            else: # 'word_en' ИЛИ 'word_de'
                self.word_shown = False # Текст будет скрыт для немецкого изначально

            self.update_card()
            self.is_flipping = False
            self.activate_card()

    def get_hint_text(self):
        """
        Генерирует строку-подсказку из подчеркиваний,
        соответствующую ожидаемому ответу (с артиклем/to, если применимо).
        """
        lang_key = self.languages[self.language_index]
        base_word = str(self.word_data.get(lang_key, '')).strip()

        if not base_word:
            return ""

        word_for_hint_length = base_word

        if lang_key == 'word_de':
            article = self.word_data.get('article_de', '').strip()
            # --- НОВОЕ ИЗМЕНЕНИЕ: Используем регулярное выражение для подсказки ---
            if not re.search(r'[a-zA-Zа-яА-ЯёЁ]', article):
                article = ''
            # --- КОНЕЦ НОВОГО ИЗМЕНЕНИЯ ---
            if article:
                word_for_hint_length = f"{article} {base_word}"
        elif lang_key == 'word_en':
            word_category = self.word_data.get('category', '').strip().lower()
            if word_category == 'глагол' and not base_word.lower().startswith("to "):
                word_for_hint_length = f"to {base_word}"

        hint_parts = []
        for part in word_for_hint_length.split():
            hint_parts.append('_' * len(part))
        return ' '.join(hint_parts)

    def hide_text(self):
        """Скрыть текст карточки и подложку."""
        self.word_shown = False
        self.canvas.itemconfig(self.text_id, text='')
        self.show_text_btn.config(state='normal') # Делаем кнопку "Open" активной при скрытии
        self._remove_text_background() # Удаляем подложку при скрытии текста

    def show_text(self):
        """Показать текст карточки и подложку (если не русский язык)."""
        self.word_shown = True
        self.canvas.itemconfig(self.text_id, text=self.current_word())

        lang_key = self.languages[self.language_index]
        if lang_key != 'word_ru': # Для EN и DE - создаём подложку и отключаем кнопку
            self._create_text_background()
            self.show_text_btn.config(state='disabled')
        else: # Для RU - убираем подложку (кнопка уже disabled)
            self._remove_text_background()

    def _force_russian_initial_state(self):
        """Принудительная установка начального состояния для русского языка."""
        self.language_index = 2
        self.word_shown = True  # Для русского текст всегда виден
        self.update_card() # update_card теперь устанавливает текст и фон
        # Здесь нет необходимости явно вызывать hide_text() или show_text_btn.config()
        # потому что update_card() обработает это на основе language_index и word_shown

    def update_card(self):
        lang_key = self.languages[self.language_index]
        current_bg_column_name = f'bg_{lang_key[-2:]}'
        saved_bg_path = self.word_data.get(current_bg_column_name)

        if saved_bg_path and os.path.exists(saved_bg_path):
            self.set_background(saved_bg_path)
        else:
            self.set_default_background(lang_key)

        # === ЛОГИКА УПРАВЛЕНИЯ ВИДИМОСТЬЮ ТЕКСТА И КНОПКОЙ "OPEN" ===
        if lang_key == 'word_ru':
            self.word_shown = True
            self.canvas.itemconfig(self.text_id, text=self.current_word(), fill='white')
            self.show_text_btn.config(state='disabled')
            self._remove_text_background()
        else: # Этот блок теперь для 'word_en' И 'word_de'
            if not self.word_shown:
                self.canvas.itemconfig(self.text_id, text='', fill='white')
                self.show_text_btn.config(state='normal')
                self._remove_text_background()
            else: # Если текст уже "открыт" (self.word_shown == True)
                self.canvas.itemconfig(self.text_id, text=self.current_word(), fill='white') # Покажет текст (с артиклем для DE)
                self.show_text_btn.config(state='disabled')
                self._create_text_background()

        # Логика для рамки активной карточки
        if self.is_active:
            self.config(bd=2, relief='raised', highlightthickness=4, highlightbackground='lime green', highlightcolor='lime green')
        else:
            self.config(bd=2, relief='raised', highlightthickness=0, highlightbackground='SystemButtonFace',
                        highlightcolor='SystemButtonFace')

    def set_background(self, image_path):
        try:
            img = Image.open(image_path).resize((300, 200), Image.Resampling.LANCZOS)
            self.bg_img = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor='nw', image=self.bg_img)

            # Пересоздаем текст, чтобы он был поверх изображения
            self.text_id = self.canvas.create_text(
                150, 100,
                text=self.current_word() if self.word_shown else '',
                font=('Arial', 16, 'bold'),
                width=280,
                fill='white',
                anchor='center'
            )
            # Поднимаем кнопки на передний план
            self.show_text_btn.lift()
            self.sound_btn.lift()
            self.img_btn.lift()

        except Exception as e:
            print(f"Ошибка загрузки изображения {image_path}: {e}")
            self.set_default_background(self.languages[self.language_index])

    def set_default_background(self, lang_key):
        colors = {
            'word_en': '#ADD8E6',  # Светло-голубой
            'word_de': '#FFCCCC',  # Светло-красный
            'word_ru': '#CCFFCC'  # Светло-зеленый
        }
        bg_color = colors.get(lang_key, 'gray')

        self.canvas.delete("all")
        self.canvas.create_rectangle(0, 0, 300, 200, fill=bg_color, outline="")

        # Пересоздаем текст
        self.text_id = self.canvas.create_text(
            150, 100,
            text=self.current_word() if self.word_shown else '',
            font=('Arial', 16, 'bold'),
            width=280,
            fill='white',
            anchor='center'
        )
        self.show_text_btn.lift()
        self.sound_btn.lift()
        self.img_btn.lift()

    def choose_language_background(self):
        filepath = filedialog.askopenfilename(
            title=f"Выберите фон для {self.languages[self.language_index]}",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg")]
        )
        if filepath:
            current_lang_key = self.languages[self.language_index]
            self.set_background(filepath)
            self.save_image_path(filepath, current_lang_key)
            # После установки фона, логика отображения текста обновится в update_card
            # Дополнительный вызов show_text/hide_text не нужен здесь,
            # так как update_card уже вызывает их по необходимости.
            # update_card() # Вызвать update_card, чтобы гарантировать правильное состояние текста

    def _gray_scale(self, alpha):
        return f'#%02x%02x%02x' % (alpha, alpha, alpha)

    def speak_word(self):
        lang_key = self.languages[self.language_index]
        text_to_speak = self.word_data.get(lang_key, '')

        print(f"Попытка озвучить: '{text_to_speak}' на языке: '{lang_key}'")
        if not text_to_speak:
            print(f"ОТЛАДКА: Нет текста для воспроизведения для языка {lang_key}.")
            return

        lang_code = ''
        if lang_key == 'word_en':
            lang_code = 'en'
        elif lang_key == 'word_de':
            lang_code = 'de'
        elif lang_key == 'word_ru':
            lang_code = 'ru'
        else:
            print(f"ОТЛАДКА: Неизвестный язык для воспроизведения: {lang_key}")
            return

        print(f"ОТЛАДКА: Текст для gTTS: '{text_to_speak}', Код языка: '{lang_code}'")

        try:
            tts = gTTS(text=text_to_speak, lang=lang_code)

            if hasattr(self, '_last_temp_mp3') and self._last_temp_mp3 and os.path.exists(self._last_temp_mp3):
                try:
                    os.remove(self._last_temp_mp3)
                    print(f"ОТЛАДКА: Успешно удален старый файл: {self._last_temp_mp3}")
                except OSError as e:
                    print(f"ОТЛАДКА: Повторная попытка удаления старого файла не удалась: {self._last_temp_mp3}: {e}")

            temp_file_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
            tts.save(temp_file_path)
            print(f"ОТЛАДКА: Файл MP3 сохранен по пути: {temp_file_path}")

            if not pygame.mixer.get_init():
                print("ОТЛАДКА: Pygame Mixer не инициализирован, пытаюсь инициализировать снова.")
                pygame.mixer.init()

            pygame.mixer.music.load(temp_file_path)

            pygame.mixer.music.play()


            self._last_temp_mp3 = temp_file_path

            # !!! ИЗМЕНЕНИЕ ЗДЕСЬ: УВЕЛИЧИВАЕМ ЗАДЕРЖКУ ПЕРЕД ВЫЗОВОМ stop_and_delete_mp3 !!!
            # Попробуйте 1000 мс (1 секунда) сначала. Если не поможет, попробуйте 2000 мс (2 секунды).
            root.after(1000, lambda: self.stop_and_delete_mp3(temp_file_path))

        except Exception as e:
            print(f"ОШИБКА ВОСПРОИЗВЕДЕНИЯ В speak_word(): {e}")
            messagebox.showerror("Ошибка воспроизведения", f"Не удалось воспроизвести звук: {e}")

    # --- НОВЫЙ МЕТОД В КЛАССЕ FLASHCARD ---
    def stop_and_delete_mp3(self, file_path):
        """Останавливает воспроизведение, выгружает музыку и затем пытается удалить временный MP3 файл."""
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                print(f"ОТЛАДКА: Музыка остановлена для файла: {file_path}")
            else:
                print(f"ОТЛАДКА: Музыка не воспроизводилась для файла: {file_path}, пропуск остановки.")

            # Дополнительно: выгружаем музыку, чтобы явно освободить ресурс
            pygame.mixer.music.unload()
            print(f"ОТЛАДКА: Музыка выгружена для файла: {file_path}")

            # Увеличенная задержка перед первой попыткой удаления
            root.after(500, lambda: self._perform_delete(file_path, attempts=0))  # Начинаем с 0 попыток
        except Exception as e:
            print(f"ОШИБКА В stop_and_delete_mp3(): {e}")

    # --- ИЗМЕНЕННЫЙ МЕТОД: _perform_delete() ---
    def _perform_delete(self, file_path, attempts=0, max_attempts=5, delay=100):
        """
        Внутренняя функция для выполнения удаления файла с повторными попытками.
        attempts: текущая попытка
        max_attempts: максимальное количество попыток
        delay: задержка в мс между попытками
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"ОТЛАДКА: Файл {file_path} успешно удален (попытка {attempts + 1}).")
            else:
                pass # print(f"ОТЛАДКА: Файл {file_path} не существует или уже удален.")
        except OSError as e:
            if attempts < max_attempts:
                print(f"ОШИБКА УДАЛЕНИЯ ФАЙЛА В _perform_delete() (попытка {attempts + 1}/{max_attempts}): {file_path}: {e}. Повторная попытка через {delay}мс.")
                root.after(delay, lambda: self._perform_delete(file_path, attempts + 1, max_attempts, delay * 2))
            else:
                print(f"ОШИБКА УДАЛЕНИЯ ФАЙЛА В _perform_delete(): {file_path}: {e}. Достигнуто максимальное количество попыток. Файл не удален.")

    def _generate_and_play_audio(self, current_lang, lang_map):
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3').name
            tts = gTTS(text=self.current_word(), lang=lang_map[current_lang])
            tts.save(temp_file)
            self.after(0, lambda: self._play_audio(temp_file))
        except Exception as e:
            self.after(0, lambda: self._handle_sound_error(e))

    def _play_audio(self, filename):
        try:
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            self._monitor_sound(filename)
        except Exception as e:
            self._handle_sound_error(e)

    def _monitor_sound(self, filename):
        if pygame.mixer.music.get_busy():
            self.after(100, lambda: self._monitor_sound(filename))
        else:
            self.after(0, self._reset_sound_controls)
            self._safe_delete(filename)

    def _reset_sound_controls(self):
        self.is_playing_sound = False
        self.sound_btn.config(state='normal')

    def _safe_delete(self, filename):
        try:
            if os.path.exists(filename):
                pygame.mixer.music.stop()
                os.remove(filename)
        except Exception as e:
            print(f"Ошибка удаления файла: {e}")

    def _handle_sound_error(self, error):
        self.is_playing_sound = False
        self.sound_btn.config(state='normal')
        messagebox.showerror("Ошибка", f"Ошибка аудио: {str(error)}")

    # УДАЛЯЕМ choose_image, так как choose_language_background его заменяет
    # def choose_image(self):
    #     pass

    def save_image_path(self, image_path, lang_key):
        conn = sqlite3.connect(DB_NAME) # Изменено
        cursor = conn.cursor()
        column_map = {
            'word_en': 'bg_en',
            'word_de': 'bg_de',
            'word_ru': 'bg_ru'
        }
        column_name = column_map.get(lang_key)

        if column_name:
            self.word_data[column_name] = image_path  # Обновляем данные в словаре word_data

            cursor.execute(f'''
                UPDATE words
                SET {column_name} = ?
                WHERE word_en = ? AND word_de = ? AND word_ru = ?
            ''', (image_path, self.word_data['word_en'], self.word_data['word_de'], self.word_data['word_ru']))
            conn.commit()
            print(f"Сохранен фон для {lang_key}: {image_path}")
        else:
            print(f"Неизвестный ключ языка: {lang_key}")
        conn.close()

    def get_expected_answers(self):
        expected_answers = []

        # --- НОВОЕ УСЛОВИЕ ДЛЯ РЕЖИМА "СЛУЧАЙНОЕ СЛОВО (DE)" ---
        # Если карточка НЕ показывается, и текущий язык - немецкий (language_index == 1),
        # то мы ожидаем немецкий ответ.
        if self.language_index == 1 and not self.word_shown:
            raw_answer_from_db = str(self.word_data.get('word_de', '')).strip().lower()
            article = self.word_data.get('article_de', '').strip().lower()

            if not re.search(r'[a-zA-Zа-яА-ЯёЁ]', article):
                article_for_logic = ''
            else:
                article_for_logic = article

            if article_for_logic:
                expected_answers.append(f"{article_for_logic} {raw_answer_from_db}")
            else:
                expected_answers.append(raw_answer_from_db)

            # В этом режиме нам не нужны другие языки, возвращаем сразу.
            return list(set(expected_answers))
        # --- КОНЕЦ НОВОГО УСЛОВИЯ ---

        # НИЖЕ СУЩЕСТВУЮЩАЯ ЛОГИКА (ОСТАВЛЯЕМ ЕЁ КАК ЕСТЬ, ОНА РАБОТАЕТ В ДРУГИХ СЦЕНАРИЯХ)
        # Эта часть выполняется, если не сработало новое условие выше (т.е. это не скрытое немецкое слово)

        # Определяем язык, который сейчас отображается на карточке
        current_lang_key_on_card = self.languages[self.language_index]

        raw_answer_from_db = str(self.word_data[current_lang_key_on_card]).strip().lower()

        # Логика для немецкого языка (с артиклями) - это для случая, когда НЕМЕЦКИЙ язык ПОКАЗЫВАЕТСЯ
        if current_lang_key_on_card == 'word_de':
            article = self.word_data.get('article_de', '').strip().lower()
            if not re.search(r'[a-zA-Zа-яА-ЯёЁ]', article):
                article_for_logic = ''
            else:
                article_for_logic = article

            if article_for_logic:
                expected_answers.append(f"{article_for_logic} {raw_answer_from_db}")
            else:
                expected_answers.append(raw_answer_from_db)

        # Логика для английского языка (с "to" для глаголов И множественными вариантами)
        elif current_lang_key_on_card == 'word_en':
            possible_english_answers = [ans.strip() for ans in raw_answer_from_db.split('/') if ans.strip()]
            word_category = self.word_data.get('category', '').strip().lower()

            for ans in possible_english_answers:
                expected_answers.append(ans)
                if word_category == 'глагол' and not ans.startswith("to "):
                    expected_answers.append(f"to {ans}")

        # Для русского или других языков
        else:
            expected_answers.append(raw_answer_from_db)

        return list(set(expected_answers))

# Загрузка карточек
def load_cards():
    global all_raw_word_data # Объявляем использование глобальной переменной

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, word_en, word_de, word_ru, category, article_de, freq, difficulty, image_path, bg_en, bg_de, bg_ru
        FROM words
    ''')
    fetched_data = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    conn.close()

    all_raw_word_data = [] # Очищаем и заполняем all_raw_word_data
    for row in fetched_data:
        all_raw_word_data.append(dict(zip(columns, row)))

    # Убедитесь, что combobox-ы установлены в "Все" и поле поиска пустое
    # перед вызовом filter_cards для первой загрузки
    level_var.set('Все')
    category_var.set('Все')
    if search_entry:
        search_entry.delete(0, tk.END)

    filter_cards() # Вызываем filter_cards для первоначального отображения
    print("Загружены все карточки по умолчанию.")


def play_random_de_word():
    global random_active_card, current_filtered_data, feedback_label, answer_entry, answer_language_label, current_active_card

    # 1. Проверяем, есть ли вообще отфильтрованные данные
    if not current_filtered_data:
        # Используйте messagebox.showinfo, убедитесь, что импорт messagebox есть: from tkinter import messagebox
        messagebox.showinfo("Информация", "Нет карточек для текущих фильтров. Измените фильтры или добавьте слова.")
        return

    # 2. Отбираем только немецкие слова из *ТЕКУЩИХ ОТФИЛЬТРОВАННЫХ ДАННЫХ*
    # Это важно: мы берем только из тех карточек, которые соответствуют текущим фильтрам
    de_words = [d for d in current_filtered_data if d.get('word_de') and d['word_de'].strip() != '']

    if not de_words:
        messagebox.showinfo("Информация", "Нет немецких слов среди отфильтрованных карточек для воспроизведения.")
        return

    # 3. Выбираем случайное немецкое слово из отобранного списка
    selected_word_data = random.choice(de_words)

    # 4. Находим соответствующую карточку-виджет среди уже отображенных на экране (если есть)
    found_card_widget = None
    for card_widget in card_widgets:
        # Сравниваем по уникальному ID слова из данных карточки
        if card_widget.word_data['id'] == selected_word_data['id']:
            found_card_widget = card_widget
            break

    # 5. Устанавливаем current_active_card для обработки ответа
    if found_card_widget:
        # Если карточка уже на экране, активируем ее
        random_active_card = found_card_widget
    else:
        # Если карточки нет на экране, создаем временную Flashcard для воспроизведения звука
        # и обработки ответа. Она не будет показана, но позволит использовать логику Flashcard.
        # Временная карточка будет привязана к cards_frame, но не будет гридоваться.
        random_active_card = Flashcard(cards_frame, selected_word_data)
        # Мы не пакуем/гридим ее, чтобы она не отображалась,
        # но ее методы (speak_word, get_expected_answers) будут работать.
        # Она будет заменена при следующем вызове play_random_de_word.

    # 6. Деактивируем предыдущую активную карточку, если она была
    if current_active_card is not None and current_active_card != random_active_card:
        if current_active_card.winfo_exists():  # Проверяем, существует ли виджет, прежде чем деактивировать
            current_active_card.deactivate_card()
        # Если виджет не существует (например, был уничтожен при пагинации), просто обнуляем
        else:
            current_active_card = None

    # 7. Теперь current_active_card становится нашей случайной карточкой
    current_active_card = random_active_card
    current_active_card.language_index = 1  # Устанавливаем немецкий язык (индекс 1 для 'word_de')
    current_active_card.word_shown = False  # Скрываем слово, чтобы пользователь вводил его
    current_active_card.update_card()  # Обновляем карточку (она будет показывать фон, но без текста)
    current_active_card.activate_card()  # Активируем карточку, чтобы она выделялась

    # 8. Воспроизводим немецкое слово
    current_active_card.speak_word()

    # 9. Очищаем поле ввода и настраиваем лейбл для ответа
    if feedback_label is not None: feedback_label.config(text="")
    if answer_entry is not None: answer_entry.delete(0, tk.END)
    if answer_language_label is not None:
        answer_language_label.config(text="Введите услышанное слово (DE):")

def filter_cards():
    global all_raw_word_data, current_filtered_data, current_page, cards_per_page, search_entry, card_widgets

    # 1. Очищаем предыдущие виджеты на экране
    clear_cards() # Используем уже существующую функцию для очистки виджетов

    # Удаляем сообщение "Нет карточек", если оно есть (это также часть clear_cards, но на всякий случай)
    for child in cards_frame.winfo_children():
        if isinstance(child, tk.Label) and child.cget("text") == "Нет карточек для выбранных параметров":
            child.destroy()

    # 2. Получаем параметры фильтрации
    category_filter_val = category_var.get()
    level_filter_val = level_var.get()
    # Проверяем, что search_entry существует, прежде чем получить его значение
    search_term = search_entry.get().strip().lower() if search_entry else ""

    # 3. Фильтруем данные из all_raw_word_data (загруженных один раз при старте)
    current_filtered_data = []
    for word_data_dict in all_raw_word_data: # Итерируемся по ВСЕМ сырым данным
        match = True

        # Фильтрация по категории
        if category_filter_val != 'Все' and word_data_dict.get('category', '') != category_filter_val:
            match = False

        # Фильтрация по уровню сложности
        if level_filter_val != 'Все' and word_data_dict.get('difficulty', '') != level_filter_val:
            match = False

        # Фильтрация по поисковому запросу
        if search_term:
            found_in_word = False
            for lang_key in ['word_en', 'word_de', 'word_ru']:
                # Проверяем, что значение существует и является строкой
                word_val = word_data_dict.get(lang_key, '')
                if isinstance(word_val, str) and search_term in word_val.lower():
                    found_in_word = True
                    break
            if not found_in_word:
                match = False

        if match:
            current_filtered_data.append(word_data_dict)

    random.shuffle(current_filtered_data) # Перемешиваем отфильтрованные данные
    current_page = 0 # Всегда начинаем с первой страницы при новой фильтрации

    show_page(current_page) # Отображаем первую страницу отфильтрованных карточек

    # Если после фильтрации карточек нет, показываем сообщение
    if not current_filtered_data:
        tk.Label(cards_frame, text="Нет карточек для выбранных параметров").grid(row=0, column=0, columnspan=4, pady=50)

    update_pagination_buttons() # Обновляем состояние кнопок пагинации


def load_next_cards():  # Эта функция не используется, можете удалить
    for widget in card_frame.winfo_children():
        widget.destroy()

    conn = sqlite3.connect("words.db")
    c = conn.cursor()
    c.execute("SELECT * FROM words")
    words = c.fetchall()
    conn.close()

    if words:
        word = random.choice(words)
        columns = ['id', 'word_en', 'word_de', 'word_ru', 'category', 'article_de', 'freq',
                   'difficulty', 'image_path', 'bg_en', 'bg_de', 'bg_ru']
        word_dict = dict(zip(columns, word))

        new_card = Flashcard(card_frame, word_dict)
        new_card.pack(pady=10)
    else:
        messagebox.showinfo("Информация", "Нет доступных карточек.")


def show_page(page_num):
    global current_page, card_widgets # Объявляем использование глобальной card_widgets

    # Сначала уничтожаем все текущие виджеты Flashcard на экране
    for widget in card_widgets:
        widget.destroy()
    card_widgets.clear() # Очищаем список после уничтожения виджетов

    # Удаляем сообщение "Нет карточек", если оно есть (на случай если оно осталось после фильтрации)
    for child in cards_frame.winfo_children():
        if isinstance(child, tk.Label) and child.cget("text") == "Нет карточек для выбранных параметров":
            child.destroy()

    start = page_num * cards_per_page
    end = start + cards_per_page

    # Используем current_filtered_data для отображения
    cards_to_show_data = current_filtered_data[start:end]

    for idx, card_data_dict in enumerate(cards_to_show_data):
        card = Flashcard(cards_frame, card_data_dict)
        row, col = divmod(idx, 4)
        card.grid(row=row, column=col, padx=10, pady=10)
        card_widgets.append(card) # Добавляем созданный виджет в card_widgets

    current_page = page_num
    update_pagination_buttons() # Обновляем кнопки пагинации


def update_pagination_buttons():
    global prev_btn, next_btn  # Объявляем, что используем глобальные переменные для кнопок

    # prev_btn и next_btn будут созданы позже в коде, поэтому проверяем их существование
    # перед тем как пытаться изменить их состояние.
    if prev_btn.winfo_exists():  # Проверяем, существует ли виджет
        if current_page == 0:
            prev_btn.config(state='disabled')
        else:
            prev_btn.config(state='normal')

    if next_btn.winfo_exists():  # Проверяем, существует ли виджет
        if (current_page + 1) * cards_per_page >= len(current_filtered_data):  # Используем current_filtered_data
            next_btn.config(state='disabled')
        else:
            next_btn.config(state='normal')


def add_background_columns():  # Эта функция, вероятно, уже отработала
    conn = sqlite3.connect(DB_NAME) # Изменено
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE words ADD COLUMN bg_en TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE words ADD COLUMN bg_de TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE words ADD COLUMN bg_ru TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


add_background_columns()

# Интерфейс
root = tk.Tk()
root.title("Языковые карточки")
root.geometry("1400x900")

control_frame = tk.Frame(root)
control_frame.pack(pady=10)

nav_frame = tk.Frame(root)
nav_frame.pack(pady=10)


def next_page():
    if (current_page + 1) * cards_per_page < len(current_filtered_data):  # ИЗМЕНЕНО
        show_page(current_page + 1)


def prev_page():
    # Эта функция уже использует current_page, но косвенно через show_page.
    # Тем не менее, она должна быть согласована с пагинацией по current_filtered_data.
    # Здесь прямое изменение all_cards не требуется, но для ясности:
    if current_page > 0:  # Это условие корректно
        show_page(current_page - 1)


prev_btn = ttk.Button(nav_frame, text="← Предыдущие", command=prev_page)
prev_btn.grid(row=0, column=0, padx=10)

next_btn = ttk.Button(nav_frame, text="Следующие →", command=next_page)
next_btn.grid(row=0, column=1, padx=10)

card_frame = tk.Frame(root)  # Эта переменная `card_frame` не используется, можете удалить
card_frame.pack(pady=10)

random_de_word_btn = tk.Button(control_frame, text="Случайное слово (DE)", command=play_random_de_word, bg='#87CEEB', fg='white')
random_de_word_btn.grid(row=0, column=7, padx=10) # Новая кнопка



def clear_cards():
    global current_active_card, card_widgets
    for card_widget in card_widgets:
        if card_widget == current_active_card:
            current_active_card = None
        card_widget.destroy()
    card_widgets.clear() # Очищаем список после уничтожения
    # Также очищаем все Label, если было сообщение "Нет карточек"
    for child in cards_frame.winfo_children():
        if isinstance(child, tk.Label) and child.cget("text") == "Нет карточек для выбранных параметров":
            child.destroy()


levels = ['Все'] + ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
categories = ['Все'] + ['Глагол', 'Существительное', 'Прилагательное', 'Предлог', 'Наречие', 'Вопросительное слово']

tk.Label(control_frame, text='Уровень:').grid(row=0, column=0, padx=5)
level_var = tk.StringVar()
level_menu = ttk.Combobox(control_frame, textvariable=level_var, values=levels, state='readonly', width=10)
level_menu.grid(row=0, column=1, padx=5)

tk.Label(control_frame, text='Категория:').grid(row=0, column=2, padx=5)
category_var = tk.StringVar()
category_menu = ttk.Combobox(control_frame, textvariable=category_var, values=categories, state='readonly', width=15)
category_menu.grid(row=0, column=3, padx=5)

load_btn = tk.Button(control_frame, text="Загрузить карточки", command=filter_cards, bg='#4CAF50', fg='white') # Изменено
load_btn.grid(row=0, column=4, padx=10)

level_menu = ttk.Combobox(control_frame, textvariable=level_var, values=levels, state='readonly', width=10)
level_menu.grid(row=0, column=1, padx=5)
level_menu.bind("<<ComboboxSelected>>", lambda event: filter_cards())

category_menu = ttk.Combobox(control_frame, textvariable=category_var, values=categories, state='readonly', width=15)
category_menu.grid(row=0, column=3, padx=5)
category_menu.bind("<<ComboboxSelected>>", lambda event: filter_cards())

cards_frame = tk.Frame(root)
cards_frame.pack(pady=20)
cards_frame.grid_columnconfigure(0, weight=1)
cards_frame.grid_columnconfigure(1, weight=1)
cards_frame.grid_columnconfigure(2, weight=1)
cards_frame.grid_columnconfigure(3, weight=1)

check_frame = tk.Frame(root)
check_frame.pack(pady=10)

answer_language_label = tk.Label(check_frame, text="...", font=('Arial', 12))
answer_language_label.pack(side=tk.LEFT, padx=5)

answer_entry = tk.Entry(check_frame, width=40, font=('Arial', 14))
answer_entry.pack(side=tk.LEFT, padx=5)
answer_entry.bind("<Return>", lambda event=None: check_spelling())

check_button = ttk.Button(check_frame, text="Проверить", command=lambda: check_spelling())
check_button.pack(side=tk.LEFT, padx=5)

feedback_label = tk.Label(check_frame, text="", font=('Arial', 12, 'bold'))
feedback_label.pack(side=tk.LEFT, padx=5)

# --- НОВЫЙ БЛОК: Поле для поиска по словам (используем grid!) ---
search_label = tk.Label(control_frame, text="Поиск:", font=('Arial', 12))
search_label.grid(row=0, column=5, padx=5, pady=5) # Размещаем в той же строке, но в следующем столбце


search_entry = tk.Entry(control_frame, width=20, font=('Arial', 12))
search_entry.grid(row=0, column=6, padx=5, pady=5) # Еще в следующем столбце

# Привязываем событие "отпускание клавиши" к функции filter_cards
search_entry.bind('<KeyRelease>', lambda event: filter_cards())


def check_spelling():
    global current_active_card, feedback_label, answer_entry, answer_language_label, random_active_card, current_page, card_widgets, current_filtered_data  # Добавил current_filtered_data

    if current_active_card is None:
        messagebox.showinfo("Ошибка",
                            "Сначала выберите карточку, кликнув по ней, или используйте 'Случайное слово (DE)'.")
        return

    user_answer = answer_entry.get().strip().lower()
    expected_answers = current_active_card.get_expected_answers()

    if not expected_answers:
        feedback_label.config(text="Нет ожидаемых ответов для этой карточки.", fg="orange")
        answer_entry.delete(0, tk.END)
        return

    answer_entry.delete(0, tk.END)  # Очищаем поле ввода после каждой попытки

    is_random_mode_card = (current_active_card == random_active_card)

    # Сохраняем ID слова, которое было угадано/неугадно
    processed_word_id = current_active_card.word_data['id']

    if user_answer in expected_answers:
        feedback_label.config(text="Правильно!", fg="green")
        current_active_card.reset_attempts()

        # --- Логика для случайной карточки (угадали) ---
        if is_random_mode_card:
            # Уничтожаем временную карточку, если она была (и не отображалась)
            if random_active_card is not None and random_active_card not in card_widgets:
                random_active_card.destroy()
            random_active_card = None  # Сбрасываем random_active_card

            answer_language_label.config(text="Введите слово:")  # Возвращаем стандартный лейбл
            current_active_card = None  # Сбрасываем текущую активную карточку (важно перед show_page)

            # !!! НОВОЕ: Находим страницу угаданного слова и переходим на нее !!!
            target_index = -1
            for idx, data_dict in enumerate(current_filtered_data):
                if data_dict['id'] == processed_word_id:
                    target_index = idx
                    break

            if target_index != -1:
                target_page = target_index // cards_per_page
                show_page(target_page)  # Переходим на страницу с угаданным словом
            else:
                # Если слово почему-то не найдено в current_filtered_data (очень маловероятно),
                # просто перезагружаем текущую страницу.
                show_page(current_page)

                # Ищем угаданную карточку среди ТЕКУЩИХ отображенных виджетов (card_widgets)
            # Она теперь гарантированно на экране, если target_page был найден
            for card_widget in card_widgets:
                if card_widget.word_data['id'] == processed_word_id:
                    current_active_card = card_widget  # Делаем ее активной для дальнейших кликов
                    current_active_card.language_index = 1  # Показываем немецкое слово
                    current_active_card.word_shown = True  # Показываем текст
                    current_active_card.update_card()  # Обновляем отображение
                    current_active_card.deactivate_card()  # Снимаем синюю рамку
                    break  # Найдено, можно выйти из цикла

        # --- Логика для обычной карточки (не из режима случайного слова, угадали) ---
        else:
            current_active_card.word_shown = True  # Показываем слово
            current_active_card.update_card()  # Обновляем отображение
            current_active_card.deactivate_card()  # Деактивируем карточку
            current_active_card = None  # Сбрасываем текущую активную карточку

    else:  # Если ответ НЕправильный
        current_active_card.incorrect_attempts += 1
        attempts_left = 3 - current_active_card.incorrect_attempts

        if attempts_left <= 0:
            all_correct_str = ", ".join(expected_answers)
            feedback_label.config(
                text=f"Неправильно. Правильный ответ: '{all_correct_str}'. Ответ показан на карточке.", fg="red")
            current_active_card.reset_attempts()

            # --- Логика для случайной карточки (исчерпали попытки) ---
            if is_random_mode_card:
                # Уничтожаем временную карточку, если она была (и не отображалась)
                if random_active_card is not None and random_active_card not in card_widgets:
                    random_active_card.destroy()
                random_active_card = None  # Сбрасываем random_active_card

                answer_language_label.config(text="Введите слово:")  # Возвращаем стандартный лейбл
                current_active_card = None  # Сбрасываем текущую активную карточку (важно перед show_page)

                # !!! НОВОЕ: Находим страницу слова, по которому исчерпаны попытки, и переходим на нее !!!
                target_index = -1
                for idx, data_dict in enumerate(current_filtered_data):
                    if data_dict['id'] == processed_word_id:
                        target_index = idx
                        break

                if target_index != -1:
                    target_page = target_index // cards_per_page
                    show_page(target_page)  # Переходим на страницу со словом
                else:
                    show_page(current_page)

                    # Ищем карточку среди ТЕКУЩИХ отображенных виджетов (card_widgets)
                for card_widget in card_widgets:
                    if card_widget.word_data['id'] == processed_word_id:
                        current_active_card = card_widget  # Делаем ее активной
                        current_active_card.language_index = 1  # Показываем немецкое слово
                        current_active_card.word_shown = True  # Показываем текст
                        current_active_card.update_card()  # Обновляем отображение
                        current_active_card.deactivate_card()  # Снимаем синюю рамку
                        break  # Найдено, можно выйти из цикла

            # --- Логика для обычной карточки (не из режима случайного слова, исчерпали попытки) ---
            else:
                current_active_card.word_shown = True  # Показываем слово
                current_active_card.update_card()  # Обновляем отображение
                current_active_card.deactivate_card()  # Деактивируем карточку
                current_active_card = None  # Сбрасываем текущую активную карточку

        else:
            feedback_label.config(text=f"Неправильно. Осталось попыток: {attempts_left}", fg="orange")


load_cards()

root.mainloop()