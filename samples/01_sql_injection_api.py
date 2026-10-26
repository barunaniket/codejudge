import sqlite3
from flask import Flask, request

app = Flask(__name__)
DB = "users.db"


@app.route("/user")
def get_user():
    username = request.args.get("name")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    query = f"SELECT id, email FROM users WHERE username = '{username}'"
    cur.execute(query)
    row = cur.fetchone()
    return {"id": row[0], "email": row[1]}


@app.route("/search")
def search():
    term = request.args.get("q", "")
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT * FROM products WHERE name LIKE '%" + term + "%'").fetchall()
    return {"results": rows}


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
