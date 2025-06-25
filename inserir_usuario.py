from pymongo import MongoClient

# 1. CONEXÃO COM MONGODB ATLAS
MONGO_URI = "mongodb+srv://bibliotecaluizcarlos:terra166@cluster0.uyvqnek.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGO_URI)

# 2. SELECIONA O BANCO E A COLEÇÃO
db = client["sistema_fardas"]
usuarios_col = db["usuarios"]

# 3. DADOS DO NOVO USUÁRIO
novo_usuario = {
    "usuario": "admin",
    "senha": "1234"
}

# 4. INSERE O USUÁRIO CASO NÃO EXISTA
if usuarios_col.find_one({"usuario": novo_usuario["usuario"]}):
    print("⚠️ Usuário já existe.")
else:
    usuarios_col.insert_one(novo_usuario)
    print("✅ Usuário inserido com sucesso.")
