import sqlite3

# Conecta ao seu banco de dados
conn = sqlite3.connect('banco_provas.db')
cursor = conn.cursor()

try:
    # Executa o comando para adicionar a nova coluna
    cursor.execute("ALTER TABLE questoes ADD COLUMN uso TEXT DEFAULT 'PROVA';")
    conn.commit()
    print("✅ Coluna 'uso' adicionada com sucesso!")
except sqlite3.OperationalError:
    print("⚠️ A coluna 'uso' já existe ou houve um erro de digitação.")
finally:
    conn.close()