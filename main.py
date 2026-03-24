import os
import sqlite3
import shutil
import datetime
import random
from tkinter import Tk, Frame, Label, Entry, Button, Toplevel, StringVar, LEFT, RIGHT, TOP, BOTTOM, BOTH, X, Y, W, END, \
    VERTICAL
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import pandas as pd

# КОНСТАНТЫ ПРИЛОЖЕНИЯ

DATABASE_NAME = "shoes.db"
FOLDER_RESOURCES = "resources"
FOLDER_IMAGES = "images"
DEFAULT_IMAGE_NAME = "picture.png"

# Цветовая схема интерфейса
COLOR_BACKGROUND_MAIN = "#FFFFFF"
COLOR_BACKGROUND_SECONDARY = "#7FFF00"
COLOR_ACCENT = "#00FA9A"
COLOR_DISCOUNT_HIGHLIGHT = "#2E8B57"
COLOR_OUT_OF_STOCK = "#ADD8E6"
COLOR_DELETE_BUTTON = "#FFA07A"

# ФУНКЦИИ РАБОТЫ С БАЗОЙ ДАННЫХ

def initialize_database():
    """
    Инициализация структуры базы данных.
    Создаёт таблицы и импортирует данные при первом запуске.
    """
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS manufacturers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            full_name TEXT NOT NULL,
            login TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pickup_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            unit TEXT NOT NULL,
            price REAL NOT NULL,
            supplier_id INTEGER,
            manufacturer_id INTEGER,
            category_id INTEGER,
            discount INTEGER DEFAULT 0,
            stock INTEGER NOT NULL,
            description TEXT,
            image_path TEXT,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
            FOREIGN KEY (manufacturer_id) REFERENCES manufacturers(id),
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT UNIQUE NOT NULL,
            order_date TEXT NOT NULL,
            delivery_date TEXT,
            pickup_point_id INTEGER,
            user_id INTEGER,
            pickup_code TEXT,
            status TEXT NOT NULL,
            FOREIGN KEY (pickup_point_id) REFERENCES pickup_points(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_article TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY (product_article) REFERENCES products(article)
        );
    ''')

    connection.commit()

    # Проверка наличия пользователей
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    if user_count == 0:
        _import_initial_data(connection)

    connection.close()


def _import_initial_data(database_connection):
    """
    Импорт начальных данных из Excel-файлов.
    """
    cursor = database_connection.cursor()

    # Импорт категорий, производителей, поставщиков
    products_dataframe = pd.read_excel(os.path.join(FOLDER_RESOURCES, "Tovar.xlsx"))

    unique_categories = products_dataframe["Категория товара"].dropna().unique()
    unique_manufacturers = products_dataframe["Производитель"].dropna().unique()
    unique_suppliers = products_dataframe["Поставщик"].dropna().unique()

    for category_name in unique_categories:
        cursor.execute(
            "INSERT OR IGNORE INTO categories (name) VALUES (?)",
            (category_name,)
        )

    for manufacturer_name in unique_manufacturers:
        cursor.execute(
            "INSERT OR IGNORE INTO manufacturers (name) VALUES (?)",
            (manufacturer_name,)
        )

    for supplier_name in unique_suppliers:
        cursor.execute(
            "INSERT OR IGNORE INTO suppliers (name) VALUES (?)",
            (supplier_name,)
        )

    database_connection.commit()

    # Импорт пунктов выдачи
    pickup_dataframe = pd.read_excel(
        os.path.join(FOLDER_RESOURCES, "Пункты выдачи_import.xlsx"),
        header=None
    )

    for address_row in pickup_dataframe[0]:
        cursor.execute(
            "INSERT OR IGNORE INTO pickup_points (address) VALUES (?)",
            (address_row,)
        )

    database_connection.commit()

    # Импорт пользователей
    users_dataframe = pd.read_excel(
        os.path.join(FOLDER_RESOURCES, "user_import.xlsx")
    )

    for _, user_row in users_dataframe.iterrows():
        cursor.execute(
            "INSERT INTO users (role, full_name, login, password) VALUES (?,?,?,?)",
            (
                user_row["Роль сотрудника "],
                user_row["ФИО "],
                user_row["Логин "],
                user_row["Пароль "]
            )
        )

    database_connection.commit()

    # Создание словарей для связей
    category_mapping = {
        name: id_
        for id_, name in cursor.execute("SELECT id, name FROM categories")
    }
    manufacturer_mapping = {
        name: id_
        for id_, name in cursor.execute("SELECT id, name FROM manufacturers")
    }
    supplier_mapping = {
        name: id_
        for id_, name in cursor.execute("SELECT id, name FROM suppliers")
    }

    # Создание папки для изображений
    if not os.path.exists(FOLDER_IMAGES):
        os.makedirs(FOLDER_IMAGES)

    # Импорт товаров
    for _, product_row in products_dataframe.iterrows():
        _process_product_row(
            cursor,
            product_row,
            category_mapping,
            manufacturer_mapping,
            supplier_mapping
        )

    database_connection.commit()

    # Импорт заказов
    _import_orders(database_connection, cursor)

    print("Данные успешно импортированы в базу данных.")


def _process_product_row(cursor, row, cat_map, man_map, sup_map):
    """
    Обработка одной строки товара при импорте.
    """
    article = row["Артикул "]
    product_name = row["Наименование товара "]
    unit = row["Единица измерения "]
    price_value = float(row["Цена "])
    supplier_name = row["Поставщик "]
    manufacturer_name = row["Производитель "]
    category_name = row["Категория товара "]

    discount_value = (
        int(row["Действующая скидка "])
        if pd.notna(row["Действующая скидка "])
        else 0
    )

    stock_value = (
        int(row["Кол-во на складе "])
        if pd.notna(row["Кол-во на складе "])
        else 0
    )

    description_text = (
        row["Описание товара "]
        if pd.notna(row["Описание товара "])
        else " "
    )

    image_filename = row["Фото "] if pd.notna(row["Фото "]) else None

    # Копирование изображения
    image_destination_path = None
    if image_filename and os.path.exists(os.path.join(FOLDER_RESOURCES, image_filename)):
        source_path = os.path.join(FOLDER_RESOURCES, image_filename)
        destination_path = os.path.join(FOLDER_IMAGES, image_filename)

        if not os.path.exists(destination_path):
            shutil.copy(source_path, destination_path)

        image_destination_path = os.path.join(FOLDER_IMAGES, image_filename)

    cursor.execute('''
        INSERT INTO products 
        (article, name, unit, price, supplier_id, manufacturer_id, category_id, 
         discount, stock, description, image_path)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        article, product_name, unit, price_value,
        sup_map.get(supplier_name),
        man_map.get(manufacturer_name),
        cat_map.get(category_name),
        discount_value, stock_value, description_text, image_destination_path
    ))


