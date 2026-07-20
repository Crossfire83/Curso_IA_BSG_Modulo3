"""
Núcleo reutilizable del agente.

Este módulo contiene el avance de Clase 3:
- agente LangChain;
- tools descubiertas desde mcp_datos.py;
- memoria de corto plazo por conversación;
- ventana de mensajes para limitar el contexto;
- trazabilidad de llamadas a tools.

No contiene Streamlit ni configuración de Claude Desktop. Eso permite reutilizar
la misma lógica desde diferentes clientes.
"""
from __future__ import annotations
import os
from collections.abc import Iterable
from dotenv import load_dotenv
from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import before_model
from langchain.messages import AIMessage, ToolMessage, RemoveMessage
from langchain_aws import ChatBedrock
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.runtime import Runtime
from fastmcp import Context

load_dotenv(override=True)

MODEL_NAME = os.getenv("AWS_BEDROCK_MODEL", "us.anthropic.claude-sonnet-5")
DATA_MCP_URL = os.getenv("DATA_MCP_URL", "http://127.0.0.1:8000/mcp")
WINDOW_MESSAGES = int(os.getenv("MEMORY_WINDOW_MESSAGES", "8"))

SYSTEM_PROMPT = """
Eres un analista de finanzas personales y respondes en español claro.

REGLAS:
1. Para toda afirmación factual sobre transacciones de clientes o categorias, usa las tools MCP antes de responder.
2. Nunca inventes cifras, conceptos, fechas, categorias ni resultados.
3. Si el usuario no especifica el periodo de tiempo, revisa la conversación reciente y reutiliza el tiempo especificado previamente: esa es la razón de usar memoria de corto plazo.
4. Si no tienes un periodo de fecha que puedas utilizar, usa obtener_fecha_actual y define el periodo de tiempo de este mes (a partir de hoy, menos 30 dias hacia atrás, incluyendo hoy).
5. Si el usuario te pide un reporte, genera un markdown con título, tabla de contenido, secciones y gráficos.
6. Las tools son de solo lectura: nunca digas que modificaste la informacion.
7. Estructura las respuestas de análisis con Hallazgos, Evidencia y Recomendación.
8. Sé transparente: cuando los datos sean insuficientes, indícalo.
"""

# Persistencia EN MEMORIA DEL PROCESO: sirve para una clase y un prototipo local.
# Al reiniciar el proceso, las conversaciones se pierden.
CHECKPOINTER = InMemorySaver()

@before_model
def ventana_contexto(state: AgentState, runtime: Runtime):
    """
    Equivalente moderno a una 'ConversationBufferWindowMemory':
    conserva el primer mensaje del estado y los últimos N mensajes.
    Se ejecuta antes de cada llamada al LLM para controlar el contexto enviado.
    """
    messages = state["messages"]
    if len(messages) <= WINDOW_MESSAGES:
        return None

    first_message = messages[0]
    recent_messages = messages[-WINDOW_MESSAGES:]
    # Evita partir una secuencia de tool calls de forma obvia.
    if isinstance(recent_messages[0], ToolMessage) and len(messages) > WINDOW_MESSAGES + 1:
        recent_messages = messages[-(WINDOW_MESSAGES + 1):]

    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            first_message,
            *recent_messages,
        ]
    }

async def construir_agente(ctx: Context):
    """Descubre las tools remotas del MCP de datos y arma el agente LangChain."""
    # si no hay authorization header, el usuario no esta autenticado.
    received_headers = ctx.request_context.request.headers
    auth_header = received_headers.get("Authorization")
    client = MultiServerMCPClient(
        {
            "monettia": {
                "transport": "http", 
                "url": DATA_MCP_URL,
                "headers": { "Authorization": f"{auth_header}"} if auth_header else None,
            }
        }
    )
    tools = await client.get_tools()

    llm = ChatBedrock(
        model_id=MODEL_NAME,
        temperature=0.0,
    )

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=CHECKPOINTER,
        middleware=[ventana_contexto],
    )
    return agent

def _texto_final(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            return str(message.content)
    return "El agente no generó una respuesta final."

def _traza(messages: Iterable) -> list[dict]:
    trace: list[dict] = []
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            for call in message.tool_calls:
                trace.append({
                    "tipo": "tool_call",
                    "tool": call.get("name"),
                    "argumentos": call.get("args", {}),
                })
        if isinstance(message, ToolMessage):
            content = str(message.content)
            trace.append({
                "tipo": "tool_result",
                "tool_call_id": message.tool_call_id,
                "resultado_previo": content[:500] + ("..." if len(content) > 500 else ""),
            })
    return trace

async def resolver_consulta(
    mensaje: str,
    session_id: str,
    ctx: Context,
    canal: str = "web",
) -> dict:
    """
    Ejecuta una interacción completa. thread_id vincula los turnos de una conversación.
    session_id debe ser estable dentro de una misma conversación.
    """
    if not os.getenv("AWS_ACCESS_KEY_ID"):
        raise RuntimeError("Falta AWS_ACCESS_KEY_ID. Cópiala en un archivo .env.")
    if not os.getenv("AWS_SECRET_ACCESS_KEY"):
        raise RuntimeError("Falta AWS_SECRET_ACCESS_KEY. Cópiala en un archivo .env.")
    if not os.getenv("AWS_REGION"):
        raise RuntimeError("Falta AWS_REGION. Cópiala en un archivo .env.")

    agent = await construir_agente(ctx)
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": mensaje}]},
        {"configurable": {"thread_id": session_id, "canal": canal}},
    )

    messages = result["messages"]
    user_visible = [
        {"rol": "usuario" if getattr(m, "type", "") == "human" else "asistente",
         "contenido": str(m.content)[:600]}
        for m in messages
        if getattr(m, "type", "") in {"human", "ai"} and not getattr(m, "tool_calls", None)
    ]

    return {
        "respuesta": _texto_final(messages),
        "session_id": session_id,
        "canal": canal,
        "modelo": MODEL_NAME,
        "memoria": {
            "tipo": "corto_plazo_en_memoria",
            "window_messages": WINDOW_MESSAGES,
            "mensajes_estado": len(messages),
            "nota": "La conversación persiste solo mientras el proceso esté activo.",
        },
        "traza": _traza(messages),
        "historial_visible": user_visible[-WINDOW_MESSAGES:],
    }
