from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps
import sqlite3
from datetime import datetime, timedelta
import os


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'library.db')

app = Flask(__name__)
app.secret_key = 'change-this-secret-key'



def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Books table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            isbn TEXT NOT NULL UNIQUE,
            category TEXT,
            copies INTEGER NOT NULL DEFAULT 1,
            available INTEGER NOT NULL DEFAULT 1
        )
    """)

    # Admin table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Default admin
    cursor.execute("""
        INSERT OR IGNORE INTO admin (username, password)
        VALUES (?, ?)
    """, ("admin", "sakthi19"))

    # Issued books table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS issued_books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            borrower_name TEXT NOT NULL,
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            return_date TEXT,
            FOREIGN KEY(book_id) REFERENCES books(id)
        )
    """)

    conn.commit()
    conn.close()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.context_processor
def inject_current_year():
    return {'current_year': datetime.utcnow().year}





@app.route('/')
def home():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db_connection()
        cursor = conn.cursor()

        admin = cursor.execute(
            "SELECT * FROM admin WHERE username=? AND password=?",
            (username, password)
        ).fetchone()

        conn.close()

        if admin:
            session['admin_logged_in'] = True
            flash('Welcome back, Admin!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():

    if request.method == 'POST':

        username = request.form['username']
        new_password = request.form['new_password']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE admin SET password=? WHERE username=?",
            (new_password, username)
        )

        conn.commit()
        conn.close()

        flash("Password changed successfully!", "success")

        return redirect(url_for('login'))

    return render_template('forgot_password.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('admin_logged_in', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    stats = {}
    stats['total_books'] = cursor.execute('SELECT COUNT(*) FROM books').fetchone()[0]
    stats['total_copies'] = cursor.execute('SELECT SUM(copies) FROM books').fetchone()[0] or 0
    stats['available_books'] = cursor.execute('SELECT SUM(available) FROM books').fetchone()[0] or 0
    stats['issued_books'] = cursor.execute('SELECT COUNT(*) FROM issued_books WHERE return_date IS NULL').fetchone()[0]
    overdue_rows = cursor.execute(
        'SELECT ib.id, b.title, b.author, ib.borrower_name, ib.issue_date, ib.due_date '
        'FROM issued_books ib JOIN books b ON ib.book_id = b.id '
        'WHERE ib.return_date IS NULL AND date(ib.due_date) < date(?)',
        (datetime.utcnow().strftime('%Y-%m-%d'),)
    ).fetchall()
    overdue = []
    today = datetime.utcnow().date()
    for row in overdue_rows:
        due_date = datetime.fromisoformat(row['due_date']).date()
        row_data = dict(row)
        row_data['days_late'] = (today - due_date).days
        overdue.append(row_data)
    recent_issues = cursor.execute(
        'SELECT ib.id, b.title, b.author, ib.borrower_name, ib.issue_date, ib.due_date, ib.return_date '
        'FROM issued_books ib JOIN books b ON ib.book_id = b.id '
        'ORDER BY ib.issue_date DESC LIMIT 5'
    ).fetchall()
    conn.close()
    return render_template('dashboard.html', stats=stats, overdue=overdue, recent_issues=recent_issues)


@app.route('/books', methods=['GET', 'POST'])
@login_required
def books():
    conn = get_db_connection()
    cursor = conn.cursor()
    message = None
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        isbn = request.form.get('isbn', '').strip()
        category = request.form.get('category', '').strip()
        copies = int(request.form.get('copies', 1))
        if title and author and isbn and copies > 0:
            try:
                cursor.execute(
                    'INSERT INTO books (title, author, isbn, category, copies, available) VALUES (?, ?, ?, ?, ?, ?)',
                    (title, author, isbn, category, copies, copies)
                )
                conn.commit()
                flash('Book added successfully.', 'success')
            except sqlite3.IntegrityError:
                flash('A book with the same ISBN already exists.', 'danger')
        else:
            flash('Please fill in all required book fields and use positive copies.', 'warning')

    query = request.args.get('q', '').strip()
    if query:
        query_text = f'%{query}%'
        books = cursor.execute(
            'SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ? OR category LIKE ? ORDER BY title',
            (query_text, query_text, query_text, query_text)
        ).fetchall()
    else:
        books = cursor.execute('SELECT * FROM books ORDER BY title').fetchall()
    conn.close()
    return render_template('books.html', books=books, query=query)


@app.route('/books/edit/<int:book_id>', methods=['POST'])
@login_required
def edit_book(book_id):
    title = request.form.get('title', '').strip()
    author = request.form.get('author', '').strip()
    isbn = request.form.get('isbn', '').strip()
    category = request.form.get('category', '').strip()
    copies = int(request.form.get('copies', 1))
    conn = get_db_connection()
    cursor = conn.cursor()
    existing = cursor.execute('SELECT copies, available FROM books WHERE id = ?', (book_id,)).fetchone()
    if not existing:
        flash('Book not found.', 'danger')
        conn.close()
        return redirect(url_for('books'))

    available = existing['available'] + (copies - existing['copies'])
    if available < 0:
        available = 0
    cursor.execute(
        'UPDATE books SET title = ?, author = ?, isbn = ?, category = ?, copies = ?, available = ? WHERE id = ?',
        (title, author, isbn, category, copies, available, book_id)
    )
    conn.commit()
    conn.close()
    flash('Book updated successfully.', 'success')
    return redirect(url_for('books'))


@app.route('/books/delete/<int:book_id>', methods=['POST'])
@login_required
def delete_book(book_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM issued_books WHERE book_id = ?', (book_id,))
    cursor.execute('DELETE FROM books WHERE id = ?', (book_id,))
    conn.commit()
    conn.close()
    flash('Book removed from the catalog.', 'info')
    return redirect(url_for('books'))


@app.route('/issue', methods=['GET', 'POST'])
@login_required
def issue_book():
    conn = get_db_connection()
    cursor = conn.cursor()
    available_books = cursor.execute('SELECT * FROM books WHERE available > 0 ORDER BY title').fetchall()
    if request.method == 'POST':
        book_id = int(request.form.get('book_id', 0))
        borrower_name = request.form.get('borrower_name', '').strip()
        days = int(request.form.get('days', 14))
        if book_id and borrower_name and days > 0:
            issue_date = datetime.utcnow().date()
            due_date = issue_date + timedelta(days=days)
            cursor.execute(
                'INSERT INTO issued_books (book_id, borrower_name, issue_date, due_date) VALUES (?, ?, ?, ?)',
                (book_id, borrower_name, issue_date.isoformat(), due_date.isoformat())
            )
            cursor.execute('UPDATE books SET available = available - 1 WHERE id = ?', (book_id,))
            conn.commit()
            flash('Book issued successfully.', 'success')
            conn.close()
            return redirect(url_for('issue_book'))
        flash('Please select a book, borrower name and valid due days.', 'warning')

    conn.close()
    return render_template('issue.html', books=available_books)


@app.route('/returns', methods=['GET'])
@login_required
def returns():
    conn = get_db_connection()
    cursor = conn.cursor()
    issued = cursor.execute(
        'SELECT ib.id, ib.borrower_name, ib.issue_date, ib.due_date, b.title, b.author '
        'FROM issued_books ib JOIN books b ON ib.book_id = b.id '
        'WHERE ib.return_date IS NULL ORDER BY ib.due_date'
    ).fetchall()
    conn.close()
    return render_template('returns.html', issued=issued)


@app.route('/return/<int:issue_id>', methods=['POST'])
@login_required
def return_book(issue_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    issued = cursor.execute('SELECT book_id FROM issued_books WHERE id = ? AND return_date IS NULL', (issue_id,)).fetchone()
    if issued:
        cursor.execute('UPDATE issued_books SET return_date = ? WHERE id = ?', (datetime.utcnow().date().isoformat(), issue_id))
        cursor.execute('UPDATE books SET available = available + 1 WHERE id = ?', (issued['book_id'],))
        conn.commit()
        flash('Book returned successfully.', 'success')
    else:
        flash('Issue record not found or already returned.', 'warning')
    conn.close()
    return redirect(url_for('returns'))


@app.route('/search')
@login_required
def search_books():
    query = request.args.get('q', '').strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    books = []
    if query:
        query_text = f'%{query}%'
        books = cursor.execute(
            'SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ? OR category LIKE ? ORDER BY title',
            (query_text, query_text, query_text, query_text)
        ).fetchall()
    conn.close()
    return render_template('books.html', books=books, query=query)


if __name__ == '__main__':
     ensure_database()
     app.run(debug=True)