def _import_orders(database_connection, cursor):
    """
    Импорт данных о заказах из Excel-файла.
    """
    orders_dataframe = pd.read_excel(
        os.path.join(FOLDER_RESOURCES, "Заказ_import.xlsx")
    )

    user_mapping = {
        name: id_
        for id_, name in cursor.execute("SELECT id, full_name FROM users")
    }

    pickup_mapping = {
        addr: id_
        for id_, addr in cursor.execute("SELECT id, address FROM pickup_points")
    }

    for _, order_row in orders_dataframe.iterrows():
        _process_order_row(
            cursor, database_connection, order_row,
            user_mapping, pickup_mapping
        )

    database_connection.commit()


def _process_order_row(cursor, conn, row, user_map, pp_map):
    """
    Обработка одной строки заказа при импорте.
    """
    order_number = row["Номер заказа "]
    order_date_raw = row["Дата заказа "]

    if pd.isna(order_date_raw):
        print(f"Пропущена строка заказа {order_number}: нет даты заказа")
        return

    # Парсинг даты заказа
    try:
        if isinstance(order_date_raw, str):
            order_date = datetime.datetime.strptime(
                order_date_raw, "%d.%m.%Y"
            ).date()
        else:
            order_date = pd.to_datetime(order_date_raw).date()
    except ValueError:
        print(f"Ошибка в дате заказа {order_date_raw} для заказа {order_number}")
        return

    # Парсинг даты доставки
    delivery_raw = row["Дата доставки "]
    delivery_date = None

    if not pd.isna(delivery_raw):
        try:
            if isinstance(delivery_raw, str):
                delivery_date = datetime.datetime.strptime(
                    delivery_raw, "%d.%m.%Y"
                ).date()
            else:
                delivery_date = pd.to_datetime(delivery_raw).date()
        except ValueError:
            print(f"Ошибка в дате доставки для заказа {order_number}")

    address_value = row["Адрес пункта выдачи "]
    user_full_name = row["ФИО авторизированного клиента "]
    pickup_code_value = row["Код для получения "]
    status_value = row["Статус заказа "]

    # Получение или создание пункта выдачи
    if address_value in pp_map:
        pickup_id = pp_map[address_value]
    else:
        cursor.execute(
            "INSERT INTO pickup_points (address) VALUES (?)",
            (address_value,)
        )
        conn.commit()
        pickup_id = cursor.lastrowid
        pp_map[address_value] = pickup_id

    # Поиск пользователя
    user_id = user_map.get(user_full_name)
    if user_id is None:
        print(f"Пропущен заказ {order_number}: пользователь {user_full_name} не найден")
        return

    # Вставка заказа
    cursor.execute('''
        INSERT INTO orders 
        (order_number, order_date, delivery_date, pickup_point_id, 
         user_id, pickup_code, status)
        VALUES (?,?,?,?,?,?,?)
    ''', (
        order_number, order_date, delivery_date, pickup_id,
        user_id, pickup_code_value, status_value
    ))

    order_id = cursor.lastrowid

    # Обработка позиций заказа
    items_string = row["Артикул заказа "]
    if pd.isna(items_string):
        return

    items_list = items_string.split(", ")

    for idx in range(0, len(items_list), 2):
        try:
            article_item = items_list[idx]
            quantity_item = int(items_list[idx + 1])

            cursor.execute(
                "INSERT INTO order_items (order_id, product_article, quantity) VALUES (?,?,?)",
                (order_id, article_item, quantity_item)
            )
        except (IndexError, ValueError):
            print(f"Ошибка в разборе артикулов для заказа {order_number}")
            continue

# КЛАССЫ ГРАФИЧЕСКОГО ИНТЕРФЕЙСА

class ShoeStoreApplication:
    """
    Главный класс приложения обувного магазина.
    Управляет навигацией между окнами и хранит состояние пользователя.
    """

    def __init__(self):
        self.main_window = Tk()
        self.main_window.title("Обувь - магазин обуви")
        self.main_window.geometry("1200x600")

        # Установка иконки приложения
        icon_file_path = os.path.join(FOLDER_RESOURCES, "icon.ico")
        if os.path.exists(icon_file_path):
            self.main_window.iconbitmap(icon_file_path)

        self.active_user = None
        self._display_login_screen()

    def _display_login_screen(self):
        """Отображение окна авторизации."""
        self._clear_all_widgets()
        AuthenticationWindow(self.main_window, self)

    def _display_catalog_screen(self):
        """Отображение каталога товаров."""
        self._clear_all_widgets()
        ProductCatalogWindow(self.main_window, self)

    def _display_orders_screen(self):
        """Отображение списка заказов."""
        self._clear_all_widgets()
        OrdersManagementWindow(self.main_window, self)

    def _clear_all_widgets(self):
        """Удаление всех виджетов из главного окна."""
        for widget_item in self.main_window.winfo_children():
            widget_item.destroy()

    def start(self):
        """Запуск главного цикла приложения."""
        self.main_window.mainloop()


