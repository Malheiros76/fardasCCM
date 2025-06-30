import streamlit as st
from pymongo import MongoClient
from datetime import datetime
import pandas as pd
import urllib.parse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
import smtplib
from email.mime.text import MIMEText
import os
import bcrypt

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
    try:
        if isinstance(senha_hash, str):
            senha_hash = senha_hash.encode('utf-8')
        return bcrypt.checkpw(senha_plain.encode(), senha_hash)
    except:
        return False

def autenticar(usuario, senha):
    user = usuarios_col.find_one({"usuario": usuario})
    if user:
        senha_hash = user.get("senha", "")
        if verificar_senha(senha, senha_hash):
            st.session_state['usuario_logado'] = usuario
            st.session_state['nivel_usuario'] = user.get("nivel", "user")
            return True
    return False

def migrar_senhas_texto_para_hash():
    usuarios = list(usuarios_col.find())
    count_atualizados = 0

    for user in usuarios:
        senha_atual = user.get("senha", "")
        if not (senha_atual.startswith("$2b$") or senha_atual.startswith("$2a$")):
            novo_hash = hash_senha(senha_atual)
            usuarios_col.update_one(
                {"_id": user["_id"]},
                {"$set": {"senha": novo_hash.decode('utf-8')}}
            )
            count_atualizados += 1

    st.success(f"Migradas {count_atualizados} senhas para hash bcrypt.")

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
            server.login('bibliotecaluizcarlos@gmail.com', 'terra166')  # Atenção: use senha app!
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

    # Menu com controle de acesso
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

    # Botão para migrar senhas - só admin
    if st.session_state.get("nivel_usuario") == "admin":
        if st.button("Migrar senhas texto para hash (Admin)"):
            migrar_senhas_texto_para_hash()

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
            if st.button("Gerar PDF"):
                nome_pdf = f"relatorio_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
                cpdf = canvas.Canvas(nome_pdf, pagesize=A4)
                # Cabeçalho com logo e título
                try:
                    cpdf.drawImage("CABEÇARIOAPP.png", 2*cm, 27*cm, width=16*cm, height=3*cm)
                except:
                    pass
                cpdf.setFont("Helvetica-Bold", 16)
                cpdf.drawString(2*cm, 24*cm, "Relatório de Estoque")
                y = 22*cm
                for i, row in df.iterrows():
                    texto = f"{row['produto']} - Entrada: {row['entrada']} - Saída: {row['saida']} - Saldo: {row['saldo']}"
                    cpdf.drawString(2*cm, y, texto)
                    y -= 0.6*cm
                    if y < 2*cm:
                        cpdf.showPage()
                        try:
                            cpdf.drawImage("CABEÇARIOAPP.png", 2*cm, 27*cm, width=16*cm, height=3*cm)
                        except:
                            pass
                        cpdf.setFont("Helvetica-Bold", 16)
                        cpdf.drawString(2*cm, 24*cm, "Relatório de Estoque (Continuação)")
                        y = 22*cm
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

    # --- ABA ALUNOS ---
