"""
Cliente Streamlit del MCP del agente.

Esta aplicación NO contiene el LLM ni las consultas SQL.
Es un cliente que consume mcp_agente.py por HTTP y hace visible:
- el chat;
- la session_id;
- la memoria de corto plazo;
- las herramientas invocadas.
"""
from __future__ import annotations
import asyncio
import json
import os
import traceback
import uuid
import streamlit as st
import requests
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv(override=True)
AGENT_MCP_URL = os.getenv("AGENT_MCP_URL") or st.secrets.get("AGENT_MCP_URL", "http://127.0.0.1:8001/mcp")
# Base URL of your backend authentication API
API_BASE_URL = os.getenv("API_BASE_URL") or st.secrets.get("API_BASE_URL")

async def llamar_agente(mensaje: str) -> dict:
    if st.session_state.auth_token:
        headers = {"Authorization": f"Bearer {st.session_state.auth_token}"}
    else:
        headers = None

    client = MultiServerMCPClient(
        {
            "agente": {
                "transport": "http", 
                "url": AGENT_MCP_URL,
                "headers": headers,
            }
        }
    )
    tools = await client.get_tools()
    tool_by_name = {tool.name: tool for tool in tools}
    tool = tool_by_name["resolver_consulta_financiera"]
    raw_result = await tool.ainvoke({
        "mensaje": mensaje,
        "session_id": st.session_state.session_id,
        "canal": "streamlit",
    })

    # El resultado de tool.ainvoke() es un string JSON; lo parseamos a dict.
    if isinstance(raw_result, str):
        return json.loads(raw_result)
    if isinstance(raw_result, list):
        # Algunos adaptadores devuelven content blocks; tomamos el texto del primero.
        text = raw_result[0] if isinstance(raw_result[0], str) else raw_result[0].get("text", "{}")
        return json.loads(text)
    return raw_result

# 1. Initialize session state variables
if "auth_token" not in st.session_state:
    st.session_state.auth_token = None
if "user_info" not in st.session_state:
    st.session_state.user_info = None

# 2. Render Login Screen if not authenticated
if st.session_state.auth_token is None:
    st.title("Welcome Back")
    st.subheader("Please sign in to access the system")

    with st.form("api_login_form"):
        email = st.text_input("Email", placeholder="user@example.com")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Sign In")

        if submit_button:
            if not email or not password:
                st.error("Please enter both email and password.")
            else:
                # Prepare payload (matches standard OAuth2 / token exchange format)
                login_data = {
                    "email": email,
                    "password": password
                }
                
                try:
                    with st.spinner("Authenticating..."):
                        # Send POST request to your auth endpoint
                        response = requests.post(
                            f"{API_BASE_URL}/User/Login", 
                            json=login_data, # Use data=login_data if your API expects form-encoded fields
                            timeout=50
                        )
                    
                    if response.status_code == 200:
                        # Extract token data assuming API returns {"access_token": "...", "token_type": "bearer"}
                        token_response = response.json()

                        user_info = {
                            "email": email,
                            "token": token_response.get("token"),
                            "first_name": token_response.get("firstName"),
                            "last_name": token_response.get("lastName")
                        }
                        
                        # Save token to state to prevent losing it on user interactions
                        st.session_state.auth_token = token_response.get("token")
                        st.session_state.user_info = user_info
                        st.success("Successfully logged in!")
                        st.rerun() # Refresh app to render the dashboard
                    else:
                        st.error(f"Login failed: Incorrect email or password. {response}")
                        
                except requests.exceptions.RequestException as e:
                    st.error(f"Could not connect to authentication API: {e}")



# 3. Render Main Application if authenticated
else:
    st.sidebar.title(f"Logged in as: {st.session_state.user_info.get('first_name')}")
    
    # Logout feature clears state
    if st.sidebar.button("Log Out"):
        st.session_state.auth_token = None
        st.session_state.user_info = None
        st.rerun()

    st.set_page_config(page_title="Financial Analyst MCP", page_icon="🛒", layout="wide")
    st.title("🛒 Agente asesor financiero: Streamlit como cliente MCP")
    st.caption("La UI consume el MCP del agente; el agente consume el MCP de datos.")
    
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"streamlit-{uuid.uuid4().hex[:10]}"
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_result" not in st.session_state:
        st.session_state.last_result = None

    # 4. Use the saved Bearer token to make secure requests to other API endpoints
    with st.sidebar:
        st.header("Sesión y memoria")
        st.code(st.session_state.session_id)
        st.write("La misma `session_id` mantiene la conversación dentro del proceso del agente.")
        if st.button("Nueva conversación"):
            st.session_state.session_id = f"streamlit-{uuid.uuid4().hex[:10]}"
            st.session_state.messages = []
            st.session_state.last_result = None
            st.rerun()
        st.divider()
        st.write("Servidor esperado:")
        st.code(AGENT_MCP_URL)

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Ej.: Dime mis gastos de este mes.")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("El cliente MCP consulta al agente..."):
                try:
                    result = asyncio.run(llamar_agente(prompt))
                    answer = result["respuesta"]
                    st.markdown(answer)
                    st.session_state.last_result = result
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                except json.JSONDecodeError as exc:
                    st.error(f"El agente respondió con un formato inesperado (no es JSON válido): {exc}")
                    st.code(traceback.format_exc(), language="python")
                except KeyError as exc:
                    st.error(f"La respuesta del agente no contiene el campo esperado: {exc}")
                    st.code(traceback.format_exc(), language="python")
                except requests.exceptions.ConnectionError as exc:
                    st.error("No se pudo conectar al servidor MCP del agente. ¿Está corriendo mcp_agente.py?")
                    st.code(traceback.format_exc(), language="python")
                except requests.exceptions.Timeout as exc:
                    st.error("La solicitud al agente excedió el tiempo de espera.")
                    st.code(traceback.format_exc(), language="python")
                except BaseException as exc:
                    # Unwrap ExceptionGroup / TaskGroup errors to show the real cause
                    real_exc = exc
                    if isinstance(exc, BaseExceptionGroup):
                        sub_exceptions = exc.exceptions
                        if sub_exceptions:
                            real_exc = sub_exceptions[0]
                    st.error(
                        f"Error al consultar el agente: {type(real_exc).__name__}: {real_exc}"
                    )
                    st.code(traceback.format_exc(), language="python")

    if st.session_state.last_result:
        result = st.session_state.last_result
        left, right = st.columns(2)
        with left:
            st.subheader("Memoria de corto plazo")
            st.json(result["memoria"])
            st.caption(
                "Al cambiar la sesión se parte con memoria vacía. "
                "Al reiniciar mcp_agente.py, todas las memorias en RAM se eliminan."
            )
        with right:
            st.subheader("Traza de orquestación")
            st.json(result["traza"])



















