from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_required, current_user
import mysql.connector
from config import SECRET_KEY
from checkRole import CheckRole
from mysql_db import MySQL
from auth import check_permission, load_user, init_login_manager
from auth import bp as auth_bp
import os, bleach, hashlib, markdown
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['UPLOAD_FOLDER'] = 'static/covers'
app.config.from_pyfile('config.py')

mysql = MySQL(app)

init_login_manager(app)

app.register_blueprint(auth_bp)

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

@app.route('/')
@app.route('/index')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    conn = mysql.connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''SELECT books.id, books.title, books.year, 
                             GROUP_CONCAT(genres.name) AS genres, 
                             AVG(reviews.rating) AS average_rating, 
                             COUNT(reviews.id) AS review_count 
                      FROM books 
                      LEFT JOIN book_genres ON books.id = book_genres.book_id 
                      LEFT JOIN genres ON book_genres.genre_id = genres.id 
                      LEFT JOIN reviews ON books.id = reviews.book_id 
                      GROUP BY books.id 
                      ORDER BY books.year DESC 
                      LIMIT %s OFFSET %s''', (per_page, offset))
    books = cursor.fetchall() or []

    cursor.execute('SELECT COUNT(*) AS count FROM books')
    total_books = cursor.fetchone()
    total_books = total_books['count'] if total_books else 0
    has_next = total_books > page * per_page

    return render_template('index.html', books=books, page=page, has_next=has_next)

@app.route('/add_book', methods=['GET', 'POST'])
@login_required
@check_permission('create')
def add_book():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        year = request.form['year']
        publisher = request.form['publisher']
        author = request.form['author']
        pages = request.form['pages']
        genres = request.form.getlist('genres')
        cover = request.files['cover']

        conn = mysql.connection()
        cursor = conn.cursor()

        cover_id = None
        if cover:
            cover_filename = secure_filename(cover.filename)
            cover_path = os.path.join(app.config['UPLOAD_FOLDER'], cover_filename)
            cover_md5 = hashlib.md5(cover.read()).hexdigest()
            
            # Проверяем, существует ли уже обложка с таким хэшем
            cursor.execute('SELECT id FROM covers WHERE md5_hash = %s', (cover_md5,))
            existing_cover = cursor.fetchone()
            if existing_cover:
                cover_id = existing_cover['id']
            else:
                # Перемещаем курсор в начало файла после чтения хэша
                cover.seek(0)
                cover.save(cover_path)
                cursor.execute('''INSERT INTO covers (file_name, mime_type, md5_hash)
                                  VALUES (%s, %s, %s)''',
                               (cover_filename, cover.mimetype, cover_md5))
                cover_id = cursor.lastrowid

        # Добавление книги
        cursor.execute('''INSERT INTO books (title, description, year, publisher, author, pages, cover_id)
                          VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                       (title, description, year, publisher, author, pages, cover_id))
        book_id = cursor.lastrowid
        
        # Добавление жанров
        for genre_id in genres:
            cursor.execute('INSERT INTO book_genres (book_id, genre_id) VALUES (%s, %s)', (book_id, genre_id))
        
        conn.commit()
        flash('Книга добавлена', 'success')
        return redirect(url_for('index'))
    
    conn = mysql.connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM genres')
    all_genres = cursor.fetchall()
    
    return render_template('add_book.html', book=None, all_genres=all_genres, selected_genres=[])

