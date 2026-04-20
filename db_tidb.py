#!/usr/bin/env python3
"""
MyanOS — TiDB Cloud Database Module
Connects to TiDB Cloud (Manus.im platform database)
Supports: users, notebooks, cells, executionHistory, aiConversations

Ported from ai_colab_platform drizzle/schema.ts to Python
"""

import pymysql
import json
import time
from datetime import datetime
from pathlib import Path

# ─── TiDB Cloud Config ──────────────────────────────────────────────────────────
# Manus.im platform database
TIDB_CONFIG = {
    'host': 'gateway05.us-east-1.prod.aws.tidbcloud.com',
    'port': 4000,
    'user': '3ALSUXejPqQqPNQ.root',
    'password': '38uh4znmeywa36ygGpv8',
    'database': 'k5v9REA8zeJJPPpXwFJgTA',
    'charset': 'utf8mb4',
    'ssl': {'ssl': {}},
    'connect_timeout': 10,
    'autocommit': True,
}

# Connection pool (simple)
_pool = []
_pool_lock = __import__('threading').Lock()
MAX_POOL_SIZE = 5


def get_connection():
    """Get a database connection from pool or create new one"""
    global _pool
    conn = None
    with _pool_lock:
        if _pool:
            conn = _pool.pop()
            try:
                conn.ping(reconnect=True)
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
    # Create new connection
    try:
        conn = pymysql.connect(**TIDB_CONFIG)
        conn.cursor().execute("SET time_zone = '+00:00'")
        return conn
    except Exception as e:
        print(f"  [DB] TiDB connection failed: {e}")
        return None


def release_connection(conn):
    """Return connection to pool"""
    global _pool
    if conn is None:
        return
    with _pool_lock:
        if len(_pool) < MAX_POOL_SIZE:
            _pool.append(conn)
        else:
            try:
                conn.close()
            except Exception:
                pass


def db_init():
    """Initialize database tables if they don't exist"""
    conn = get_connection()
    if not conn:
        print("  [DB] Cannot initialize — no database connection")
        return False

    try:
        cursor = conn.cursor()

        # Note: users table already exists from Manus.im deployment
        # Only create new tables (notebooks, cells, executionHistory, aiConversations)

        # Notebooks table
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notebooks (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    userId INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
                    INDEX idx_notebooks_userId (userId)
                )
            """)
        except Exception as e:
            print(f"  [DB] notebooks table: {e}")

        # Cells table
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cells (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    notebookId INT NOT NULL,
                    type ENUM('code', 'markdown') NOT NULL,
                    content LONGTEXT NOT NULL,
                    `order` INT NOT NULL,
                    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
                    INDEX idx_cells_notebookId (notebookId)
                )
            """)
        except Exception as e:
            print(f"  [DB] cells table: {e}")

        # Execution history table
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS executionHistory (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    cellId INT NOT NULL,
                    notebookId INT NOT NULL,
                    code LONGTEXT NOT NULL,
                    output LONGTEXT,
                    error LONGTEXT,
                    status ENUM('success', 'error', 'running') NOT NULL,
                    executionTime INT,
                    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    INDEX idx_exec_cellId (cellId),
                    INDEX idx_exec_notebookId (notebookId)
                )
            """)
        except Exception as e:
            print(f"  [DB] executionHistory table: {e}")

        # AI conversations table
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS aiConversations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    notebookId INT NOT NULL,
                    cellId INT,
                    type ENUM('completion', 'explanation', 'generation') NOT NULL,
                    userMessage LONGTEXT NOT NULL,
                    assistantResponse LONGTEXT,
                    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    INDEX idx_ai_notebookId (notebookId)
                )
            """)
        except Exception as e:
            print(f"  [DB] aiConversations table: {e}")

        conn.commit()
        print("  [DB] TiDB tables initialized successfully")
        return True
    except Exception as e:
        print(f"  [DB] Table init error: {e}")
        return False
    finally:
        release_connection(conn)


def db_health():
    """Check database connection health"""
    conn = get_connection()
    if not conn:
        return {'connected': False, 'error': 'Cannot connect to TiDB'}
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        # Try users table
        try:
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
        except Exception:
            user_count = -1  # Table exists but not accessible
        # Try notebooks table
        try:
            cursor.execute("SELECT COUNT(*) FROM notebooks")
            nb_count = cursor.fetchone()[0]
        except Exception:
            nb_count = -1
        return {
            'connected': True,
            'host': TIDB_CONFIG['host'],
            'database': TIDB_CONFIG['database'],
            'users': user_count,
            'notebooks': nb_count,
        }
    except Exception as e:
        return {'connected': False, 'error': str(e)}
    finally:
        release_connection(conn)


