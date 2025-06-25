from pymongo import MongoClient

client = MongoClient("mongodb+srv://bibliotecaluizcarlos:terra166@cluster0.uyvqnek.mongodb.net/")
db = client["fardasDB"]
usuarios_col = db["usuarios"]

# Cria usuário admin se não existir
if usuarios_col.find_one({"usuario": "admin"}) is None:
    usuarios_col.insert_one({"usuario": "admin", "senha": "admin123"})
    print("Usuário admin criado com sucesso!")
else:
    print("Usuário admin já existe.")
