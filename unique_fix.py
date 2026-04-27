import sqlite3

conn = sqlite3.connect("ems.db")
cursor = conn.cursor()

try:
    cursor.execute("CREATE UNIQUE INDEX idx_username ON employees(username)")
    print("Unique constraint added ✅")
except:
    print("Already exists")

conn.commit()
conn.close()