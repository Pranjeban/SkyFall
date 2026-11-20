import sqlite3

conn = sqlite3.connect(r'C:\Users\pranj\OneDrive\Documents\Skyfall(1)\Skyfall\Data_Memory\skyfall_memory.sqlite3')
cursor = conn.cursor()

print('=== All tables ===')
cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name")
rows = cursor.fetchall()
for r in rows:
    print(f'{r[0]}: {r[1]}')

print('\n=== Table contents ===')
for r in rows:
    table_name = r[0]
    try:
        cursor.execute(f'SELECT * FROM {table_name} LIMIT 5')
        rows_data = cursor.fetchall()
        cursor.execute(f'PRAGMA table_info({table_name})')
        cols = cursor.fetchall()
        print(f'\n{table_name}:')
        print(f'  Columns: {cols}')
        print(f'  Rows (first 5): {rows_data}')
    except Exception as e:
        print(f'\n{table_name}: ERROR - {e}')

conn.close()