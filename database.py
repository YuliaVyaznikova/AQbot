import sqlite3
import logging

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

DATABASE_FILE = "users.db"

def init_db():
    """Initialize the database."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create questions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS questions (
                question_id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER,
                to_user_id INTEGER,
                question_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_answered BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (from_user_id) REFERENCES users (user_id),
                FOREIGN KEY (to_user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Create answers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS answers (
                answer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER,
                answer_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (question_id) REFERENCES questions (question_id)
            )
        ''')
        
        conn.commit()
        logger.info("База данных успешно инициализирована.")
        
        conn.close()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")

def add_question(from_user_id: int, to_user_id: int, question_text: str) -> int:
    """Add a new question to the database."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO questions (from_user_id, to_user_id, question_text)
            VALUES (?, ?, ?)
        ''', (from_user_id, to_user_id, question_text))
        
        question_id = cursor.lastrowid
        conn.commit()
        logger.info(f"Добавлен новый вопрос от {from_user_id} к {to_user_id} с ID {question_id}")
        
        conn.close()
        return question_id
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении вопроса: {e}")
        return None

def get_unanswered_questions(user_id: int) -> list:
    """Get all unanswered questions for a user."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT q.question_id, u.username as from_username, q.question_text, q.created_at
            FROM questions q
            LEFT JOIN users u ON q.from_user_id = u.user_id
            WHERE q.to_user_id = ? AND q.is_answered = FALSE
            ORDER BY q.created_at DESC
        ''', (user_id,))
        
        questions = cursor.fetchall()
        conn.close()
        return questions
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении вопросов: {e}")
        return []

def add_answer(question_id: int, answer_text: str) -> int:
    """Add an answer to a question."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        # Add answer
        cursor.execute('''
            INSERT INTO answers (question_id, answer_text)
            VALUES (?, ?)
        ''', (question_id, answer_text))
        
        answer_id = cursor.lastrowid
        
        # Mark question as answered
        cursor.execute('''
            UPDATE questions
            SET is_answered = TRUE
            WHERE question_id = ?
        ''', (question_id,))
        
        conn.commit()
        conn.close()
        return answer_id
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении ответа: {e}")
        return None

def get_question(question_id: int) -> dict:
    """Get question details."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                q.question_id, 
                q.from_user_id,
                u1.username as from_username,
                q.to_user_id,
                u2.username as to_username,
                q.question_text, 
                q.created_at,
                a.answer_id, 
                a.answer_text,
                a.created_at as answer_created_at
            FROM questions q
            LEFT JOIN answers a ON q.question_id = a.question_id
            LEFT JOIN users u1 ON q.from_user_id = u1.user_id
            LEFT JOIN users u2 ON q.to_user_id = u2.user_id
            WHERE q.question_id = ?
        ''', (question_id,))
        
        question = cursor.fetchone()
        conn.close()
        return question
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении вопроса: {e}")
        return None

def add_user(user_id: int, username: str):
    """Add a new user to the database or update their username if they already exist."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        # Check if user already exists
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        existing_user = cursor.fetchone()
        if existing_user:
            logger.info(f"Пользователь {user_id} уже существует в базе данных.")
        
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username) VALUES (?, ?)
        ''', (user_id, username))
        
        conn.commit()
        conn.close()
        logger.info(f"Пользователь {user_id} ({username}) добавлен или обновлен.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при добавлении/обновлении пользователя {user_id}: {e}")

def get_user(user_id: int):
    """Retrieve a user's data from the database."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        if user:
            logger.info(f"Пользователь найден: ID={user[0]}, Username={user[1]}")
        else:
            logger.info(f"Пользователь с ID={user_id} не найден в базе данных")
        
        conn.close()
        # Returns a tuple (user_id, username) or None
        return user
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении пользователя {user_id}: {e}")
        return None