# ─── User Operations ─────────────────────────────────────────────────────────────

def get_user_by_openid(open_id):
    """Get user by openId"""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT * FROM users WHERE openId = %s", (open_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"  [DB] get_user_by_openid error: {e}")
        return None
    finally:
        release_connection(conn)


def upsert_user(open_id, name=None, email=None, login_method=None):
    """Create or update user"""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("""
            INSERT INTO users (openId, name, email, loginMethod, lastSignedIn)
            VALUES (%s, %s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE
                name = COALESCE(%s, name),
                email = COALESCE(%s, email),
                loginMethod = COALESCE(%s, loginMethod),
                lastSignedIn = NOW(),
                updatedAt = NOW()
        """, (open_id, name, email, login_method, name, email, login_method))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE openId = %s", (open_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"  [DB] upsert_user error: {e}")
        return None
    finally:
        release_connection(conn)


def list_users():
    """List all users"""
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT id, openId, name, email, loginMethod, role, createdAt, lastSignedIn FROM users ORDER BY createdAt DESC")
        return cursor.fetchall()
    except Exception as e:
        print(f"  [DB] list_users error: {e}")
        return []
    finally:
        release_connection(conn)


# ─── Notebook Operations ─────────────────────────────────────────────────────────

def create_notebook(user_id, title, description=None):
    """Create a new notebook"""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "INSERT INTO notebooks (userId, title, description) VALUES (%s, %s, %s)",
            (user_id, title, description)
        )
        conn.commit()
        cursor.execute("SELECT * FROM notebooks WHERE id = LAST_INSERT_ID()")
        return cursor.fetchone()
    except Exception as e:
        print(f"  [DB] create_notebook error: {e}")
        return None
    finally:
        release_connection(conn)


def get_user_notebooks(user_id):
    """Get all notebooks for a user"""
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT * FROM notebooks WHERE userId = %s ORDER BY updatedAt DESC",
            (user_id,)
        )
        return cursor.fetchall()
    except Exception as e:
        print(f"  [DB] get_user_notebooks error: {e}")
        return []
    finally:
        release_connection(conn)


