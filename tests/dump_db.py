import sqlite3

conn = sqlite3.connect("intel.db")
cur = conn.cursor()

# Print table schema
cur.execute("PRAGMA table_info(events);")
print("Table schema:", cur.fetchall())

# Print first 10 rows
cur.execute("SELECT * FROM events LIMIT 10;")
rows = cur.fetchall()
for row in rows:
    print(row)

conn.close()