class AuthenticationWindow:
    """
    Окно авторизации пользователей.
    Поддерживает вход по логину/паролю и гостевой режим.
    """

    def __init__(self, parent_window, application):
        self.application = application
        self.container = Frame(parent_window, bg=COLOR_BACKGROUND_MAIN)
        self.container.pack(fill=BOTH, expand=True)

        # Загрузка логотипа
        logo_file = os.path.join(FOLDER_RESOURCES, "logo.png")
        if os.path.exists(logo_file):
            try:
                logo_image = Image.open(logo_file)
                logo_image = logo_image.resize((200, 100), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(logo_image)
                Label(self.container, image=self.logo_photo, bg=COLOR_BACKGROUND_MAIN).pack(pady=10)
            except Exception:
                pass

        # Поле логина
        Label(
            self.container,
            text="Логин",
            font=("Times New Roman", 12),
            bg=COLOR_BACKGROUND_MAIN
        ).pack(pady=5)

        self.entry_login = Entry(self.container, font=("Times New Roman", 12))
        self.entry_login.pack(pady=5)

        # Поле пароля
        Label(
            self.container,
            text="Пароль",
            font=("Times New Roman", 12),
            bg=COLOR_BACKGROUND_MAIN
        ).pack(pady=5)

        self.entry_password = Entry(
            self.container,
            show="*",
            font=("Times New Roman", 12)
        )
        self.entry_password.pack(pady=5)

        # Кнопки входа
        Button(
            self.container,
            text="Войти",
            command=self._authenticate_user,
            bg=COLOR_ACCENT,
            font=("Times New Roman", 12)
        ).pack(pady=5)

        Button(
            self.container,
            text="Войти как гость",
            command=self._enter_guest_mode,
            bg=COLOR_BACKGROUND_SECONDARY,
            font=("Times New Roman", 12)
        ).pack(pady=5)

    def _authenticate_user(self):
        """Проверка учётных данных пользователя."""
        login_value = self.entry_login.get()
        password_value = self.entry_password.get()

        connection = sqlite3.connect(DATABASE_NAME)
        cursor = connection.cursor()

        cursor.execute(
            "SELECT id, role, full_name FROM users WHERE login=? AND password=?",
            (login_value, password_value)
        )

        user_data = cursor.fetchone()
        connection.close()

        if user_data:
            self.application.active_user = {
                "id": user_data[0],
                "role": user_data[1],
                "full_name": user_data[2]
            }
            self.application._display_catalog_screen()
        else:
            messagebox.showerror("Ошибка", "Неверный логин или пароль")

    def _enter_guest_mode(self):
        """Вход в систему в режиме гостя."""
        self.application.active_user = {
            "id": None,
            "role": "guest",
            "full_name": "Гость"
        }
        self.application._display_catalog_screen()


class ProductCatalogWindow:
    """
    Окно просмотра каталога товаров.
    Поддерживает поиск, фильтрацию и сортировку для менеджеров и администраторов.
    """

    def __init__(self, parent_window, application):
        self.application = application
        self.parent = parent_window
        self.cached_images = {}

        self.main_frame = Frame(parent_window, bg=COLOR_BACKGROUND_MAIN)
        self.main_frame.pack(fill=BOTH, expand=True)

        # Верхняя панель
        header_frame = Frame(self.main_frame, bg=COLOR_BACKGROUND_MAIN)
        header_frame.pack(fill=X, padx=10, pady=5)

        # Приветствие
        Label(
            header_frame,
            text=f"Добро пожаловать, {self.application.active_user['full_name']}",
            font=("Times New Roman", 12),
            bg=COLOR_BACKGROUND_MAIN
        ).pack(side=LEFT)

        # Кнопка выхода
        Button(
            header_frame,
            text="Выйти",
            command=self._logout_user,
            bg=COLOR_BACKGROUND_SECONDARY
        ).pack(side=RIGHT)

        self.user_role = self.application.active_user['role']

        # Панели управления для менеджера и администратора
        if self.user_role in ('Администратор', 'Менеджер'):
            self._create_control_panels(header_frame)

        # Таблица товаров
        self.column_names = (
            "Фото", "Наименование", "Категория", "Описание",
            "Производитель", "Поставщик", "Цена", "Ед.изм.",
            "Кол-во", "Скидка"
        )

        self.products_table = ttk.Treeview(
            self.main_frame,
            columns=self.column_names[1:],
            show="headings",
            height=20
        )

        self.products_table.heading("#0", text="Фото")
        self.products_table.column("#0", width=80)

        for column_name in self.column_names[1:]:
            self.products_table.heading(column_name, text=column_name)
            self.products_table.column(column_name, width=100)

        self.products_table.pack(fill=BOTH, expand=True, padx=10, pady=5)

        # Полоса прокрутки
        scroll_bar = ttk.Scrollbar(
            self.main_frame,
            orient=VERTICAL,
            command=self.products_table.yview
        )
        scroll_bar.pack(side=RIGHT, fill=Y)
        self.products_table.configure(yscrollcommand=scroll_bar.set)

        # Загрузка данных
        self._load_product_data()

        # Привязка двойного клика для администратора
        if self.user_role == 'Администратор':
            self.products_table.bind("<Double-1>", self._on_product_double_click)

    def _create_control_panels(self, parent_frame):
        """Создание панелей поиска, фильтрации и управления."""
        left_panel = Frame(parent_frame, bg=COLOR_BACKGROUND_MAIN)
        left_panel.pack(side=LEFT, fill=X, expand=True)

        right_panel = Frame(parent_frame, bg=COLOR_BACKGROUND_MAIN)
        right_panel.pack(side=RIGHT)

        # Элементы поиска и фильтрации
        self._add_search_filter_elements(left_panel)

        # Кнопки администратора
        if self.user_role == 'Администратор':
            Button(
                right_panel,
                text="Удалить товар",
                command=self._delete_selected_product,
                bg=COLOR_DELETE_BUTTON
            ).pack(side=RIGHT, padx=5)

            Button(
                right_panel,
                text="Добавить товар",
                command=self._add_new_product,
                bg=COLOR_ACCENT
            ).pack(side=RIGHT, padx=5)

        # Кнопка заказов
        Button(
            right_panel,
            text="Заказы",
            command=self._navigate_to_orders,
            bg=COLOR_ACCENT
        ).pack(side=RIGHT, padx=5)

    def _add_search_filter_elements(self, parent):
        """Добавление элементов поиска, фильтрации и сортировки."""
        # Поиск
        Label(parent, text="Поиск: ", bg=COLOR_BACKGROUND_MAIN).pack(side=LEFT)
        self.search_text = StringVar()
        self.search_input = Entry(parent, textvariable=self.search_text, width=20)
        self.search_input.pack(side=LEFT, padx=5)
        self.search_text.trace('w', lambda *args: self._load_product_data())

        # Фильтр по поставщику
        Label(parent, text="Поставщик: ", bg=COLOR_BACKGROUND_MAIN).pack(side=LEFT, padx=(10, 0))
        self.supplier_text = StringVar()
        self.supplier_selector = ttk.Combobox(
            parent,
            textvariable=self.supplier_text,
            state="readonly"
        )
        self._load_suppliers_list()
        self.supplier_selector.pack(side=LEFT, padx=5)
        self.supplier_text.trace('w', lambda *args: self._load_product_data())

        # Сортировка
        Label(parent, text="Сортировка по кол-ву: ", bg=COLOR_BACKGROUND_MAIN).pack(side=LEFT, padx=(10, 0))
        self.sort_text = StringVar()
        self.sort_selector = ttk.Combobox(
            parent,
            textvariable=self.sort_text,
            values=("Нет", "По возрастанию", "По убыванию"),
            state="readonly"
        )
        self.sort_selector.set("Нет")
        self.sort_selector.pack(side=LEFT, padx=5)
        self.sort_text.trace('w', lambda *args: self._load_product_data())

    def _load_suppliers_list(self):
        """Загрузка списка поставщиков из базы данных."""
        connection = sqlite3.connect(DATABASE_NAME)
        cursor = connection.cursor()

        cursor.execute("SELECT name FROM suppliers ORDER BY name")
        suppliers_list = [row[0] for row in cursor.fetchall()]

        connection.close()

        self.supplier_selector['values'] = ["Все поставщики"] + suppliers_list
        self.supplier_text.set("Все поставщики")

    def _load_product_data(self):
        """Загрузка и отображение товаров из базы данных."""
        connection = sqlite3.connect(DATABASE_NAME)
        cursor = connection.cursor()

        query = '''
            SELECT p.article, p.name, c.name, p.description, m.name, s.name,
                   p.price, p.unit, p.stock, p.discount, p.image_path
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            LEFT JOIN manufacturers m ON p.manufacturer_id = m.id
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            WHERE 1=1
        '''

        parameters = []

        # Поиск (только для менеджера и администратора)
        if self.user_role in ('Менеджер', 'Администратор'):
            if hasattr(self, 'search_text') and self.search_text.get().strip():
                search_term = self.search_text.get().strip()
                query += " AND (p.name LIKE ? OR p.description LIKE ? OR m.name LIKE ? OR s.name LIKE ?)"
                like_pattern = f"%{search_term}%"
                parameters.extend([like_pattern, like_pattern, like_pattern, like_pattern])

            # Фильтр по поставщику
            if hasattr(self, 'supplier_text') and self.supplier_text.get() != "Все поставщики":
                query += " AND s.name = ?"
                parameters.append(self.supplier_text.get())

            # Сортировка
            if hasattr(self, 'sort_text') and self.sort_text.get() != "Нет":
                if self.sort_text.get() == "По возрастанию":
                    query += " ORDER BY p.stock ASC"
                else:
                    query += " ORDER BY p.stock DESC"

        cursor.execute(query, parameters)
        rows_data = cursor.fetchall()
        connection.close()

        # Очистка таблицы
        for item_id in self.products_table.get_children():
            self.products_table.delete(item_id)

        self.cached_images = {}

        # Заполнение таблицы
        for row in rows_data:
            self._insert_product_row(row)

        # Настройка тегов для подсветки
        self.products_table.tag_configure("discount", background=COLOR_DISCOUNT_HIGHLIGHT)
        self.products_table.tag_configure("out_of_stock", background=COLOR_OUT_OF_STOCK)
        self.products_table.tag_configure("normal", background=COLOR_BACKGROUND_MAIN)

    def _insert_product_row(self, row):
        """Вставка одной строки товара в таблицу."""
        (article, name, category, desc, manuf, supplier,
         price, unit, stock, discount, img_path) = row

        # Формирование отображения цены
        if discount and discount > 0:
            final_price = price * (100 - discount) / 100
            price_display = f"{price:.2f} руб.\n{final_price:.2f} руб."
        else:
            price_display = f"{price:.2f} руб."

        # Загрузка изображения
        image_widget = None
        if img_path and os.path.exists(img_path):
            try:
                pil_image = Image.open(img_path)
                pil_image.thumbnail((70, 70), Image.Resampling.LANCZOS)
                image_widget = ImageTk.PhotoImage(pil_image)
                self.cached_images[article] = image_widget
            except Exception:
                pass
        else:
            # Заглушка
            placeholder_path = os.path.join(FOLDER_IMAGES, DEFAULT_IMAGE_NAME)
            if os.path.exists(placeholder_path):
                try:
                    pil_image = Image.open(placeholder_path)
                    pil_image.thumbnail((70, 70), Image.Resampling.LANCZOS)
                    image_widget = ImageTk.PhotoImage(pil_image)
                    self.cached_images[article] = image_widget
                except Exception:
                    pass

        # Вставка строки
        item_id = self.products_table.insert(
            "", END, text="",
            values=(name, category, desc, manuf, supplier,
                    price_display, unit, stock, f"{discount}%"),
            tags=(article,)
        )

        if image_widget:
            self.products_table.item(item_id, image=image_widget)

        # Применение тегов подсветки
        if discount > 15:
            self.products_table.item(item_id, tags=("discount", article))
        elif stock == 0:
            self.products_table.item(item_id, tags=("out_of_stock", article))
        else:
            self.products_table.item(item_id, tags=("normal", article))

    def _on_product_double_click(self, event):
        """Обработка двойного клика по товару (редактирование)."""
        selected_items = self.products_table.selection()
        if not selected_items:
            return

        item = selected_items[0]
        article_value = self.products_table.item(item, "tags")[1]

        ProductEditDialog(self.parent, self.application, article_value, self)

    def _add_new_product(self):
        """Открытие формы добавления нового товара."""
        ProductEditDialog(self.parent, self.application, None, self)

    def _delete_selected_product(self):
        """Удаление выбранного товара."""
        selected_items = self.products_table.selection()

        if not selected_items:
            messagebox.showwarning("Удаление", "Выберите товар для удаления")
            return

        item = selected_items[0]
        article_value = self.products_table.item(item, "tags")[1]

        # Проверка наличия в заказах
        connection = sqlite3.connect(DATABASE_NAME)
        cursor = connection.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM order_items WHERE product_article=?",
            (article_value,)
        )

        order_count = cursor.fetchone()[0]
        connection.close()

        if order_count > 0:
            messagebox.showerror(
                "Ошибка",
                "Невозможно удалить товар, который присутствует в заказах."
            )
            return

        # Подтверждение удаления
        if messagebox.askyesno("Подтверждение", f"Удалить товар {article_value}?"):
            connection = sqlite3.connect(DATABASE_NAME)
            cursor = connection.cursor()

            # Получение пути к изображению
            cursor.execute(
                "SELECT image_path FROM products WHERE article=?",
                (article_value,)
            )
            image_file = cursor.fetchone()[0]

            cursor.execute("DELETE FROM products WHERE article=?", (article_value,))
            connection.commit()
            connection.close()

            # Удаление файла изображения
            if image_file and os.path.exists(image_file):
                try:
                    os.remove(image_file)
                except Exception:
                    pass

            self._load_product_data()
            messagebox.showinfo("Успех", "Товар удалён")

    def _logout_user(self):
        """Выход из системы."""
        self.application.active_user = None
        self.application._display_login_screen()

    def _navigate_to_orders(self):
        """Переход к управлению заказами."""
        self.application._display_orders_screen()


