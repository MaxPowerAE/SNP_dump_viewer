# SNP Dump Viewer

SNP Dump Viewer — это локальное Streamlit-приложение для просмотра SQLite-дампа SNPedia-Scraper.

Приложение позволяет:
- загрузить файл базы (`.sqlite`, `.db`, `.sqlite3`),
- найти SNP по `rsid` (например, `rs7412`),
- увидеть метаданные записи,
- получить список wiki-ссылок из контента,
- прочитать контент по секциям.

---

## 1. Требования

- Python **3.10+** (рекомендуется 3.11)
- `pip`
- локальный SQLite-дамп с таблицей `snps`

Ожидаемая схема таблицы:
- `rsid`
- `content`
- `scraped_at`
- `attribution`

---

## 2. Установка

### 2.1. Клонирование репозитория

```bash
git clone <URL_ВАШЕГО_РЕПО>
cd SNP_dump_viewer
```

### 2.2. Создание и активация виртуального окружения

#### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2.3. Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Запуск приложения

Из корня проекта выполните:

```bash
streamlit run app.py
```

После запуска Streamlit выведет локальный URL, обычно:

- `http://localhost:8501`

Откройте этот адрес в браузере.

---

## 4. Как пользоваться

1. В интерфейсе нажмите **«Локальный файл дампа (.sqlite/.db)»** и выберите файл базы.
2. В поле ввода введите `rsid`, например: `rs7412`.
3. Приложение покажет:
   - похожие `rsid` (подсказки),
   - метаданные (`scraped_at`, `attribution`),
   - найденные wiki-ссылки,
   - секции контента в раскрывающихся блоках.

---

## 5. Запуск тестов и линтера

> Полезно для проверки перед коммитом.

### Тесты

```bash
pytest
```

### Линтер (ruff)

```bash
ruff check .
```

---

## 6. Частые проблемы

### Приложение не стартует

- Убедитесь, что активировано виртуальное окружение.
- Проверьте, что зависимости установлены: `pip install -r requirements.txt`.

### Ошибка чтения базы

- Проверьте, что выбран корректный файл SQLite.
- Проверьте наличие таблицы `snps` и нужных колонок.

### SNP не находится

- Убедитесь, что `rsid` присутствует в вашей базе.
- Попробуйте частичный ввод, чтобы увидеть подсказки похожих `rsid`.

---

## 7. Структура проекта

- `app.py` — Streamlit UI и сценарий работы приложения.
- `core.py` — функции чтения БД и обработки wiki-контента.
- `tests/test_app.py` — unit-тесты для функций обработки текста.
- `requirements.txt` — зависимости проекта.

---

## 8. Короткий сценарий (быстрый старт)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```



## 9. Скрипт статистики по `match_progress*.json`

Добавлен отдельный CLI-скрипт:

```bash
python scripts/match_progress_stats.py
```

По умолчанию он ищет самый свежий файл в `.progress/` и печатает краткую таблицу со статистикой.

Можно передать явный файл:

```bash
python scripts/match_progress_stats.py .progress/match_progress_xxx.json
```

