import sqlite3

conn = sqlite3.connect("notes.db")
cursor = conn.cursor()
cursor.execute("""
    
    SELECT * FROM sections;
""")
for row in cursor.fetchall():
    print(row)
conn.commit()
conn.close()