def get_notebook_by_id(notebook_id, user_id=None):
    """Get notebook by ID (optionally check ownership)"""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        if user_id:
            cursor.execute(
                "SELECT * FROM notebooks WHERE id = %s AND userId = %s",
                (notebook_id, user_id)
            )
        else:
            cursor.execute("SELECT * FROM notebooks WHERE id = %s", (notebook_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"  [DB] get_notebook_by_id error: {e}")
        return None
    finally:
        release_connection(conn)


def update_notebook(notebook_id, title=None, description=None):
    """Update notebook"""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        updates = []
        params = []
        if title is not None:
            updates.append("title = %s")
            params.append(title)
        if description is not None:
            updates.append("description = %s")
            params.append(description)
        if not updates:
            return None
        params.append(notebook_id)
        cursor.execute(f"UPDATE notebooks SET {', '.join(updates)} WHERE id = %s", params)
        conn.commit()
        cursor.execute("SELECT * FROM notebooks WHERE id = %s", (notebook_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"  [DB] update_notebook error: {e}")
        return None
    finally:
        release_connection(conn)


def delete_notebook(notebook_id):
    """Delete notebook and all related data"""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM executionHistory WHERE notebookId = %s", (notebook_id,))
        cursor.execute("DELETE FROM aiConversations WHERE notebookId = %s", (notebook_id,))
        # Get cell IDs first
        cursor.execute("SELECT id FROM cells WHERE notebookId = %s", (notebook_id,))
        cell_ids = [row[0] for row in cursor.fetchall()]
        if cell_ids:
            placeholders = ','.join(['%s'] * len(cell_ids))
            cursor.execute(f"DELETE FROM executionHistory WHERE cellId IN ({placeholders})", cell_ids)
            cursor.execute(f"DELETE FROM aiConversations WHERE cellId IN ({placeholders})", cell_ids)
        cursor.execute("DELETE FROM cells WHERE notebookId = %s", (notebook_id,))
        cursor.execute("DELETE FROM notebooks WHERE id = %s", (notebook_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"  [DB] delete_notebook error: {e}")
        return False
    finally:
        release_connection(conn)


# ─── Cell Operations ────────────────────────────────────────────────────────────

def create_cell(notebook_id, cell_type, content, order):
    """Create a new cell"""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "INSERT INTO cells (notebookId, type, content, `order`) VALUES (%s, %s, %s, %s)",
            (notebook_id, cell_type, content, order)
        )
        conn.commit()
        cursor.execute("SELECT * FROM cells WHERE id = LAST_INSERT_ID()")
        return cursor.fetchone()
    except Exception as e:
        print(f"  [DB] create_cell error: {e}")
        return None
    finally:
        release_connection(conn)


def get_notebook_cells(notebook_id):
    """Get all cells for a notebook ordered by position"""
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT * FROM cells WHERE notebookId = %s ORDER BY `order` ASC",
            (notebook_id,)
        )
        return cursor.fetchall()
    except Exception as e:
        print(f"  [DB] get_notebook_cells error: {e}")
        return []
    finally:
        release_connection(conn)


def update_cell(cell_id, content=None):
    """Update cell content"""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        if content is not None:
            cursor.execute("UPDATE cells SET content = %s WHERE id = %s", (content, cell_id))
            conn.commit()
        cursor.execute("SELECT * FROM cells WHERE id = %s", (cell_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"  [DB] update_cell error: {e}")
        return None
    finally:
        release_connection(conn)


def delete_cell(cell_id):
    """Delete a cell"""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM executionHistory WHERE cellId = %s", (cell_id,))
        cursor.execute("DELETE FROM aiConversations WHERE cellId = %s", (cell_id,))
        cursor.execute("DELETE FROM cells WHERE id = %s", (cell_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"  [DB] delete_cell error: {e}")
        return False
    finally:
        release_connection(conn)


def reorder_cells(notebook_id, cell_ids):
    """Reorder cells"""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        for idx, cell_id in enumerate(cell_ids):
            cursor.execute(
                "UPDATE cells SET `order` = %s WHERE id = %s AND notebookId = %s",
                (idx, cell_id, notebook_id)
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"  [DB] reorder_cells error: {e}")
        return False
    finally:
        release_connection(conn)


# ─── Execution History ──────────────────────────────────────────────────────────

def create_execution_record(cell_id, notebook_id, code, status, output, error, execution_time):
    """Record code execution"""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("""
            INSERT INTO executionHistory (cellId, notebookId, code, status, output, error, executionTime)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (cell_id, notebook_id, code, status, output, error, execution_time))
        conn.commit()
        cursor.execute("SELECT * FROM executionHistory WHERE id = LAST_INSERT_ID()")
        return cursor.fetchone()
    except Exception as e:
        print(f"  [DB] create_execution_record error: {e}")
        return None
    finally:
        release_connection(conn)


def get_cell_execution_history(cell_id):
    """Get execution history for a cell"""
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT * FROM executionHistory WHERE cellId = %s ORDER BY createdAt DESC LIMIT 20",
            (cell_id,)
        )
        return cursor.fetchall()
    except Exception as e:
        print(f"  [DB] get_cell_execution_history error: {e}")
        return []
    finally:
        release_connection(conn)


# ─── AI Conversations ───────────────────────────────────────────────────────────

def create_ai_conversation(notebook_id, conv_type, user_message, assistant_response, cell_id=None):
    """Record AI conversation"""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("""
            INSERT INTO aiConversations (notebookId, cellId, type, userMessage, assistantResponse)
            VALUES (%s, %s, %s, %s, %s)
        """, (notebook_id, cell_id, conv_type, user_message, assistant_response))
        conn.commit()
        cursor.execute("SELECT * FROM aiConversations WHERE id = LAST_INSERT_ID()")
        return cursor.fetchone()
    except Exception as e:
        print(f"  [DB] create_ai_conversation error: {e}")
        return None
    finally:
        release_connection(conn)


# ─── Self-Test ──────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("Testing TiDB connection...")
    health = db_health()
    print(json.dumps(health, indent=2, default=str))
    if health.get('connected'):
        print("\nInitializing tables...")
        db_init()
        print("\nDone!")
