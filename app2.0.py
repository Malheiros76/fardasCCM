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

# --- Configurar MongoDB ---
client = MongoClient("mongodb+srv://bibliotecaluizcarlos:terra166@cluster0.uyvqnek.mongodb.net/?retryWrites=true&w=majority")
db = client["fardasDB"]

usuarios_col = db["usuarios"]
cadastro_col = db["cadastro"]
produtos_col = db["produtos"]
movimentacao_col = db["movimentacao"]
alunos_col = db["alunos"]

# --- Funções Auxiliares ---
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
            server.login('bibliotecaluizcarlos@gmail.com', 'terra166')  # Altere para senha de app se necessário
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
            "saldo": saldo,
        })
    return pd.DataFrame(lista)

# --- Interface ---
st.set_page_config(page_title="Sistema de Fardas", layout="centered")
st.title("Controle de Fardas")

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
            "Importar Alunos"
        ]
    )

    # ------------------------------
    # NOVA ABA: ALUNOS
    # ------------------------------
    if menu == "Alunos":
        st.subheader("Controle de Entrega para Alunos")

        # Lista de alunos cadastrados
        alunos = list(alunos_col.find())
        nomes = [a["nome"] for a in alunos]

        aluno_selecionado = st.selectbox("Selecione o aluno", nomes)

        if aluno_selecionado:
            aluno = alunos_col.find_one({"nome": aluno_selecionado})
            st.write(f"**CGM:** {aluno['cgm']}")
            st.write(f"**Turma:** {aluno['turma']}")

            st.write("---")
            st.write("### Entrega de Peças:")

            pecas = list(produtos_col.find())
            quantidades = {}

            cols = st.columns(len(pecas))
            for i, peca in enumerate(pecas):
                with cols[i]:
                    # Se tiver campo imagem_url no produto, mostre a imagem
                    if "imagem_url" in peca:
                        st.image(peca["imagem_url"], width=100)
                    st.write(peca["produto"])
                    quantidades[peca["produto"]] = st.number_input(
                        f"Qtd {peca['produto']}",
                        min_value=0,
                        step=1,
                        key=f"qtd_{peca['produto']}"
                    )

            if st.button("Salvar entrega"):
                for produto, qtd in quantidades.items():
                    if qtd > 0:
                        movimentacao_col.insert_one({
                            "data": datetime.now().strftime("%Y-%m-%d"),
                            "tipo": "Saída",
                            "funcionario": aluno_selecionado,
                            "produto": produto,
                            "quantidade": qtd
                        })
                        produtos_col.update_one({"produto": produto}, {"$set": {"produto": produto}}, upsert=True)
                st.success("Entrega registrada!")

            st.write("---")
            st.write("### Histórico de peças entregues ao aluno:")

            historico = list(movimentacao_col.find({
                "funcionario": aluno_selecionado,
                "tipo": "Saída"
            }))

            if historico:
                df_hist = pd.DataFrame(historico)
                st.dataframe(df_hist[["data", "produto", "quantidade"]])

                st.write("### Devolver peça ao estoque")
                for i, row in df_hist.iterrows():
                    if st.button(f"Devolver {row['produto']} ({row['quantidade']})", key=f"devolver_{i}"):
                        movimentacao_col.insert_one({
                            "data": datetime.now().strftime("%Y-%m-%d"),
                            "tipo": "Entrada",
                            "funcionario": aluno_selecionado,
                            "produto": row["produto"],
                            "quantidade": row["quantidade"]
                        })
                        st.success(f"Peça {row['produto']} devolvida ao estoque.")
            else:
                st.info("Nenhuma peça registrada para este aluno.")

    # ------------------------------
    # NOVA ABA: IMPORTAR ALUNOS
    # ------------------------------
    elif menu == "Importar Alunos":
        st.subheader("Importação de Alunos via Arquivo")

        arquivo = st.file_uploader("Escolha o arquivo .txt ou .csv", type=["txt", "csv"])
        delimitador = st.selectbox("Delimitador", [";", ",", "\\t"])

        if arquivo is not None:
            delimitador_real = {";": ";", ",": ",", "\\t": "\t"}[delimitador]
            try:
                df_import = pd.read_csv(arquivo, delimiter=delimitador_real)
                st.dataframe(df_import)
                if st.button("Importar alunos"):
                    erros = []
                    for _, row in df_import.iterrows():
                        try:
                            alunos_col.insert_one({
                                "cgm": str(row["cgm"]),
                                "nome": str(row["nome"]),
                                "turma": str(row["turma"]),
                                "telefone": str(row.get("telefone", ""))
                            })
                        except Exception as e:
                            erros.append(f"Erro na linha {row.to_dict()}: {e}")
                    if erros:
                        st.error("Erros durante a importação:")
                        for erro in erros:
                            st.error(erro)
                    else:
                        st.success("Importação concluída com sucesso!")
            except Exception as e:
                st.error(f"Erro ao processar arquivo: {e}")

    # ---- ABA EXISTENTES DO SISTEMA
    elif menu == "Cadastro Geral":
        # (mantém igual ao seu código)
        st.subheader("Cadastro de Funcionários")
        with st.form("cadastro"):
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
                    st.success("Cadastrado com sucesso!")
                else:
                    st.error("Todos os campos são obrigatórios")

    elif menu == "Movimentação":
        # (mantém igual ao seu código original)

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
                if data and tipo and funcionario and produto and quantidade:
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
                    st.error("Todos os campos são obrigatórios")

    elif menu == "Estoque":
        st.subheader("Estoque Atual")
        df = calcular_estoque()
        if not df.empty:
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
        else:
            st.info("Nenhum dado de movimentação encontrado.")

    elif menu == "Relatórios":
        st.subheader("Relatórios")
        opcao = st.selectbox("Tipo de Relatório", ["Por Quantidade", "Por Local", "Por Funcionário"])
        df = calcular_estoque()
        if df.empty:
            st.info("Nenhum dado para gerar relatório.")
        else:
            def situacao(row):
                limite = row['entrada'] * 0.2
                if row['saldo'] <= 0:
                    return '🔴 Crítico'
                elif row['saldo'] < limite:
                    return '🟡 Atenção'
                else:
                    return '🟢 OK'
            df['situação'] = df.apply(situacao, axis=1)
            filtro_produto = st.multiselect("Filtrar por produto", options=df['produto'].tolist())
            filtro_situacao = st.multiselect("Filtrar por situação", options=df['situação'].unique().tolist())
            if filtro_produto:
                df = df[df['produto'].isin(filtro_produto)]
            if filtro_situacao:
                df = df[df['situação'].isin(filtro_situacao)]
            st.bar_chart(df.set_index("produto")["saldo"])
            st.dataframe(df)
            if st.button("Gerar PDF"):
                nome_pdf = f"relatorio_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
                cpdf = canvas.Canvas(nome_pdf, pagesize=A4)
                cpdf.setFont("Helvetica-Bold", 16)
                cpdf.drawString(2*cm, 28*cm, "Relatório de Estoque de Fardas")
                cpdf.setFont("Helvetica", 12)
                y = 26*cm
                for i, row in df.iterrows():
                    texto = f"{row['produto']} - Entrada: {row['entrada']} - Saída: {row['saida']} - Saldo: {row['saldo']} - Situação: {row['situação']}"
                    cpdf.drawString(2*cm, y, texto)
                    y -= 0.6*cm
                    if y < 2*cm:
                        cpdf.showPage()
                        y = 28*cm
                cpdf.drawString(2*cm, 2.5*cm, "Assinatura do responsável: __________________________")
                cpdf.drawRightString(19*cm, 2.5*cm, datetime.now().strftime("Gerado em: %d/%m/%Y"))
                cpdf.save()
                with open(nome_pdf, "rb") as f:
                    st.download_button("Baixar Relatório", f, file_name=nome_pdf)

    elif menu == "Importar Estoque":
        st.subheader("Importar Estoque via Arquivo .TXT ou .CSV")
        arquivo = st.file_uploader("Escolha o arquivo .txt ou .csv", type=["txt", "csv"])
        delimitador = st.selectbox("Delimitador", [";", ",", "\\t"])
        if arquivo is not None:
            delimitador_real = {";": ";", ",": ",", "\\t": "\t"}[delimitador]
            try:
                df_import = pd.read_csv(arquivo, delimiter=delimitador_real)
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
                            if cadastro_col.find_one({"nome": funcionario}) is None:
                                erros.append(f"Funcionário '{funcionario}' não cadastrado.")
                                continue
                            movimentacao_col.insert_one({
                                "data": data,
                                "tipo": tipo,
                                "funcionario": funcionario,
                                "produto": produto,
                                "quantidade": quantidade
                            })
                            produtos_col.update_one({"produto": produto}, {"$set": {"produto": produto}}, upsert=True)
                        except Exception as erro:
                            erros.append(f"Erro na linha: {row.to_dict()} - Erro: {erro}")
                    if erros:
                        st.error("Algumas linhas não foram importadas:")
                        for e in erros:
                            st.error(e)
                    else:
                        st.success("Importação concluída com sucesso!")
            except Exception as e:
                st.error(f"Erro ao ler o arquivo: {e}")

