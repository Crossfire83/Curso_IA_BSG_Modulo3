"""MCP de datos e-commerce basado en el dataset real del proyecto.

Cada tool expone una capacidad analítica de negocio y manda llamar una API
parametrizada y de solo lectura. El LLM no genera Datos en sistema.

Inicio local:
    python mcp_datos.py

Endpoint MCP:
    http://127.0.0.1:8000/mcp
"""
from __future__ import annotations

import json
import os
import requests
import re
from fastmcp import FastMCP, Context
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

mcp = FastMCP(
    name="Finance Analytics Data MCP",
    instructions=(
        "Servidor MCP de analítica de finanzas personales de solo lectura. Usa herramientas "
        "específicas para analizar transacciones, categorias y analiticas."
    ),
)

API_BASE_URL = os.environ.get("API_BASE_URL", "").rstrip("/")
API_TIMEOUT = int(os.environ.get("API_TIMEOUT", "15"))
API_TRANSACTIONS_PATH = os.environ.get(
    "API_TRANSACTIONS_PATH",
    "Transactions",
)
API_CATEGORIES_PATH = os.environ.get(
    "API_CATEGORIES_PATH",
    "Categories",
)
API_CATEGORY_ANALYTICS_PATH = os.environ.get(
    "API_CATEGORY_ANALYTICS_PATH",
    "Categories/Analytics",
)
def is_valid_date(date_string: str) -> bool:
    VALID_DATE_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
    # 1. Quick regex structure check
    if not VALID_DATE_REGEX.match(date_string):
        return False

    # 2. Strict calendar logic check
    try:
        datetime.strptime(date_string, "%Y-%m-%d")
        return True
    except ValueError:
        return False

# -----------------------------------------------------------------------------
# CONECTOR API REST: helper interno, no es una tool MCP.
# -----------------------------------------------------------------------------
def llamar_api(
        metodo_http: str, 
        ruta: str,
        ctx: Context,
        parametros: dict | None = None,
        cuerpo_peticion: dict | None = None,
        ) -> dict:
    """
    Llama una ruta GET previamente definida por el desarrollador.
    El LLM no controla URL base, headers ni token.
    """
    headers = {
        "Accept": "application/json",
    }
    # si no hay authorization header, el usuario no esta autenticado.
    received_headers = ctx.request_context.request.headers
    auth_header = received_headers.get("Authorization")
    if auth_header:
        headers["Authorization"] = f"{auth_header}"


    try:
        response = requests.request(
            method=metodo_http,
            url=f"{API_BASE_URL}/{ruta.lstrip('/')}",
            params=parametros or {},
            headers=headers,
            timeout=API_TIMEOUT,
            json=cuerpo_peticion if metodo_http in ("POST", "PUT", "PATCH") else None,
        )
        response.raise_for_status()
        return response.json()
    except requests.Timeout:
        return {"error": "La API excedio el tiempo maximo de espera."}
    except requests.HTTPError as exc:
        return {
            "error": "La API respondio con error HTTP.",
            "status_code": exc.response.status_code if exc.response is not None else None,
            "detail": str(exc),
        }
    except requests.RequestException as exc:
        return {"error": "No fue posible conectar con la API.", "detail": str(exc)}


@mcp.tool()
def obtener_transacciones(
        ctx: Context,
        from_date: str | None = None, 
        to_date: str | None = None
    ) -> str:
    """
    Consulta las transacciones del usuario autenticado con filtrado opcional por fecha.

    Preguntas que resuelve:
        - "Dime las transacciones de este ultimo mes"
        - "Cual fue mi transaccion o gasto mas caro de esta semana?"
        - "Cual fue mi gasto mas frecuente de este mes?"
        - "Cuales fueron mis transacciones de este año?"
        - "Cuales fueron mis ingresos de este mes?"

    Args:
        from_date: fecha de inicio de periodo en formato yyyy-MM-dd (opcional).
        to_date: fecha de fin de periodo en formato yyyy-MM-dd (opcional).

    Seguridad:
        - El endpoint es fijo y controlado por el desarrollador.
        - La API key no se expone al modelo.
        - Normaliza la respuesta antes de entregarla al LLM.
    """
    ruta = API_TRANSACTIONS_PATH

    body = {}
    if from_date:
        if is_valid_date(from_date):
            body["fromDate"] = from_date
        else:
            raise ValueError("Fecha inválida en from_date.")
    if to_date:
        if is_valid_date(to_date):
            body["toDate"] = to_date
        else:
            raise ValueError("Fecha inválida en to_date.")

    respuesta = llamar_api(
        metodo_http="POST",
        ruta=ruta,
        cuerpo_peticion=body,
        ctx=ctx,
    )

    return json.dumps(respuesta, ensure_ascii=False)


@mcp.tool()
def obtener_categorias(ctx: Context) -> str:
    """
    Consulta las categorias disponibles para un usuario.

    Preguntas que resuelve:
        - "Cuales son mis categorias?"

    Seguridad:
        - El endpoint es fijo y controlado por el desarrollador.
        - La API key no se expone al modelo.
        - Normaliza la respuesta antes de entregarla al LLM.
    """
    ruta = API_CATEGORIES_PATH

    respuesta = llamar_api(
        metodo_http="GET",
        ruta=ruta,
        ctx=ctx,
    )

    return json.dumps(respuesta, ensure_ascii=False)


@mcp.tool()
def obtener_analitica_categorias(
        ctx: Context,
        from_date: str | None = None, 
        to_date: str | None = None
    ) -> str:
    """
    Consulta las categorias disponibles para un usuario.

    Preguntas que resuelve:
        - "Cual fue mi categoria de mayor gasto?"
        - "Cuales son mis categorias de mayor gasto?"
        - "Cual fue mi categoria de mayor ingreso?"

    Args:
        from_date: fecha de inicio de periodo en formato yyyy-MM-dd (opcional).
        to_date: fecha de fin de periodo en formato yyyy-MM-dd (opcional).

    Seguridad:
        - El endpoint es fijo y controlado por el desarrollador.
        - La API key no se expone al modelo.
        - Normaliza la respuesta antes de entregarla al LLM.
    """
    ruta = API_CATEGORY_ANALYTICS_PATH

    query_params = {}
    if from_date:
        if is_valid_date(from_date):
            query_params["fromDate"] = from_date
        else:
            raise ValueError("Fecha inválida en from_date.")
    if to_date:
        if is_valid_date(to_date):
            query_params["toDate"] = to_date
        else:
            raise ValueError("Fecha inválida en to_date.")

    respuesta = llamar_api(
        metodo_http="GET",
        ruta=ruta,
        parametros=query_params,
        ctx=ctx,
    )

    return json.dumps(respuesta, ensure_ascii=False)


@mcp.tool()
def obtener_fecha_actual() -> str:
    """
    Obtiene la fecha actual del sistema en formato yyyy-MM-dd

    Pregunta que resuelve:
    - "Dame la fecha actual"

    """
    from datetime import date

    today = date.today()
    print(today) 
    return json.dumps({"fecha_actual": str(today)})



if __name__ == "__main__":
    PORT = int(os.getenv("PORT_DATOS", "8000"))
    mcp.run(transport="http", host="0.0.0.0", port=PORT, stateless_http=True)
