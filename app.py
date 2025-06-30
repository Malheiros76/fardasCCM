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

def autenticar(usuario, senha):
    return usuarios_col.find_one({"usuario": usuario, "senha": senha}) is not None

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
            server.login('bibliotecaluizcarlos@gmail.com', 'terra166') # ajuste para senha de app se necessário
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
            if autenticar(usuario, senha):
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

    menu = st.sidebar.selectbox(
        "Menu",
        [
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
    )

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
            funcionario = st.selectbox("Funcionário", funcionarios if funcionarios else ["Nenhum funcionário cadastrado"])
            produtos_cadastrados = [p["produto"] for p in produtos_col.find({}, {"produto": 1})]
            produto = st.selectbox("Produto", produtos_cadastrados if produtos_cadastrados else ["Nenhum produto cadastrado"])
            quantidade = st.number_input("Quantidade", min_value=1, step=1)
            if st.form_submit_button("Registrar"):
                if funcionario and produto and quantidade:
                    movimentacao_col.insert_one({
                        "data": data.strftime("%Y-%m-%d"),
                        "tipo": tipo,
                        "funcionario": funcionario,
                        "produto": produto,
                        "quantidade": quantidade
                    })
                    produtos_col.update_one({"produto": produto}, {"$set": {"produto": produto}}, upsert=True)
                    st.success("Movimentação registrada!")

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
                cpdf.setFont("Helvetica-Bold", 16)
                cpdf.drawString(2*cm, 28*cm, "Relatório de Estoque")
                y = 26*cm
                for i, row in df.iterrows():
                    texto = f"{row['produto']} - Entrada: {row['entrada']} - Saída: {row['saida']} - Saldo: {row['saldo']}"
                    cpdf.drawString(2*cm, y, texto)
                    y -= 0.6*cm
                    if y < 2*cm:
                        cpdf.showPage()
                        y = 28*cm
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
        alunos = list(alunos_col.find())
        nomes_alunos = [a["nome"] for a in alunos] if alunos else []
        aluno_nome = st.selectbox("Aluno", nomes_alunos)
        turma = ""
        cgm = ""
        if aluno_nome:
            aluno_data = alunos_col.find_one({"nome": aluno_nome})
            turma = aluno_data.get("turma", "")
            cgm = aluno_data.get("cgm", "")
        st.text(f"CGM: {cgm}")
        st.text(f"Turma: {turma}")

        # Dicionário com tamanhos por peça
        tamanhos_por_peca = {
            "jaqueta": ["EXG", "G1", "G2", "G3", "G4"],
            "calça_conjunto_abrigo": ["EXG", "G1", "G2", "G3", "G4"],
            "camisa_farda_masculina": ["6", "7", "8", "9", "10", "11", "12"],
            "camisa_farda_feminina": ["6", "7", "10", "11", "12", "34", "G1", "GG"],
            "calça_farda_masculina": ["46", "48", "50", "52", "54", "56", "58", "60"],
            "calça_farda_feminina": ["46", "48", "50", "52", "54", "56", "58"],
            "boina": ["P", "M", "G", "GG"]
        }

        # Lista de peças com nome do arquivo e chave para tamanhos
        pecas = [
            ("boina.png", "boina"),
            ("conjunto_abrigo.png", "jaqueta"),
            ("calça_farda.png", "calça_farda_masculina"),
            ("camisa_farda_masc.png", "camisa_farda_masculina"),
            ("camisa_farda_fem.png", "camisa_farda_feminina"),
            ("calça_farda_fem.png", "calça_farda_feminina"),
            ("calça_conjunto_abrigo.png", "calça_conjunto_abrigo")
        ]

        entrega = {}
        cols = st.columns(3)
        for idx, (imagem, nome_peca) in enumerate(pecas):
            with cols[idx % 3]:
                img_path = os.path.join("images", imagem)
                if os.path.exists(img_path):
                    st.image(img_path, width=120)
                
                qtd = st.number_input(
                    f"Qtd {nome_peca}",
                    min_value=0,
                    step=1,
                    key=f"qtd_{nome_peca}"
                )

                tamanhos_opcoes = tamanhos_por_peca.get(nome_peca, ["Único"])
                tam = st.selectbox(
                    f"Tamanho {nome_peca}",
                    tamanhos_opcoes,
                    key=f"tam_{nome_peca}"
                )
                
                entrega[nome_peca] = {
                    "quantidade": qtd,
                    "tamanho": tam
                }

        if st.button("Salvar Entrega"):
            for peca, dados in entrega.items():
                if dados["quantidade"] > 0:
                    movimentacao_aluno_col.insert_one({
                        "aluno": aluno_nome,
                        "cgm": cgm,
                        "turma": turma,
                        "peca": peca,
                        "quantidade": dados["quantidade"],
                        "tamanho": dados["tamanho"],
                        "data": datetime.now().strftime("%Y-%m-%d")
                    })
            st.success("Registro salvo com sucesso!")

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
                st.dataframe(df[["peca", "quantidade", "tamanho", "data"]])
                if st.button("Devolver todas as peças"):
                    movimentacao_aluno_col.delete_many({"aluno": aluno_nome})
                    st.success("Peças devolvidas ao estoque.")
            else:
                st.info("Nenhum registro encontrado para este aluno.")

    # --- IMPORTAR ALUNOS ---
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
                                    "turma": str(row["turma"])
                                }
                            },
                            upsert=True
                        )
                    st.success("Alunos importados com sucesso!")
            except Exception as e:
                st.error(f"Erro ao importar arquivo: {e}")

    # --- SAIR ---
    elif menu == "🚪 Sair do Sistema":
        st.session_state.logado = False
        st.rerun()