elif menu == "Alunos":
    st.subheader("Registro de Entrega de Fardas aos Alunos")

    # Busca todos os alunos cadastrados
    alunos = list(alunos_col.find())
    nomes_alunos = [a["nome"] for a in alunos] if alunos else []

    aluno_nome = st.selectbox("Aluno", nomes_alunos)

    turma = ""
    cgm = ""
    sexo_aluno = ""
    if aluno_nome:
        # Busca dados do aluno selecionado
        aluno_data = alunos_col.find_one({"nome": aluno_nome})
        turma = aluno_data.get("turma", "")
        cgm = aluno_data.get("cgm", "")
        sexo_aluno = aluno_data.get("sexo", "")

    st.text(f"CGM: {cgm}")
    st.text(f"Turma: {turma}")
    st.text(f"Sexo: {sexo_aluno}")

    # Produtos e tamanhos separados por sexo
    produtos_por_sexo = {
        "Masculino": {
            "CAMISA FARDA MASC.": ["6", "7", "8", "9", "10", "11", "12"],
            "CALÇA FARDA MASC.": ["46", "48", "50", "52", "54", "56", "58", "60"],
        },
        "Feminino": {
            "CAMISA FARDA FEM.": ["6", "7", "10", "11", "12", "34", "G1", "GG"],
            "CALÇA FARDA FEM.": ["46", "48", "50", "52", "54", "56", "58"],
        },
        "Unissex": {
            "JAQUETA": ["EXG", "G1", "G2", "G3", "G4"],
            "CONJUNTO ABRIGO - Jaqueta": ["EXG", "G1", "G2", "G3", "G4"],
            "CONJUNTO ABRIGO - Calça": ["EXG", "G1", "G2", "G3", "G4"],
            "BOINA": ["Único"],
        }
    }

    with st.form("entrega_farda_form"):
        if sexo_aluno:
            # Combina produtos do sexo do aluno + unissex
            produtos_selecionaveis = {
                **produtos_por_sexo.get(sexo_aluno, {}),
                **produtos_por_sexo["Unissex"]
            }
        else:
            # Caso sexo não informado, mostra tudo
            produtos_selecionaveis = {}
            for grupo in produtos_por_sexo.values():
                produtos_selecionaveis.update(grupo)

        produto = st.selectbox("Produto", list(produtos_selecionaveis.keys()))

        tamanhos = produtos_selecionaveis[produto]
        tamanho = st.selectbox("Tamanho", tamanhos)

        quantidade = st.number_input("Quantidade", min_value=1, step=1)

        enviar = st.form_submit_button("Salvar Entrega")

        if enviar and aluno_nome:
            movimentacao_aluno_col.insert_one({
                "aluno": aluno_nome,
                "cgm": cgm,
                "turma": turma,
                "sexo": sexo_aluno,
                "peca": produto,
                "tamanho": tamanho,
                "quantidade": quantidade,
                "data": datetime.now().strftime("%Y-%m-%d")
            })
            st.success(f"Entrega registrada: {produto} - Tam. {tamanho} - {quantidade} unidade(s)")

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
            if not df.empty:
                st.dataframe(df[["peca", "tamanho", "quantidade", "data"]])
            if st.button("Devolver todas as peças"):
                movimentacao_aluno_col.delete_many({"aluno": aluno_nome})
                st.success("Peças devolvidas ao estoque.")
        else:
            st.info("Nenhum registro encontrado para este aluno.")
            # --- ABA IMPORTAR ALUNOS ---
    elif menu == "Importar Alunos":
        st.subheader("Importar Alunos via TXT ou CSV")
    
        arquivo = st.file_uploader("Arquivo de alunos", type=["txt", "csv"])
        delimitador = st.selectbox("Delimitador", [";", ",", "\\t"])
    
        if arquivo:
            delimitador_real = {";": ";", ",": ",", "\\t": "\t"}[delimitador]
            try:
                df_alunos = pd.read_csv(arquivo, delimiter=delimitador_real)
                st.dataframe(df_alunos)
    
                if st.button("Importar Alunos"):
                    for _, row in df_alunos.iterrows():
                        alunos_col.update_one(
                            {"cgm": str(row["cgm"])},
                            {
                                "$set": {
                                    "nome": str(row["nome"]),
                                    "turma": str(row["turma"]),
                                    "sexo": str(row.get("sexo", ""))   # Novo campo
                                }
                            },
                            upsert=True
                        )
                    st.success("Alunos importados com sucesso!")
            except Exception as e:
                st.error(f"Erro ao importar arquivo: {e}")
    # --- CADASTRO DE USUÁRIOS ---
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
            nivel = st.selectbox("Nível", ["admin", "user"])
            submit = st.form_submit_button("Cadastrar")

            if submit:
                if novo_usuario and nova_senha:
                    if usuarios_col.find_one({"usuario": novo_usuario}):
                        st.warning("Usuário já existe!")
                    else:
                        # Salvar senha já hashada
                        senha_hash = hash_senha(nova_senha).decode('utf-8')
                        usuarios_col.insert_one({
                            "usuario": novo_usuario,
                            "senha": senha_hash,
                            "nivel": nivel
                        })
                        st.success(f"Usuário {novo_usuario} cadastrado com sucesso!")
                        st.experimental_rerun()
                else:
                    st.error("Usuário e senha são obrigatórios.")

    # --- SAIR ---
    elif menu == "🚪 Sair do Sistema":
        st.session_state.logado = False
        st.session_state.pop('usuario_logado', None)
        st.session_state.pop('nivel_usuario', None)
        st.experimental_rerun()
