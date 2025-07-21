import streamlit as st
from pymongo import MongoClient
from datetime import datetime
import pandas as pd
import urllib.parse
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
import smtplib
from email.mime.text import MIMEText
import os
import bcrypt
from reportlab.lib.pagesizes import A4, landscape

# --- CONFIGURAÇÃO DE MONGO ---
client = MongoClient("mongodb+srv://bibliotecaluizcarlos:terra166@cluster0.uyvqnek.mongodb.net/?retryWrites=true&w=majority")
db = client["fardasDB"]

usuarios_col = db["usuarios"]
cadastro_col = db["cadastro"]
produtos_col = db["produtos"]
movimentacao_col = db["movimentacao"]
alunos_col = db["alunos"]
movimentacao_aluno_col = db["movimentacao_aluno"]

# --- FUNÇÕES AUXILIARES ---

def hash_senha(senha):
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt())

def verificar_senha(senha_plain, senha_hash):
    if isinstance(senha_hash, str):
        senha_hash = senha_hash.encode('utf-8')
    return bcrypt.checkpw(senha_plain.encode(), senha_hash)

def autenticar(usuario, senha):
    user = usuarios_col.find_one({"usuario": usuario})
    if user:
        senha_hash = user["senha"]
        if verificar_senha(senha, senha_hash):
            st.session_state['usuario_logado'] = usuario
            st.session_state['nivel_usuario'] = user.get("nivel", "user")
            return True
    return False

def alerta_estoque():
    pipeline = [
        {
            "$group": {
                "_id": "$produto",
                "entrada": {"$sum": {"$cond": [{"$eq": ["$tipo", "Entrada"]}, "$quantidade", 0]}},
                "saida": {"$sum": {"$cond": [{"$eq": ["$tipo", "Saída"]}, "$quantidade", 0]}}
            }
        }
    ]
    resultados = list(movimentacao_col.aggregate(pipeline))
    mensagens = []
    for r in resultados:
        saldo = r["entrada"] - r["saida"]
        limite = r["entrada"] * 0.2
        if saldo < limite:
            mensagens.append(f"Produto {r['_id']} está abaixo do limite. Saldo atual: {saldo}")
    return mensagens

def enviar_email(destinatario, mensagem):
    try:
        msg = MIMEText(mensagem)
        msg['Subject'] = 'Alerta de Estoque Baixo'
        msg['From'] = 'bibliotecaluizcarlos@gmail.com'
        msg['To'] = destinatario
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login('bibliotecaluizcarlos@gmail.com', 'terra166') # senha de app se precisar
            server.send_message(msg)
    except Exception as e:
        st.error(f"Erro ao enviar email: {e}")

def enviar_whatsapp(numero, mensagem):
    numero = numero.replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
    texto = urllib.parse.quote(mensagem)
    url = f"https://wa.me/55{numero}?text={texto}"
    st.markdown(f"[Abrir WhatsApp]({url})")

def calcular_estoque():
    pipeline = [
        {
            "$group": {
                "_id": "$produto",
                "entrada": {"$sum": {"$cond": [{"$eq": ["$tipo", "Entrada"]}, "$quantidade", 0]}},
                "saida": {"$sum": {"$cond": [{"$eq": ["$tipo", "Saída"]}, "$quantidade", 0]}}
            }
        }
    ]
    resultados = list(movimentacao_col.aggregate(pipeline))
    lista = []
    for r in resultados:
        saldo = r["entrada"] - r["saida"]
        lista.append({
            "produto": r["_id"],
            "entrada": r["entrada"],
            "saida": r["saida"],
            "saldo": saldo
        })
    return pd.DataFrame(lista)

# --- INÍCIO DO APP ---
st.set_page_config(page_title="Sistema de Fardas", layout="wide")

st.title("Sistema de Controle de Fardas")

if "logado" not in st.session_state:
    st.session_state.logado = False

