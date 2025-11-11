
# streamlit_app_senhas.py — UI Streamlit para o Distribuidor de Senhas
from __future__ import annotations

from typing import List, Dict
import streamlit as st

from event_utils import (
    read_active_areas, submit_ticket, now_str, _sheets_service, _get_spreadsheet_id
)

st.set_page_config(page_title="Distribuidor de Senhas — Evento", page_icon="🎟️", layout="centered")
st.title("🎟️ Distribuidor de Senhas — Evento")

# Ajuda rápida
with st.expander("Como funciona?"):
    st.markdown(
        """
        1. A aba **Nomes** da planilha deve listar todas as áreas, com a coluna **Ativa** marcada para as que devem aparecer aqui.
        2. Escolha a **Área** (apenas as ativas são exibidas), preencha **Nome**, **Telefone** e **Bairro**.
        3. Clique em **Gerar senha e salvar**. O app:
           - grava na aba da área com as colunas `Senha | Nome | Telefone | Bairro | Data e Hora de Registro | Data e Hora de Atendimento` (esta última em branco);
           - cria a **Senha sequencial** da planilha (1, 2, 3, …);
           - gera um **PDF** para impressão imediata.
        """
    )

# Teste de credenciais e carregamento de áreas
areas_opts: List[Dict] = []
try:
    service = _sheets_service()
    sid = _get_spreadsheet_id()
    areas_opts = read_active_areas(service, sid)
except Exception as e:
    st.error(f"⚠️ Não foi possível ler a planilha: {e}")

if not areas_opts:
    st.warning("Nenhuma área ativa encontrada na aba 'Nomes'. Verifique a planilha/credenciais.")
else:
    labels = [a["area"] for a in areas_opts]
    area_sel = st.selectbox("Área / Setor", options=[""] + labels, index=0)
    nome = st.text_input("Nome", max_chars=80)
    telefone = st.text_input("Telefone", max_chars=30, placeholder="(00) 00000-0000")
    bairro = st.text_input("Bairro", max_chars=80)

    btn = st.button("✅ Gerar senha e salvar", type="primary", disabled=(not area_sel or not nome))

    if btn:
        with st.spinner("Gravando na planilha e gerando PDF..."):
            try:
                senha_num, pdf_bytes = submit_ticket(area=area_sel, nome=nome, telefone=telefone, bairro=bairro)
                st.success(f"Senha **{senha_num}** gerada para a área **{area_sel}** às {now_str()}.")
                st.download_button(
                    "⬇️ Baixar PDF da senha",
                    data=pdf_bytes,
                    file_name=f"senha_{area_sel}_{senha_num}.pdf",
                    mime="application/pdf",
                )
            except Exception as e:
                st.error(f"Falha ao gerar senha: {e}")

