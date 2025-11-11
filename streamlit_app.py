
# streamlit_app_senhas.py — UI Streamlit para o Distribuidor de Senhas
from __future__ import annotations
from typing import List, Dict
import streamlit as st

from event_utils import (
    read_active_areas,
    read_neighborhoods,
    submit_tickets,
    format_phone_number,
    _sheets_service,
    _get_spreadsheet_id,
)

st.set_page_config(page_title="Distribuidor de Senhas — Evento", page_icon="🎟️", layout="centered")
st.title("🎟️ Distribuidor de Senhas — Evento")

st.caption(f"Planilha conectada: `{_get_spreadsheet_id()}` (definida no código)")

# Ajuda rápida
with st.expander("Como funciona?"):
    st.markdown(
        """
        1. A aba **Nomes** da planilha deve listar todas as áreas, com a coluna **Ativa** marcada para as que devem aparecer aqui.
        2. Escolha **uma ou mais áreas** (apenas as ativas são exibidas), preencha **Nome**, **Telefone** e **Bairro**.
        3. Clique em **Gerar senhas e salvar**. O app:
           - grava em cada aba selecionada com as colunas `Senha | Nome | Telefone | Bairro | Data e Hora de Registro | Data e Hora de Atendimento` (esta última em branco);
           - cria a **Senha sequencial** em cada planilha (1, 2, 3, …);
           - gera um **PDF** com uma página para cada senha.
        """
    )

# Teste de credenciais e carregamento de áreas
areas_opts: List[Dict] = []
bairros_opts: List[str] = []
try:
    service = _sheets_service()
    sid = _get_spreadsheet_id()
    areas_opts = read_active_areas(service, sid)
    bairros_opts = read_neighborhoods(service, sid)
except Exception as e:
    st.error(f"⚠️ Não foi possível ler a planilha: {e}")

if not areas_opts:
    st.warning("Nenhuma área ativa encontrada na aba 'Nomes'. Verifique a planilha/credenciais.")
else:
    labels = [a["area"] for a in areas_opts]
    areas_sel = st.multiselect(
        "Áreas / Setores", options=labels, help="Selecione uma ou mais áreas para registrar."
    )
    nome_input = st.text_input("Nome", max_chars=80)
    nome = nome_input.strip()
    telefone_input = st.text_input("Telefone", max_chars=30, placeholder="92981231234")
    telefone_ok = True
    telefone_msg = ""
    telefone_preview = ""
    if telefone_input.strip():
        try:
            telefone_preview = format_phone_number(telefone_input)
        except ValueError as exc:
            telefone_ok = False
            telefone_msg = str(exc)
    else:
        telefone_ok = False
        telefone_msg = "Informe o telefone com 11 dígitos (incluindo DDD)."

    if telefone_msg:
        st.caption(f"ℹ️ {telefone_msg}")
    elif telefone_preview:
        st.caption(f"Formato final: {telefone_preview}")
    if bairros_opts:
        bairro = st.selectbox("Bairro", options=[""] + bairros_opts, index=0)
    else:
        st.info(
            "Lista de bairros não encontrada na aba 'Bairro'. Informe manualmente abaixo ou verifique a planilha."
        )
        bairro = st.text_input("Bairro", max_chars=80)

    btn = st.button(
        "✅ Gerar senhas e salvar",
        type="primary",
        disabled=(not areas_sel or not nome or not telefone_ok),
    )

    if btn:
        with st.spinner("Gravando na planilha e gerando PDF..."):
            try:
                registros, pdf_bytes, ts_registro = submit_tickets(
                    areas=areas_sel,
                    nome=nome,
                    telefone=telefone_input,
                    bairro=bairro,
                )
                qtd = len(registros)
                senhas_fmt = "\n".join(
                    f"• Área **{reg['area']}** → Senha **{reg['senha']}**" for reg in registros
                )
                titulo = "senhas" if qtd > 1 else "senha"
                verbo = "geradas" if qtd > 1 else "gerada"
                st.success(
                    f"{qtd} {titulo} {verbo} às {ts_registro}.\n\n{senhas_fmt}"
                )
                st.download_button(
                    "⬇️ Baixar PDF das senhas",
                    data=pdf_bytes,
                    file_name=f"senhas_{qtd}_areas.pdf",
                    mime="application/pdf",
                )
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Falha ao gerar senha: {e}")
