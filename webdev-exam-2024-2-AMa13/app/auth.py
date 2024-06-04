from flask import Blueprint, request, url_for, render_template, flash, redirect, current_app
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user
from checkRole import CheckRole
from functools import wraps
from mysql_db import MySQL

bp = Blueprint('auth', __name__, url_prefix='/auth')
mysql = MySQL(current_app)

class User(UserMixin):
    def __init__(self, user_id, login, role_id, first_name, last_name, middle_name):
        self.id = user_id
        self.login = login
        self.role_id = role_id
        self.first_name = first_name
        self.last_name = last_name
        self.middle_name = middle_name

    def is_admin(self):
        return self.role_id == current_app.config['ADMIN_ROLE_ID']

    def is_moderator(self):
        return self.role_id == current_app.config['MODERATOR_ROLE_ID']

    def can(self, action, record=None):
        check_role = CheckRole(record=record)
        method = getattr(check_role, action, None)
        if method:
            return method()
        return False

def load_user(user_id):
    conn = mysql.connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM users WHERE id=%s', (user_id,))
    user = cursor.fetchone()
    if user:
        return User(
            user_id=user['id'], 
            login=user['login'], 
            role_id=user['role_id'], 
            first_name=user['first_name'], 
            last_name=user['last_name'],
            middle_name=user['middle_name']
        )
    return None

def init_login_manager(app):
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Доступ к данной странице есть только у авторизованных пользователей'
    login_manager.login_message_category = 'warning'
    login_manager.user_loader(load_user)

def check_permission(action):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            book_id = kwargs.get('book_id')
            record = None
            if book_id:
                conn = mysql.connection()
                cursor = conn.cursor(dictionary=True)
                cursor.execute('SELECT * FROM books WHERE id=%s', (book_id,))
                record = cursor.fetchone()
            
            if not current_user.can(action, record):
                flash('Недостаточно прав доступа', 'danger')
                return redirect(url_for('index'))
            return func(*args, **kwargs)
        return wrapper
    return decorator

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        login = request.form.get('login')
        password = request.form.get('password')
        remember = request.form.get('remember')
        if login and password:
            conn = mysql.connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT * FROM users WHERE login=%s AND password_hash = SHA2(%s, 256)', (login, password))
            user = cursor.fetchone()
            if user:
                login_user(User(
                    user_id=user['id'], 
                    login=user['login'], 
                    role_id=user['role_id'], 
                    first_name=user['first_name'], 
                    last_name=user['last_name'],
                    middle_name=user['middle_name']
                ), remember=remember)
                flash('Вы успешно прошли аутентификацию', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('index'))
        flash('Неверные логин или пароль', 'danger')
    return render_template('login.html')

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))
