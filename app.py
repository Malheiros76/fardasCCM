import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
import smtplib
from email.mime.text import MIMEText
import urllib.parse

# Conexão com o banco
conn = sqlite3.connect("fardas.db", check_same_thread=False)
c = conn.cursor()

# Criação de tabelas
c.execute('''CREATE TABLE IF NOT EXISTS usuarios (usuario TEXT PRIMARY KEY, senha TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS cadastro (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, setor TEXT, funcao TEXT, email TEXT, telefone TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS movimentacao (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, tipo TEXT, funcionario TEXT, produto TEXT, quantidade INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS produtos (produto TEXT PRIMARY KEY)''')
conn.commit()

# Funções auxiliares
def autenticar(usuario, senha):
    c.execute("SELECT * FROM usuarios WHERE usuario=? AND senha=?", (usuario, senha))
    return c.fetchone()

def alerta_estoque():
    df = pd.read_sql_query((
        "SELECT produto, "
        "SUM(CASE WHEN tipo='Entrada' THEN quantidade ELSE 0 END) as entrada, "
        "SUM(CASE WHEN tipo='Saída' THEN quantidade ELSE 0 END) as saida "
        "FROM movimentacao GROUP BY produto"
    ), conn)
    mensagens = []
    for i, row in df.iterrows():
        saldo = row['entrada'] - row['saida']
        limite = row['entrada'] * 0.2
        if saldo < limite:
            mensagens.append(f"Produto {row['produto']} está abaixo do limite. Saldo atual: {saldo}")
    return mensagens

def enviar_email(destinatario, mensagem):
    try:
        msg = MIMEText(mensagem)
        msg['Subject'] = 'Alerta de Estoque Baixo'
        msg['From'] = 'sistema@escola.com'
        msg['To'] = destinatario
        with smtplib.SMTP('smtp.seudominio.com', 587) as server:
            server.starttls()
            server.login('seu_email', 'sua_senha')
            server.send_message(msg)
    except:
        pass

def enviar_whatsapp(numero, mensagem):
    numero = numero.replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
    texto = urllib.parse.quote(mensagem)
    url = f"https://wa.me/55{numero}?text={texto}"
    st.markdown(f"[Abrir WhatsApp]({url})")

# Interface
st.set_page_config(page_title="Sistema de Fardas", layout="centered")
st.title("Controle de Fardas")

# Login
if "logado" not in st.session_state:
    st.session_state.logado = False

if not st.session_state.logado:
    with st.form("login"):
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if autenticar(usuario, senha):
                st.session_state.logado = True
                st.rerun()
            else:
                st.error("Usuário ou senha inválido")
