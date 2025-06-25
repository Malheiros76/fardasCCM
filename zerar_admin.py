import sqlite3

conn = sqlite3.connect("fardas.db")
c = conn.cursor()

# Criar usuário admin
c.execute("INSERT INTO usuarios (usuario, senha) VALUES (?, ?)", ("admin", "admin123"))
conn.commit()
conn.close()

print("Usuário admin criado com sucesso!")