class ProductEditDialog:
    """
    Диалоговое окно для добавления и редактирования товаров.
    Доступно только администратору.
    """

    def __init__(self, parent_window, application, article_value=None, refresh_callback=None):
        self.application = application
        self.refresh_callback = refresh_callback
        self.article_value = article_value
        self.image_file_path = None

        self.dialog_window = Toplevel(parent_window)
        self.dialog_window.title(
            "Редактирование товара" if article_value else "Добавление товара"
        )
        self.dialog_window.geometry("500x600")
        self.dialog_window.resizable(False, False)
        self.dialog_window.transient(parent_window)
        self.dialog_window.grab_set()

        self._load_reference_data()
        self._create_form_elements()

        if article_value:
            self._populate_form_data()

        self.dialog_window.protocol("WM_DELETE_WINDOW", self._close_dialog)

    def _load_reference_data(self):
        """Загрузка справочных данных (категории, производители, поставщики)."""
        connection = sqlite3.connect(DATABASE_NAME)
        cursor = connection.cursor()

        self.categories_dict = {
            name: id_
            for id_, name in cursor.execute("SELECT id, name FROM categories")
        }

        self.manufacturers_dict = {
            name: id_
            for id_, name in cursor.execute("SELECT id, name FROM manufacturers")
        }

        self.suppliers_dict = {
            name: id_
            for id_, name in cursor.execute("SELECT id, name FROM suppliers")
        }

        connection.close()

    def _create_form_elements(self):
        """Создание элементов формы редактирования."""
        form_frame = Frame(self.dialog_window, bg=COLOR_BACKGROUND_MAIN)
        form_frame.pack(padx=10, pady=10, fill=BOTH, expand=True)

        row_index = 0

        # Наименование
        Label(form_frame, text="Наименование: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.name_input = Entry(form_frame, width=40)
        self.name_input.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Категория
        Label(form_frame, text="Категория: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.category_text = StringVar()
        self.category_selector = ttk.Combobox(
            form_frame,
            textvariable=self.category_text,
            values=list(self.categories_dict.keys()),
            state="readonly"
        )
        self.category_selector.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Описание
        Label(form_frame, text="Описание: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.description_area = Text(form_frame, width=40, height=5)
        self.description_area.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Производитель
        Label(form_frame, text="Производитель: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.manufacturer_text = StringVar()
        self.manufacturer_selector = ttk.Combobox(
            form_frame,
            textvariable=self.manufacturer_text,
            values=list(self.manufacturers_dict.keys()),
            state="readonly"
        )
        self.manufacturer_selector.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Поставщик
        Label(form_frame, text="Поставщик: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.supplier_text = StringVar()
        self.supplier_selector = ttk.Combobox(
            form_frame,
            textvariable=self.supplier_text,
            values=list(self.suppliers_dict.keys()),
            state="readonly"
        )
        self.supplier_selector.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Цена
        Label(form_frame, text="Цена: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.price_input = Entry(form_frame, width=20)
        self.price_input.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Единица измерения
        Label(form_frame, text="Ед.изм.: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.unit_input = Entry(form_frame, width=20)
        self.unit_input.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Количество на складе
        Label(form_frame, text="Кол-во на складе: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.stock_input = Entry(form_frame, width=20)
        self.stock_input.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Скидка
        Label(form_frame, text="Скидка (%): ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.discount_input = Entry(form_frame, width=20)
        self.discount_input.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Фото
        Label(form_frame, text="Фото: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.photo_button = Button(
            form_frame,
            text="Выбрать файл",
            command=self._select_image_file,
            bg=COLOR_BACKGROUND_SECONDARY
        )
        self.photo_button.grid(row=row_index, column=1, pady=2)

        self.photo_status = Label(form_frame, text="Файл не выбран", bg=COLOR_BACKGROUND_MAIN)
        self.photo_status.grid(row=row_index + 1, column=1, pady=2)
        row_index += 2

        # Кнопки
        button_frame = Frame(form_frame, bg=COLOR_BACKGROUND_MAIN)
        button_frame.grid(row=row_index, column=0, columnspan=2, pady=10)

        Button(
            button_frame,
            text="Сохранить",
            command=self._save_product_data,
            bg=COLOR_ACCENT
        ).pack(side=LEFT, padx=5)

        Button(
            button_frame,
            text="Отмена",
            command=self._close_dialog,
            bg=COLOR_BACKGROUND_SECONDARY
        ).pack(side=LEFT)

    def _select_image_file(self):
        """Выбор файла изображения для товара."""
        file_types = (
            ("Image files", "*.jpg *.jpeg *.png *.bmp"),
            ("All files", "*.*")
        )

        filename = filedialog.askopenfilename(
            title="Выберите изображение",
            filetypes=file_types
        )

        if filename:
            try:
                img = Image.open(filename)
                img.thumbnail((300, 200), Image.Resampling.LANCZOS)

                if not os.path.exists(FOLDER_IMAGES):
                    os.makedirs(FOLDER_IMAGES)

                file_extension = os.path.splitext(filename)[1]
                new_filename = f"prod_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}{file_extension}"
                destination_path = os.path.join(FOLDER_IMAGES, new_filename)

                img.save(destination_path)

                self.image_file_path = destination_path
                self.photo_status.config(text=os.path.basename(destination_path))

            except Exception as error_message:
                messagebox.showerror(
                    "Ошибка",
                    f"Не удалось загрузить изображение: {error_message}"
                )

    def _populate_form_data(self):
        """Заполнение формы данными существующего товара."""
        connection = sqlite3.connect(DATABASE_NAME)
        cursor = connection.cursor()

        cursor.execute('''
            SELECT name, category_id, description, manufacturer_id, 
                   supplier_id, price, unit, stock, discount, image_path
            FROM products WHERE article=?
        ''', (self.article_value,))

        row_data = cursor.fetchone()
        connection.close()

        if row_data:
            (name_val, cat_id, desc_val, man_id, sup_id,
             price_val, unit_val, stock_val, discount_val, img_path) = row_data

            self.name_input.insert(0, name_val)

            for cat_name, cat_identifier in self.categories_dict.items():
                if cat_identifier == cat_id:
                    self.category_text.set(cat_name)
                    break

            self.description_area.insert(1.0, desc_val)

            for man_name, man_identifier in self.manufacturers_dict.items():
                if man_identifier == man_id:
                    self.manufacturer_text.set(man_name)
                    break

            for sup_name, sup_identifier in self.suppliers_dict.items():
                if sup_identifier == sup_id:
                    self.supplier_text.set(sup_name)
                    break

            self.price_input.insert(0, str(price_val))
            self.unit_input.insert(0, unit_val)
            self.stock_input.insert(0, str(stock_val))
            self.discount_input.insert(0, str(discount_val))

            if img_path and os.path.exists(img_path):
                self.image_file_path = img_path
                self.photo_status.config(text=os.path.basename(img_path))
            else:
                self.image_file_path = None

    def _save_product_data(self):
        """Сохранение данных товара в базу данных."""
        # Валидация цены
        try:
            price_value = float(self.price_input.get())
            if price_value < 0:
                raise ValueError("Цена не может быть отрицательной")
        except Exception:
            messagebox.showerror("Ошибка", "Цена должна быть числом >=0")
            return

        # Валидация количества
        try:
            stock_value = int(self.stock_input.get())
            if stock_value < 0:
                raise ValueError("Количество не может быть отрицательным")
        except Exception:
            messagebox.showerror("Ошибка", "Количество должно быть целым неотрицательным числом")
            return

        discount_value = int(self.discount_input.get()) if self.discount_input.get() else 0

        name_value = self.name_input.get().strip()
        if not name_value:
            messagebox.showerror("Ошибка", "Наименование обязательно")
            return

        category_name = self.category_text.get()
        manufacturer_name = self.manufacturer_text.get()
        supplier_name = self.supplier_text.get()

        if not category_name or not manufacturer_name or not supplier_name:
            messagebox.showerror(
                "Ошибка",
                "Выберите категорию, производителя и поставщика"
            )
            return

        category_id = self.categories_dict[category_name]
        manufacturer_id = self.manufacturers_dict[manufacturer_name]
        supplier_id = self.suppliers_dict[supplier_name]

        unit_value = self.unit_input.get().strip()
        description_value = self.description_area.get("1.0", END).strip()

        connection = sqlite3.connect(DATABASE_NAME)
        cursor = connection.cursor()

        if self.article_value:
            # Обновление существующего товара
            cursor.execute(
                "SELECT image_path FROM products WHERE article=?",
                (self.article_value,)
            )
            old_image = cursor.fetchone()[0]

            # Удаление старого изображения при замене
            if (self.image_file_path and old_image and
                    old_image != self.image_file_path and os.path.exists(old_image)):
                os.remove(old_image)

            cursor.execute('''
                UPDATE products SET name=?, category_id=?, description=?, 
                       manufacturer_id=?, supplier_id=?, price=?, unit=?, 
                       stock=?, discount=?, image_path=?
                WHERE article=?
            ''', (
                name_value, category_id, description_value, manufacturer_id,
                supplier_id, price_value, unit_value, stock_value,
                discount_value, self.image_file_path, self.article_value
            ))
        else:
            # Добавление нового товара
            cursor.execute("SELECT MAX(id) FROM products")
            max_identifier = cursor.fetchone()[0] or 0
            new_article = f"P{max_identifier + 1}"

            cursor.execute('''
                INSERT INTO products 
                (article, name, category_id, description, manufacturer_id, 
                 supplier_id, price, unit, stock, discount, image_path)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                new_article, name_value, category_id, description_value,
                manufacturer_id, supplier_id, price_value, unit_value,
                stock_value, discount_value, self.image_file_path
            ))

        connection.commit()
        connection.close()

        if self.refresh_callback:
            self.refresh_callback._load_product_data()

        self._close_dialog()

    def _close_dialog(self):
        """Закрытие диалогового окна."""
        self.dialog_window.destroy()


class OrdersManagementWindow:
    """
    Окно управления заказами.
    Доступно менеджеру и администратору.
    """

    def __init__(self, parent_window, application):
        self.application = application
        self.parent = parent_window

        self.main_frame = Frame(parent_window, bg=COLOR_BACKGROUND_MAIN)
        self.main_frame.pack(fill=BOTH, expand=True)

        # Верхняя панель
        header_frame = Frame(self.main_frame, bg=COLOR_BACKGROUND_MAIN)
        header_frame.pack(fill=X, padx=10, pady=5)

        Label(
            header_frame,
            text=f"Заказы - {self.application.active_user['full_name']}",
            font=("Times New Roman", 12),
            bg=COLOR_BACKGROUND_MAIN
        ).pack(side=LEFT)

        Button(
            header_frame,
            text="Назад",
            command=self._go_back,
            bg=COLOR_BACKGROUND_SECONDARY
        ).pack(side=RIGHT)

        # Кнопки администратора
        if self.application.active_user['role'] == 'Администратор':
            Button(
                header_frame,
                text="Добавить заказ",
                command=self._add_new_order,
                bg=COLOR_ACCENT
            ).pack(side=RIGHT, padx=5)

            Button(
                header_frame,
                text="Удалить заказ",
                command=self._delete_selected_order,
                bg=COLOR_DELETE_BUTTON
            ).pack(side=RIGHT, padx=5)

        # Таблица заказов
        table_columns = (
            "Номер", "Дата заказа", "Дата доставки",
            "Адрес выдачи", "Клиент", "Статус"
        )

        self.orders_table = ttk.Treeview(
            self.main_frame,
            columns=table_columns,
            show="headings",
            height=20
        )

        for col_name in table_columns:
            self.orders_table.heading(col_name, text=col_name)
            self.orders_table.column(col_name, width=150)

        self.orders_table.pack(fill=BOTH, expand=True, padx=10, pady=5)

        scroll_bar = ttk.Scrollbar(
            self.main_frame,
            orient=VERTICAL,
            command=self.orders_table.yview
        )
        scroll_bar.pack(side=RIGHT, fill=Y)
        self.orders_table.configure(yscrollcommand=scroll_bar.set)

        self._load_orders_data()

        if self.application.active_user['role'] == 'Администратор':
            self.orders_table.bind("<Double-1>", self._on_order_double_click)

    def _load_orders_data(self):
        """Загрузка данных о заказах из базы данных."""
        connection = sqlite3.connect(DATABASE_NAME)
        cursor = connection.cursor()

        cursor.execute('''
            SELECT o.id, o.order_number, o.order_date, o.delivery_date, 
                   p.address, u.full_name, o.status
            FROM orders o
            LEFT JOIN pickup_points p ON o.pickup_point_id = p.id
            LEFT JOIN users u ON o.user_id = u.id
            ORDER BY o.order_date DESC
        ''')

        rows_data = cursor.fetchall()
        connection.close()

        for item_id in self.orders_table.get_children():
            self.orders_table.delete(item_id)

        for row in rows_data:
            (order_id, number, order_date, delivery_date,
             address, client, status) = row

            self.orders_table.insert(
                "", END,
                values=(number, order_date, delivery_date, address, client, status),
                tags=(order_id,)
            )

    def _on_order_double_click(self, event):
        """Обработка двойного клика по заказу (редактирование)."""
        selected_items = self.orders_table.selection()
        if not selected_items:
            return

        item = selected_items[0]
        order_id_value = self.orders_table.item(item, "tags")[0]

        OrderEditDialog(self.parent, self.application, order_id_value, self)

    def _add_new_order(self):
        """Открытие формы добавления нового заказа."""
        OrderEditDialog(self.parent, self.application, None, self)

    def _delete_selected_order(self):
        """Удаление выбранного заказа."""
        selected_items = self.orders_table.selection()

        if not selected_items:
            messagebox.showwarning("Удаление", "Выберите заказ для удаления")
            return

        item = selected_items[0]
        order_id_value = self.orders_table.item(item, "tags")[0]

        if messagebox.askyesno("Подтверждение", "Удалить заказ?"):
            connection = sqlite3.connect(DATABASE_NAME)
            cursor = connection.cursor()

            cursor.execute("DELETE FROM orders WHERE id=?", (order_id_value,))
            connection.commit()
            connection.close()

            self._load_orders_data()
            messagebox.showinfo("Успех", "Заказ удалён")

    def _go_back(self):
        """Возврат к каталогу товаров."""
        self.application._display_catalog_screen()


class OrderEditDialog:
    """
    Диалоговое окно для добавления и редактирования заказов.
    Доступно только администратору.
    """

    def __init__(self, parent_window, application, order_id_value=None, refresh_callback=None):
        self.application = application
        self.refresh_callback = refresh_callback
        self.order_id_value = order_id_value

        self.dialog_window = Toplevel(parent_window)
        self.dialog_window.title(
            "Редактирование заказа" if order_id_value else "Добавление заказа"
        )
        self.dialog_window.geometry("500x400")
        self.dialog_window.resizable(False, False)
        self.dialog_window.transient(parent_window)
        self.dialog_window.grab_set()

        self._load_reference_data()
        self._create_form_elements()

        if order_id_value:
            self._populate_form_data()

        self.dialog_window.protocol("WM_DELETE_WINDOW", self._close_dialog)

    def _load_reference_data(self):
        """Загрузка справочных данных для формы заказа."""
        connection = sqlite3.connect(DATABASE_NAME)
        cursor = connection.cursor()

        self.pickup_points_dict = {
            addr: id_
            for id_, addr in cursor.execute("SELECT id, address FROM pickup_points")
        }

        self.clients_dict = {
            full_name: id_
            for id_, full_name in cursor.execute(
                "SELECT id, full_name FROM users WHERE role='client'"
            )
        }

        connection.close()

    def _create_form_elements(self):
        """Создание элементов формы редактирования заказа."""
        form_frame = Frame(self.dialog_window, bg=COLOR_BACKGROUND_MAIN)
        form_frame.pack(padx=10, pady=10, fill=BOTH, expand=True)

        row_index = 0

        # Номер заказа
        Label(form_frame, text="Номер заказа: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.number_input = Entry(
            form_frame,
            state='readonly' if self.order_id_value else 'normal',
            width=30
        )
        self.number_input.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Статус
        Label(form_frame, text="Статус: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.status_text = StringVar()
        self.status_selector = ttk.Combobox(
            form_frame,
            textvariable=self.status_text,
            values=("Новый", "Завершен"),
            state="readonly"
        )
        self.status_selector.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Адрес выдачи
        Label(form_frame, text="Адрес выдачи: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.address_text = StringVar()
        self.address_selector = ttk.Combobox(
            form_frame,
            textvariable=self.address_text,
            values=list(self.pickup_points_dict.keys()),
            state="readonly"
        )
        self.address_selector.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Дата заказа
        Label(form_frame, text="Дата заказа: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.order_date_input = Entry(form_frame, width=30)
        self.order_date_input.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Дата выдачи
        Label(form_frame, text="Дата выдачи: ", bg=COLOR_BACKGROUND_MAIN).grid(
            row=row_index, column=0, sticky=W, pady=2
        )
        self.delivery_date_input = Entry(form_frame, width=30)
        self.delivery_date_input.grid(row=row_index, column=1, pady=2)
        row_index += 1

        # Клиент (только для нового заказа)
        if not self.order_id_value:
            Label(form_frame, text="Клиент: ", bg=COLOR_BACKGROUND_MAIN).grid(
                row=row_index, column=0, sticky=W, pady=2
            )
            self.client_text = StringVar()
            self.client_selector = ttk.Combobox(
                form_frame,
                textvariable=self.client_text,
                values=list(self.clients_dict.keys()),
                state="readonly"
            )
            self.client_selector.grid(row=row_index, column=1, pady=2)
            row_index += 1

        # Кнопки
        button_frame = Frame(form_frame, bg=COLOR_BACKGROUND_MAIN)
        button_frame.grid(row=row_index, column=0, columnspan=2, pady=10)

        Button(
            button_frame,
            text="Сохранить",
            command=self._save_order_data,
            bg=COLOR_ACCENT
        ).pack(side=LEFT, padx=5)

        Button(
            button_frame,
            text="Отмена",
            command=self._close_dialog,
            bg=COLOR_BACKGROUND_SECONDARY
        ).pack(side=LEFT)

    def _populate_form_data(self):
        """Заполнение формы данными существующего заказа."""
        connection = sqlite3.connect(DATABASE_NAME)
        cursor = connection.cursor()

        cursor.execute('''
            SELECT order_number, status, pickup_point_id, order_date, delivery_date
            FROM orders WHERE id=?
        ''', (self.order_id_value,))

        row_data = cursor.fetchone()
        connection.close()

        if row_data:
            (num, status, pp_id, order_date, delivery_date) = row_data

            self.number_input.config(state='normal')
            self.number_input.delete(0, END)
            self.number_input.insert(0, num)
            self.number_input.config(state='readonly')

            self.status_text.set(status)

            for addr, identifier in self.pickup_points_dict.items():
                if identifier == pp_id:
                    self.address_text.set(addr)
                    break

            self.order_date_input.insert(0, order_date)

            if delivery_date:
                self.delivery_date_input.insert(0, delivery_date)

    def _save_order_data(self):
        """Сохранение данных заказа в базу данных."""
        order_date_value = self.order_date_input.get().strip()
        delivery_date_value = self.delivery_date_input.get().strip() or None

        # Валидация формата дат
        try:
            datetime.datetime.strptime(order_date_value, "%Y-%m-%d")
            if delivery_date_value:
                datetime.datetime.strptime(delivery_date_value, "%Y-%m-%d")
        except Exception:
            messagebox.showerror(
                "Ошибка",
                "Даты должны быть в формате YYYY-MM-DD"
            )
            return

        status_value = self.status_text.get()
        address_value = self.address_text.get()

        if not address_value:
            messagebox.showerror("Ошибка", "Выберите адрес выдачи")
            return

        pickup_id = self.pickup_points_dict[address_value]

        connection = sqlite3.connect(DATABASE_NAME)
        cursor = connection.cursor()

        if self.order_id_value:
            # Обновление существующего заказа
            cursor.execute('''
                UPDATE orders SET status=?, pickup_point_id=?, 
                       order_date=?, delivery_date=?
                WHERE id=?
            ''', (status_value, pickup_id, order_date_value, delivery_date_value, self.order_id_value))
        else:
            # Создание нового заказа
            cursor.execute("SELECT MAX(id) FROM orders")
            max_identifier = cursor.fetchone()[0] or 0
            new_number = f"Z{max_identifier + 1}"

            client_id = self.clients_dict[self.client_text.get()]
            pickup_code_value = str(random.randint(100, 999))

            cursor.execute('''
                INSERT INTO orders 
                (order_number, status, pickup_point_id, order_date, 
                 delivery_date, user_id, pickup_code)
                VALUES (?,?,?,?,?,?,?)
            ''', (
                new_number, status_value, pickup_id, order_date_value,
                delivery_date_value, client_id, pickup_code_value
            ))

        connection.commit()
        connection.close()

        if self.refresh_callback:
            self.refresh_callback._load_orders_data()

        self._close_dialog()

    def _close_dialog(self):
        """Закрытие диалогового окна."""
        self.dialog_window.destroy()


# ============================================================================
# ТОЧКА ВХОДА В ПРИЛОЖЕНИЕ
# ============================================================================

if __name__ == "__main__":
    # Создание папки для изображений
    if not os.path.exists(FOLDER_IMAGES):
        os.makedirs(FOLDER_IMAGES)

    # Копирование изображения-заглушки
    placeholder_source = os.path.join(FOLDER_RESOURCES, DEFAULT_IMAGE_NAME)
    placeholder_destination = os.path.join(FOLDER_IMAGES, DEFAULT_IMAGE_NAME)

    if os.path.exists(placeholder_source) and not os.path.exists(placeholder_destination):
        shutil.copy(placeholder_source, placeholder_destination)

    # Инициализация базы данных
    initialize_database()

    # Запуск приложения
    application = ShoeStoreApplication()
    application.start()