else:
    mensagens = alerta_estoque()
    for msg in mensagens:
        st.warning(msg)
        c.execute("SELECT email, telefone FROM cadastro")
        for email, tel in c.fetchall():
            enviar_email(email, msg)
            enviar_whatsapp(tel, msg)

    menu = st.sidebar.selectbox("Menu", ["Cadastro Geral", "Movimentação", "Estoque", "Relatórios", "Importar Estoque"])

    if menu == "Cadastro Geral":
        st.subheader("Cadastro de Funcionários")
        with st.form("cadastro"):
            nome = st.text_input("Nome")
            setor = st.text_input("Setor")
            funcao = st.text_input("Função")
            email = st.text_input("Email")
            telefone = st.text_input("Telefone")
            if st.form_submit_button("Salvar"):
                if nome and setor and funcao and email and telefone:
                    c.execute("INSERT INTO cadastro (nome, setor, funcao, email, telefone) VALUES (?, ?, ?, ?, ?)", (nome, setor, funcao, email, telefone))
                    conn.commit()
                    st.success("Cadastrado com sucesso!")
                else:
                    st.error("Todos os campos são obrigatórios")

    elif menu == "Movimentação":
        st.subheader("Entrada e Saída de Produtos")
        with st.form("movimento"):
            data = st.date_input("Data", datetime.now())
            tipo = st.selectbox("Tipo", ["Entrada", "Saída"])
            funcionarios = [row[0] for row in c.execute("SELECT nome FROM cadastro")]
            funcionario = st.selectbox("Funcionário", funcionarios if funcionarios else ["Nenhum funcionário cadastrado"])
            produto = st.text_input("Produto")
            quantidade = st.number_input("Quantidade", min_value=1, step=1)
            if st.form_submit_button("Registrar"):
                if data and tipo and funcionario and produto and quantidade:
                    c.execute("INSERT INTO movimentacao (data, tipo, funcionario, produto, quantidade) VALUES (?, ?, ?, ?, ?)", (data.strftime("%Y-%m-%d"), tipo, funcionario, produto, quantidade))
                    c.execute("INSERT OR IGNORE INTO produtos (produto) VALUES (?)", (produto,))
                    conn.commit()
                    st.success("Movimentação registrada!")
                else:
                    st.error("Todos os campos são obrigatórios")

    elif menu == "Estoque":
        st.subheader("Estoque Atual")
        df = pd.read_sql_query((
            "SELECT produto, "
            "SUM(CASE WHEN tipo='Entrada' THEN quantidade ELSE 0 END) as entrada, "
            "SUM(CASE WHEN tipo='Saída' THEN quantidade ELSE 0 END) as saida "
            "FROM movimentacao GROUP BY produto"
        ), conn)
        df['saldo'] = df['entrada'] - df['saida']
        def situacao(row):
            limite = row['entrada'] * 0.2
            if row['saldo'] <= 0:
                return '🔴 Crítico'
            elif row['saldo'] < limite:
                return '🟡 Atenção'
            else:
                return '🟢 OK'
        df['situação'] = df.apply(situacao, axis=1)
        st.dataframe(df)

    elif menu == "Relatórios":
        st.subheader("Relatórios")
        opcao = st.selectbox("Tipo de Relatório", ["Por Quantidade", "Por Local", "Por Funcionário"])
        df = pd.read_sql_query("SELECT * FROM movimentacao", conn)
        st.dataframe(df)
        if st.button("Gerar PDF"):
            nome_pdf = f"relatorio_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
            cpdf = canvas.Canvas(nome_pdf, pagesize=A4)
            cpdf.setFont("Helvetica-Bold", 16)
            cpdf.drawString(2*cm, 28*cm, "Relatório de Movimentação de Fardas")
            cpdf.setFont("Helvetica", 12)
            y = 26*cm
            for i, row in df.iterrows():
                texto = f"{row['data']} - {row['tipo']} - {row['funcionario']} - {row['produto']} - {row['quantidade']}"
                cpdf.drawString(2*cm, y, texto)
                y -= 0.6*cm
                if y < 2*cm:
                    cpdf.showPage()
                    y = 28*cm
            cpdf.save()
            with open(nome_pdf, "rb") as f:
                st.download_button("Baixar Relatório", f, file_name=nome_pdf)

    elif menu == "Importar Estoque":
        st.subheader("Importar Estoque via Arquivo .TXT")
        arquivo = st.file_uploader("Escolha o arquivo .txt ou .csv", type=["txt", "csv"])
        delimitador = st.selectbox("Delimitador", [";", ",", "\\t"])

        if arquivo is not None:
            delimitador_real = {";": ";", ",": ",", "\\t": "\t"}[delimitador]
            try:
                df_import = pd.read_csv(arquivo, delimiter=delimitador_real)
                # Renomeia colunas para o formato esperado pelo sistema
                df_import.columns = [col.strip().lower().replace("colaborador", "funcionario").replace("qtd", "quantidade") for col in df_import.columns]
                df_import.rename(columns={
                    "data": "data",
                    "tipo": "tipo",
                    "funcionario": "funcionario",
                    "produto": "produto",
                    "quantidade": "quantidade"
                }, inplace=True)
                st.dataframe(df_import)
                if st.button("Importar para o Sistema"):
                    erros = []
                    for _, row in df_import.iterrows():
                        try:
                            produto = str(row['produto'])
                            tipo = str(row['tipo'])
                            data = str(row['data'])
                            funcionario = str(row['funcionario'])
                            quantidade = int(row['quantidade'])

                            c.execute("SELECT * FROM cadastro WHERE nome = ?", (funcionario,))
                            if c.fetchone() is None:
                                erros.append(f"Funcionário '{funcionario}' não cadastrado.")
                                continue

                            c.execute("INSERT INTO movimentacao (data, tipo, funcionario, produto, quantidade) VALUES (?, ?, ?, ?, ?)",
                                      (data, tipo, funcionario, produto, quantidade))
                            c.execute("INSERT OR IGNORE INTO produtos (produto) VALUES (?)", (produto,))
                        except Exception as erro:
                            erros.append(f"Erro na linha: {row.to_dict()} - Erro: {erro}")
                    conn.commit()
                    if erros:
                        st.error("Algumas linhas não foram importadas:")
                        for e in erros:
                            st.error(e)
                    else:
                        st.success("Importação concluída com sucesso!")
            except Exception as e:
                st.error(f"Erro ao ler o arquivo: {e}")