@app.route('/edit_book/<int:book_id>', methods=['GET', 'POST'])
@login_required
@check_permission('edit')
def edit_book(book_id):
    conn = mysql.connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute('SELECT * FROM books WHERE id=%s', (book_id,))
    book = cursor.fetchone()

    if not book:
        flash('Книга не найдена', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form['title']
        description = bleach.clean(request.form['description'])
        year = request.form['year']
        publisher = request.form['publisher']
        author = request.form['author']
        pages = request.form['pages']
        genres = request.form.getlist('genres')

        try:
            # Обновление книги
            cursor.execute('''UPDATE books SET title=%s, description=%s, year=%s, publisher=%s, author=%s, pages=%s
                              WHERE id=%s''',
                              (title, description, year, publisher, author, pages, book_id))

            # Обновление жанров
            cursor.execute('DELETE FROM book_genres WHERE book_id=%s', (book_id,))
            for genre_id in genres:
                cursor.execute('INSERT INTO book_genres (book_id, genre_id) VALUES (%s, %s)', (book_id, genre_id))
            
            conn.commit()
            flash('Книга обновлена', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            conn.rollback()
            flash(f'При сохранении данных возникла ошибка. Проверьте корректность введённых данных. Ошибка: {str(e)}', 'danger')

    cursor.execute('SELECT genre_id FROM book_genres WHERE book_id=%s', (book_id,))
    selected_genres = [row['genre_id'] for row in cursor.fetchall()]

    cursor.execute('SELECT * FROM genres')
    all_genres = cursor.fetchall()

    return render_template('edit_book.html', book=book, all_genres=all_genres, selected_genres=selected_genres)



@app.route('/delete_book/<int:book_id>', methods=['POST'])
@login_required
@check_permission('delete')
def delete_book(book_id):
    conn = mysql.connection()
    cursor = conn.cursor(dictionary=True)

    # Удаление связанных записей из reviews
    cursor.execute('DELETE FROM reviews WHERE book_id=%s', (book_id,))
    conn.commit()

    # Удаление связанных записей из book_genres
    cursor.execute('DELETE FROM book_genres WHERE book_id=%s', (book_id,))
    conn.commit()

    cursor.execute('SELECT cover_id FROM books WHERE id=%s', (book_id,))
    book = cursor.fetchone()

    if not book:
        flash('Книга не найдена', 'danger')
        return redirect(url_for('index'))

    cover_id = book['cover_id']

    cursor.execute('DELETE FROM books WHERE id=%s', (book_id,))
    conn.commit()

    if cover_id:
        cursor.execute('SELECT file_name FROM covers WHERE id=%s', (cover_id,))
        cover = cursor.fetchone()
        if cover:
            cover_path = os.path.join(app.config['UPLOAD_FOLDER'], cover['file_name'])
            if os.path.exists(cover_path):
                os.remove(cover_path)
            cursor.execute('DELETE FROM covers WHERE id=%s', (cover_id,))
            conn.commit()

    flash('Книга удалена', 'success')
    return redirect(url_for('index'))

@app.route('/add_review/<int:book_id>', methods=['GET', 'POST'])
@login_required
def add_review(book_id):
    conn = mysql.connection()
    cursor = conn.cursor(dictionary=True)

    # Проверка, оставлял ли пользователь уже рецензию на эту книгу
    cursor.execute('SELECT * FROM reviews WHERE book_id=%s AND user_id=%s', (book_id, current_user.id))
    existing_review = cursor.fetchone()
    if existing_review:
        flash('Вы уже оставили рецензию на эту книгу.', 'warning')
        return redirect(url_for('view_book', book_id=book_id))

    if request.method == 'POST':
        rating = request.form['rating']
        text = bleach.clean(request.form['text'])
        
        try:
            cursor.execute('''INSERT INTO reviews (book_id, user_id, rating, text)
                              VALUES (%s, %s, %s, %s)''',
                              (book_id, current_user.id, rating, text))
            conn.commit()
            flash('Рецензия добавлена', 'success')
            return redirect(url_for('view_book', book_id=book_id))
        except Exception as e:
            conn.rollback()
            flash(f'При сохранении данных возникла ошибка. Проверьте корректность введённых данных. Ошибка: {str(e)}', 'danger')

    return render_template('add_review.html', book_id=book_id)

@app.route('/view_book/<int:book_id>')
@login_required
@check_permission('show')
def view_book(book_id):
    conn = mysql.connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('SELECT * FROM books WHERE id=%s', (book_id,))
    book = cursor.fetchone()
    if not book:
        flash('Книга не найдена', 'danger')
        return redirect(url_for('index'))

    cursor.execute('SELECT reviews.*, users.first_name, users.last_name FROM reviews JOIN users ON reviews.user_id = users.id WHERE book_id=%s', (book_id,))
    reviews = cursor.fetchall() or []

    cursor.execute('SELECT * FROM covers WHERE id=%s', (book['cover_id'],))
    cover = cursor.fetchone()
    
    description_html = markdown.markdown(book['description'])

    cursor.execute('SELECT * FROM reviews WHERE book_id=%s AND user_id=%s', (book_id, current_user.id))
    user_review = cursor.fetchone()
    
    return render_template('view_book.html', book=book, reviews=reviews, cover=cover, description_html=description_html, user_review=user_review)


if __name__ == '__main__':
    app.run(debug=True)