if not st.session_state.logado:
    st.subheader("Login do Sistema")
    with st.form("login"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if autenticar(usuario.strip(), senha.strip()):
                st.session_state.logado = True
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")
else:
    mensagens = alerta_estoque()
    for msg in mensagens:
        st.warning(msg)
        cadastros = list(cadastro_col.find({}, {"email": 1, "telefone": 1}))
        for cadastro in cadastros:
            if cadastro.get("email"):
                enviar_email(cadastro["email"], msg)
            if cadastro.get("telefone"):
                enviar_whatsapp(cadastro["telefone"], msg)

    # Menu
    if st.session_state.get("nivel_usuario") == "admin":
        opcoes_menu = [
            "Cadastro Geral",
            "Movimentação",
            "Estoque",
            "Relatórios",
            "Importar Estoque",
            "Alunos",
            "Consultar Aluno",
            "Importar Alunos",
            "Cadastro de Usuários",
            "🚪 Sair do Sistema"
        ]
    else:
        opcoes_menu = [
            "Cadastro Geral",
            "Movimentação",
            "Estoque",
            "Relatórios",
            "Importar Estoque",
            "Alunos",
            "Consultar Aluno",
            "Importar Alunos",
            "🚪 Sair do Sistema"
        ]

    menu = st.sidebar.selectbox("Menu", opcoes_menu)

    # --- ABA CADASTRO GERAL ---
    if menu == "Cadastro Geral":
        st.subheader("Cadastro de Funcionários")
        with st.form("cadastro_func"):
            nome = st.text_input("Nome")
            setor = st.text_input("Setor")
            funcao = st.text_input("Função")
            email = st.text_input("Email")
            telefone = st.text_input("Telefone")
            if st.form_submit_button("Salvar"):
                if nome and setor and funcao and email and telefone:
                    cadastro_col.insert_one({
                        "nome": nome,
                        "setor": setor,
                        "funcao": funcao,
                        "email": email,
                        "telefone": telefone
                    })
                    st.success("Funcionário cadastrado!")
                else:
                    st.error("Todos os campos são obrigatórios.")

    # --- ABA MOVIMENTAÇÃO ---
    elif menu == "Movimentação":
        st.subheader("Entrada e Saída de Produtos")
        with st.form("movimento"):
            data = st.date_input("Data", datetime.now())
            tipo = st.selectbox("Tipo", ["Entrada", "Saída"])
            funcionarios = [f["nome"] for f in cadastro_col.find({}, {"nome": 1})]
            if not funcionarios:
                st.warning("Nenhum funcionário cadastrado! Cadastre antes.")
                funcionario = None
            else:
                funcionario = st.selectbox("Funcionário", funcionarios)
            produtos_cadastrados = [p["produto"] for p in produtos_col.find({}, {"produto": 1})]
            if not produtos_cadastrados:
                st.warning("Nenhum produto cadastrado! Cadastre antes.")
                produto = None
            else:
                produto = st.selectbox("Produto", produtos_cadastrados)
            quantidade = st.number_input("Quantidade", min_value=1, step=1)
            if st.form_submit_button("Registrar"):
                if funcionario and produto and quantidade > 0:
                    movimentacao_col.insert_one({
                        "data": data.strftime("%Y-%m-%d"),
                        "tipo": tipo,
                        "funcionario": funcionario,
                        "produto": produto,
                        "quantidade": quantidade
                    })
                    produtos_col.update_one({"produto": produto}, {"$set": {"produto": produto}}, upsert=True)
                    st.success("Movimentação registrada!")
                else:
                    st.error("Preencha todos os campos corretamente.")

    # --- ABA ESTOQUE ---
    elif menu == "Estoque":
        st.subheader("Estoque Atual")
        df = calcular_estoque()
        if not df.empty:
            df["situação"] = df.apply(
                lambda row: "🔴 Crítico" if row["saldo"] <= 0 else (
                    "🟡 Atenção" if row["saldo"] < row["entrada"] * 0.2 else "🟢 OK"
                ), axis=1
            )
            st.dataframe(df)
        else:
            st.info("Nenhum dado de movimentação encontrado.")

    # --- ABA RELATÓRIOS ---    
    elif menu == "Relatórios":
        st.subheader("Relatórios de Estoque")
        df = calcular_estoque()
        if df.empty:
            st.info("Nenhum dado para gerar relatório.")
        else:
            st.dataframe(df)
            from reportlab.lib.pagesizes import A4, landscape
    if st.button("Gerar PDF"):
        nome_pdf = f"relatorio_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        
        # Define a página como A4 deitada
        cpdf = canvas.Canvas(nome_pdf, pagesize=landscape(A4))
    
        try:
            cpdf.drawImage("cabeca.png", 2*cm, 18*cm, width=24*cm, height=3*cm)
        except:
            pass
    
        cpdf.setFont("Helvetica-Bold", 16)
        cpdf.drawString(2*cm, 15*cm, "Relatório de Estoque")
    
        y = 13*cm  # posição vertical inicial, ajustada para paisagem
        for i, row in df.iterrows():
            texto = f"{row['produto']} - Entrada: {row['entrada']} - Saída: {row['saida']} - Saldo: {row['saldo']}"
            cpdf.drawString(2*cm, y, texto)
            y -= 0.6*cm
            if y < 2*cm:
                cpdf.showPage()
                try:
                    cpdf.drawImage("CABECARIOAPP.png", 2*cm, 18*cm, width=24*cm, height=3*cm)
                except:
                    pass
                cpdf.setFont("Helvetica-Bold", 16)
                cpdf.drawString(2*cm, 15*cm, "Relatório de Estoque (Continuação)")
                y = 13*cm
    
        cpdf.save()
    
        with open(nome_pdf, "rb") as f:
            st.download_button("Baixar PDF", f, file_name=nome_pdf)
            
    # --- ABA IMPORTAR ESTOQUE ---
    elif menu == "Importar Estoque":
        st.subheader("Importar Estoque via TXT ou CSV")
        arquivo = st.file_uploader("Arquivo", type=["txt", "csv"])
        delimitador = st.selectbox("Delimitador", [";", ",", "\\t"])
        if arquivo:
            delimitador_real = {";": ";", ",": ",", "\\t": "\t"}[delimitador]
            try:
                df = pd.read_csv(arquivo, delimiter=delimitador_real)
                st.dataframe(df)
                if st.button("Importar"):
                    for _, row in df.iterrows():
                        movimentacao_col.insert_one({
                            "data": str(row.get("data", datetime.now().strftime("%Y-%m-%d"))),
                            "tipo": row.get("tipo"),
                            "funcionario": row.get("funcionario"),
                            "produto": row.get("produto"),
                            "quantidade": int(row.get("quantidade", 0))
                        })
                        produtos_col.update_one({"produto": row.get("produto")}, {"$set": {"produto": row.get("produto")}}, upsert=True)
                    st.success("Importação concluída!")
            except Exception as e:
                st.error(f"Erro ao importar arquivo: {e}")

    elif menu == "Alunos":
        st.subheader("Registro de Entrega de Fardas aos Alunos")
            
        alunos = list(alunos_col.find())
        nomes_alunos = [a["nome"] for a in alunos] if alunos else []
            
        aluno_nome = st.selectbox("Aluno", nomes_alunos)
         
# Buscar os dados do aluno selecionado
        aluno_selecionado = next((a for a in alunos if a["nome"] == aluno_nome), None)
            
        if aluno_selecionado:
                    turma = aluno_selecionado.get("turma", "Sem turma")
                    cgm = aluno_selecionado.get("cgm", "Sem CGM")
                    sexo = aluno_selecionado.get("sexo", "Não informado")
            
                    # Exibir informações
                    st.write(f"**Turma:** {turma}")
                    st.write(f"**CGM:** {cgm}")
                    st.write(f"**Sexo:** {sexo}")


                    # Lista de produtos (imagens)
                    pecas = [
                        "boina.png",
                        "calça_farda.png",
                        "camisa.png",
                        "camisa_farda.png",
                        "conjunto_abrigo.png",
                        "jaqueta_farda.png",
                        "moleton_abrigo.png"
                    ]

        # Dicionário dos tamanhos por produto e sexo
        tamanhos = {
            "jaqueta_farda.png": {
                "masculino": ["EXG", "G1", "G2", "G3", "G4"],
                "feminino": ["EXG", "G1", "G2", "G3", "G4"]
            },
            "conjunto_abrigo.png": {
                "masculino": ["EXG", "G1", "G2", "G3", "G4"],
                "feminino": ["EXG", "G1", "G2", "G3", "G4"]
            },
            "calça_farda.png": {
                "masculino": ["46", "48", "50", "52", "54", "56", "58", "60"],
                "feminino": ["46", "48", "50", "52", "54", "56", "58"]
            },
            "camisa.png": {
                "masculino": ["6", "7", "8", "9", "10", "11", "12"],
                "feminino": ["6", "7", "10", "11", "12", "34", "G1", "GG"]
            },
            "camisa_farda.png": {
                "masculino": ["6", "7", "8", "9", "10", "11", "12"],
                "feminino": ["6", "7", "10", "11", "12", "34", "G1", "GG"]
            },
            "moleton_abrigo.png": {
                "masculino": ["P", "M", "G", "GG"],
                "feminino": ["P", "M", "G", "GG"]
            },
            "boina.png": {
                "masculino": [],
                "feminino": []
            }
        }

        entrega = {}

        for peca in pecas:
            img_path = os.path.join("images", peca)
            nome_peca = peca.replace(".png", "")
            if os.path.exists(img_path):
                st.image(img_path, width=100)
            else:
                st.text(f"{nome_peca} (imagem não encontrada)")

            # Quantidade
            qtd = st.number_input(f"Quantidade de {nome_peca}", min_value=0, step=1, key=f"qtd_{peca}")

            # Tamanhos possíveis
            sex_key = "masculino" if sexo in ["m", "masculino"] else "feminino"
            lista_tamanhos = tamanhos.get(peca, {}).get(sex_key, [])

            if lista_tamanhos:
                tamanho_sel = st.selectbox(f"Tamanho de {nome_peca}", options=[""] + lista_tamanhos, key=f"tam_{peca}")
                if tamanho_sel == "":
                    tamanho_manual = st.text_input(f"Informe o tamanho manual para {nome_peca}", key=f"tam_manual_{peca}")
                    tamanho_final = tamanho_manual.strip()
                else:
                    tamanho_final = tamanho_sel
            else:
                tamanho_final = ""  # produto sem tamanho

            entrega[peca] = {"quantidade": qtd, "tamanho": tamanho_final}

        if st.button("Salvar Entrega"):
            registros_salvos = 0
            for peca, dados in entrega.items():
                qtd = dados["quantidade"]
                tam = dados["tamanho"]
                if qtd > 0:
                    movimentacao_aluno_col.insert_one({
                        "aluno": aluno_nome,
                        "cgm": cgm,
                        "turma": turma,
                        "peca": peca.replace(".png", ""),
                        "quantidade": qtd,
                        "tamanho": tam,
                        "data": datetime.now().strftime("%Y-%m-%d")
                    })
                    registros_salvos += 1
            if registros_salvos > 0:
                st.success(f"{registros_salvos} registro(s) salvo(s) com sucesso!")
            else:
                st.warning("Nenhuma peça foi informada com quantidade maior que zero.")

    # --- CONSULTAR ALUNO ---
    elif menu == "Consultar Aluno":
        st.subheader("Consulta de Entregas de Fardas por Aluno")
        alunos = list(alunos_col.find())
        nomes_alunos = [a["nome"] for a in alunos] if alunos else []
        aluno_nome = st.selectbox("Selecione o aluno", nomes_alunos)
        if aluno_nome:
            registros = list(movimentacao_aluno_col.find({"aluno": aluno_nome}))
            if registros:
                df = pd.DataFrame(registros)
                st.dataframe(df[["peca", "quantidade", "data"]])
                if st.button("Devolver todas as peças"):
                    movimentacao_aluno_col.delete_many({"aluno": aluno_nome})
                    st.success("Peças devolvidas ao estoque.")
            else:
                st.info("Nenhum registro encontrado para este aluno.")

    # --- ABA IMPORTAR ALUNOS ---
    elif menu == "Importar Alunos":
        st.subheader("📚 Importar Alunos via TXT ou CSV")

        if st.button("🧹 Limpar Tabela de Alunos"):
            alunos_col.delete_many({})
            st.success("✅ Coleção 'alunos' limpa com sucesso!")

        st.markdown("---")

        arquivo = st.file_uploader("📂 Selecione o arquivo de alunos", type=["txt", "csv"])
        delimitador = st.selectbox("Delimitador", [";", ",", "\\t"], index=2)

        if arquivo:
            delimitador_real = {";": ";", ",": ",", "\\t": "\t"}[delimitador]
        try:
            df_alunos = pd.read_csv(arquivo, delimiter=delimitador_real)
            st.success("✅ Arquivo carregado com sucesso!")
            st.dataframe(df_alunos)

            if st.button("📥 Importar Alunos"):
                for _, row in df_alunos.iterrows():
                    sexo = str(row["Sexo"]).strip().upper()
                    if sexo == "M":
                        sexo_texto = "Masculino"
                    elif sexo == "F":
                        sexo_texto = "Feminino"
                    else:
                        sexo_texto = ""

                    alunos_col.update_one(
                        {"cgm": str(row["CGM"])},
                        {
                            "$s"
                            "et": {
                                "nome": str(row["Nome do Estudante"]).strip(),
                                "turma": str(row["Turma"]).strip(),
                                "sexo": sexo_texto,
                                "telefone": str(row["Telefone"]).strip()
                            }
                        },
                        upsert=True
                    )
                st.success("✅ Alunos importados com sucesso!")
        except Exception as e:
            st.error(f"❌ Erro ao importar arquivo: {e}")

# --- ABA CADASTRO DE USUÁRIOS ---
    elif menu == "Cadastro de Usuários":
        st.subheader("Cadastro e Gerenciamento de Usuários")

        usuarios = list(usuarios_col.find({}, {"_id": 0, "usuario": 1, "nivel": 1}))

        if usuarios:
            usuarios_formatados = [
                {
                    "usuario": u.get("usuario", ""),
                    "nivel": u.get("nivel", "user")
                }
                for u in usuarios
            ]
            df_usuarios = pd.DataFrame(usuarios_formatados)
            st.dataframe(df_usuarios)
        else:
            st.info("Nenhum usuário cadastrado ainda.")

        st.markdown("---")
        st.markdown("### Novo Usuário")

        with st.form("form_cadastro_usuario"):
            novo_usuario = st.text_input("Novo usuário")
            nova_senha = st.text_input("Senha", type="password")
            confirm_senha = st.text_input("Confirme a senha", type="password")
            nivel = st.selectbox("Nível", ["admin", "user"])
            submit = st.form_submit_button("Cadastrar")

            if submit:
                if not novo_usuario or not nova_senha or not confirm_senha:
                    st.error("Preencha todos os campos.")
                elif nova_senha != confirm_senha:
                    st.error("As senhas não coincidem.")
                elif len(nova_senha) < 6:
                    st.error("Senha muito curta. Mínimo 6 caracteres.")
                elif usuarios_col.find_one({"usuario": novo_usuario}):
                    st.warning("Usuário já existe!")
                else:
                    usuarios_col.insert_one({
                        "usuario": novo_usuario,
                        "senha": hash_senha(nova_senha),
                        "nivel": nivel
                    })
                    st.success(f"Usuário {novo_usuario} cadastrado com sucesso!")
                    st.rerun()

    elif menu == "🚪 Sair do Sistema":
        st.session_state.logado = False
        st.success("Sessão encerrada.")
        st.rerun()
