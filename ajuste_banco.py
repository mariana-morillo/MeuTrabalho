import streamlit as st
from sqlalchemy import text

# Conecta no seu Supabase
conn_central = st.connection("supabase", type="sql").engine.connect()

try:
    # Executa o comando de alteração no Postgres
    with conn_central:
        conn_central.execute(text("ALTER TABLE questoes ADD COLUMN uso_quest TEXT DEFAULT 'Prova Oficial';"))
        conn_central.commit()
    print("✅ Coluna 'uso_quest' adicionada com sucesso no Supabase!")
except Exception as e:
    print(f"⚠️ A coluna já existe ou houve um erro: {e}")
