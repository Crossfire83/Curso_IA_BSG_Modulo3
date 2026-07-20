# Curso_IA_BSG_Modulo3
MCP Agent with LangChain and Streamlit.

## Arquitectura Objetivo

|Capa|Responsabilidad|Tecnología utilizada|
| --- | --- | --- |
|Interfaz|Recibir preguntas, mostrar respuestas, evidencia y estado de la sesión|Streamlit|
|Agente|Interpretar la intención, elegir y utilizar tools, coordinar respuestas y gestionar memoria.|LangChain + AWS Bedrock|
|MCP de dominio|Exponer tools personalizadas con contratos claros.|FastMCP|
|Datos o API's|Entregar Informacion y ejecutar operaciones controladas.|API Propia|
|Despliegue|Publicar la interfaz y mantener disponible el MCP remoto.|Streamlit Community Cloud + servicio HTTP externo|

## Enunciado de la tarea

Desarrolla un sistema de agentes orientado a un caso de uso concreto. El sistema debe consultar un
servidor MCP personalizado, usar LangChain como capa de orquestacion, utilizar AWS Bedrock como modelo de
lenguaje base y ofrecer una interfaz Streamlit desplegada publicamente.

## Problema a resolver

Ofrecer una interfaz de chat para el usuario que comprenda, analice e interprete las transacciones financieras ademas de poder manipular (agregar, modificar, eliminar) transacciones dentro del sistema de informacion que sea amigable.

## Definicion de caso

|Campo|Valor|
| --- | --- |
|Nombre del sistema|Monett.ia|
|Usuario principal|Suscriptores (usuarios premium) de la plataforma|
|Problema que resuelve|Ofrecer orientacion y una interfaz adicional para interactuar con el sistema.|
|Pregunta o tarea tipica|¿Qué recomendación me puedes dar de mis gastos de este mes respecto del pasado?|
|Fuentes de datos o APIs|APIs de Monettia|
|Decision o resultado que entrega|Análisis y/o manipulación de informacion de transacciones de usuario.|
|Riesgos y limites|Consumo excesivo de tokens.|
|Tools MCP propuestas|`obtener_transacciones`, `obtener_categorias`, `obtener_fecha_actual`, `obtener_analitica_categorias`|

## Contratos de MCP Tools Personalizadas

<details open>
<summary>Obtener Transacciones</summary>

|Componente|Valor|
| --- | --- |
|Nombre|`obtener_transacciones`|
|Descripcion|Obtiene las transacciones de un usuario que ocurrieron en un periodo determinado o desde que el usuario utiliza la plataforma|
|Parametros|- user_id : str (bearer token)<br>- from_date : str (opcional)<br>- to_date : str (opcional)|
|Validacion|- usuario existe, con registro en plataforma<br>- parametros de fecha formateados correctamente (yyyy-MM-dd)|
|Salida|Lista de categorias con su respectiva lista de transacciones|
|Riesgo|Lectura de informacion financiera sensible|
</details>

<details open>
<summary>Obtener Categorías</summary>

|Componente|Valor|
| --- | --- |
|Nombre|`obtener_categorias`|
|Descripcion|Obtiene la informacion de las categorias que un usuario tiene registradas en la plataforma|
|Parametros|- user_id : str (bearer token)|
|Validacion|- usuario existe, con registro en plataforma|
|Salida|Lista de categorias|
|Riesgo|Bajo riesgo, no hay informacion financiera presente (montos)|
</details>

<details open>
<summary>Obtener Fecha Actual</summary>

|Componente|Valor|
| --- | --- |
|Nombre|`obtener_fecha_actual`|
|Descripcion|Obtiene la fecha actual para darle contexto temporal al agente y que sepa en que fecha está operando|
|Parametros|N/A|
|Validacion|N/A|
|Salida|fecha formateada en yyyy-MM-dd|
|Riesgo|Bajo Riesgo|
</details>

<details open>
<summary>Obtener Analíticas de Categorías</summary>

|Componente|Valor|
| --- | --- |
|Nombre|`obtener_analitica_categorias`|
|Descripcion|Obtiene las categorías de un usuario con sus analíticas de totales y porcentuales de gastos e ingresos|
|Parametros|- user_id : str (bearer token)<br>- from_date : str (opcional)<br>- to_date : str (opcional)|
|Validacion|- usuario existe, con registro en plataforma<br>- parametros de fecha formateados correctamente (yyyy-MM-dd)|
|Salida|Lista de categorias con sus detalles de analíticas|
|Riesgo|Lectura de informacion financiera sensible|
</details>

<details open>
<summary>Matríz de MCP Tools</summary>

|Tool|Necesidad que resuelve|Entrada|Salida|Riesgo|Prueba|
| --- | --- | --- | --- | --- | --- |
|`obtener_analitica_categorias`|Obtiene las categorías de un usuario con sus analíticas de totales y porcentuales de gastos e ingresos|- user_id : str (bearer token)<br>- from_date : str (opcional)<br>- to_date : str (opcional)|Lista de categorias con sus detalles de analíticas|Lectura de informacion financiera sensible|Dame la categoria en la cual gaste mas en el mes de febrero|
|`obtener_transacciones`|Obtiene las transacciones de un usuario que ocurrieron en un periodo determinado o desde que el usuario utiliza la plataforma|- user_id : str (bearer token)<br>- from_date : str (opcional)<br>- to_date : str (opcional)|Lista de categorias con su respectiva lista de transacciones|Lectura de informacion financiera sensible|Dame mis gastos de este mes|
|`obtener_categorias`|Obtiene la informacion de las categorias que un usuario tiene registradas en la plataforma|- user_id : str (bearer token)|Lista de categorias|Bajo riesgo, no hay informacion financiera presente (montos)|Me puedes decir mis categorias disponibles?|
|`obtener_fecha_actual`|Obtiene la fecha actual para darle contexto temporal al agente y que sepa en que fecha está operando|N/A|fecha formateada en yyyy-MM-dd|Bajo Riesgo|En que fecha estamos?|
</details>

## Arquitectura

``` mermaid
---
config:
  layout: elk
---
graph TB
    StreamlitApp[Streamlit App]:::interfaceLayer
    LangchainClient[Langchain Client]:::coreLayer
    MCPServer[MCP Server]:::coreLayer
    MCPTool[MCP Tool: Financial API]:::toolLayer
    AnalyticsAPI[Financial API Service]:::apiLayer
    LLMModel[LLM Model Provider]:::modelLayer

    User -->|Interact| StreamlitApp
    StreamlitApp -->|Send Chat Input| LangchainClient
    
    LangchainClient -->|Route Requests| MCPServer
    LangchainClient -->|Query| LLMModel

    MCPServer -->|Invoke| MCPTool
    
    MCPTool -->|Call| AnalyticsAPI
    MCPTool -->|Return Result| MCPServer
    
    AnalyticsAPI -->|Return Data| MCPTool

    MCPServer -->|Tool Results| LangchainClient
    LangchainClient -->|Format Response| StreamlitApp
```