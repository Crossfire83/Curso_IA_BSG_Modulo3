"""
MCP del agente de e-commerce
----------------------------
Publica una tool de alto nivel: resolver_consulta_ecommerce.

La tool contiene la composición:
Cliente MCP -> agente LangChain -> tools del MCP de datos -> SQLite.

Modos:
  python mcp_agente.py
      inicia por STDIO: recomendado para Claude Desktop.

  MCP_AGENT_TRANSPORT=http python mcp_agente.py
      inicia HTTP en http://127.0.0.1:8001/mcp: recomendado para Streamlit.
"""
from __future__ import annotations
import os
from dotenv import load_dotenv
from fastmcp import FastMCP, Context
from agent_core import resolver_consulta

load_dotenv(override=True)

mcp = FastMCP(
    name="Finance Analyst Agent MCP",
    instructions=(
        "Este servidor expone un agente analista de finanzas personales. "
        "Puede consultar transacciones de clientes, categorias y analiticas."
    ),
)

@mcp.tool()
async def resolver_consulta_financiera(
    mensaje: str,
    ctx: Context,
    session_id: str = "claude-desktop-demo",
    canal: str = "claude-desktop",
) -> dict:
    """
    Resuelve una consulta de finanzas usando un agente LangChain con herramientas MCP.

    Usa session_id estable para conservar la memoria de corto plazo entre turnos.
    Ejemplo de secuencia:
    1. "Dame mis transacciones de este mes."
    2. "Analiza cuales fueron mis categorias con mas gastos."
    """
    return await resolver_consulta(mensaje, session_id=session_id, canal=canal, ctx=ctx)

if __name__ == "__main__":
    transport = os.getenv("MCP_AGENT_TRANSPORT", "http").lower()
    if transport == "http":
        mcp.run(transport="http", host="127.0.0.1", port=8001)
    else:
        mcp.run()
