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
import httpx
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp.shared.exceptions import McpError

load_dotenv(override=True)

st.set_page_config(page_title="Financial Analyst MCP", page_icon="🛒", layout="wide")

AGENT_MCP_URL = os.getenv("AGENT_MCP_URL") or st.secrets.get("AGENT_MCP_URL", "http://127.0.0.1:8001/mcp")
# Base URL of your backend authentication API
API_BASE_URL = os.getenv("API_BASE_URL") or st.secrets.get("API_BASE_URL")

# Reintentos para absorber "cold starts" del servidor MCP remoto (p.ej. Railway
# despertando un servicio dormido). Este tipo de fallo no ocurre en local porque
# los procesos MCP corren siempre activos, pero sí en despliegues con sleep/idle.
MCP_CONNECT_MAX_RETRIES = 3
MCP_CONNECT_AWAIT_BASE_SECONDS = 2

def _is_mcp_transient_error(exc: BaseException) -> bool:
    """
    Detects transient MCP connection/initialization errors that justify a restart
    (e.g. "Session terminated" by 404 during a cold restart
    or timeouts/connection refused while the remote service wakes up).
    The ExceptionGroup from asyncio/anyio are traversed recursively.
    """
    pending = [exc]
    while pending:
        current = pending.pop()
        if isinstance(current, McpError):
            return True
        if isinstance(current, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError)):
            return True
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
    return False

async def get_persistent_mcp_client(headers=None):
    """Initializes the client and stores it in the streamlit's lifecycle"""
    if "mcp_client" not in st.session_state or st.session_state.mcp_client is None:
        client = MultiServerMCPClient(
            {
                "agente": {
                    "transport": "http",
                    "url": AGENT_MCP_URL,
                    "headers": headers,
                    "timeout": 60,
                    "sse_read_timeout": 60,
                }
            }
        )
        # Force a light first call to get the cold start lifted and connect the SSE
        await client.get_tools()
        st.session_state.mcp_client = client
    return st.session_state.mcp_client

async def llamar_agente(mensaje: str) -> dict:
    if st.session_state.auth_token:
        headers = {"Authorization": f"Bearer {st.session_state.auth_token}"}
    else:
        headers = None

    last_error: BaseException | None = None
    for retry in range(1, MCP_CONNECT_MAX_RETRIES + 1):
        try:
            client = get_persistent_mcp_client(headers)
            tools = await client.get_tools()
            tool_by_name = {tool.name: tool for tool in tools}
            tool = tool_by_name["resolver_consulta_financiera"]
            raw_result = await tool.ainvoke({
                "mensaje": mensaje,
                "session_id": st.session_state.session_id,
                "canal": "streamlit",
            })
            break
        except BaseException as exc:
            last_error = exc
            # If the damaged client caused the issue, clean it so the next retry creates a new one.
            st.session_state.mcp_client = None 
            if retry < MCP_CONNECT_MAX_RETRIES and _is_mcp_transient_error(exc):
                await asyncio.sleep(MCP_CONNECT_AWAIT_BASE_SECONDS * retry)
                continue
            raise
    else:
        # Should not be hit: or there was a break, or the error was re-thrown
        raise last_error  # type: ignore[misc]

    # The result of tool.ainvoke() is a Json string; parse it to a dict.
    if isinstance(raw_result, str):
        return json.loads(raw_result)
    if isinstance(raw_result, list):
        # Some adapters return content blocks; we take the text of the first one.
        text = raw_result[0] if isinstance(raw_result[0], str) else raw_result[0].get("text", "{}")
        return json.loads(text)
    return raw_result

# 1. Initialize session state variables
if "auth_token" not in st.session_state:
    st.session_state.auth_token = None
if "user_info" not in st.session_state:
    st.session_state.user_info = None
if "mcp_client" not in st.session_state:
    st.session_state.mcp_client = None

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
                            json=login_data,
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
        st.session_state.mcp_client = None
        st.rerun()

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

    if prompt := st.chat_input("Ej.: Dime mis gastos de este mes."):
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

