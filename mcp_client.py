from concurrent.futures import ThreadPoolExecutor
import os
import asyncio
from unittest import result
import certifi
from custom_weather_mcp_server import WEATHER_API_KEY
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from tools.flight_tool import AVIATIONSTACK_API_KEY
from langchain_groq import ChatGroq

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
AVIATIONSTACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


client = MultiServerMCPClient(
    {
        "tavily": {
            "transport": "streamable_http",
            "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}"
        },
        "Aviationstack MCP": {
            "transport": "stdio",
            "command": "uvx", 
            "args": [
                "aviationstack-mcp"
            ],
            "env": {
                "AVIATIONSTACK_API_KEY": AVIATIONSTACK_API_KEY
            }
        },
        "weather": {
            "transport": "stdio",
            "command": "/Users/rixant/opt/anaconda3/bin/python",
            "args": [
                "/Users/rixant/AI Repos/travel-planner-agent/custom_weather_mcp_server.py"
            ],
            "env": {
                "OPENWEATHER_API_KEY": WEATHER_API_KEY
            }
        }
    }
)

async def get_all_tools():
    tools = await client.get_tools()

    for tool in tools:
        print(tool.name)



search_tool = None
aviation_tools = {} 

async def intialize_mcp():

    global search_tool
    global aviation_tools

    if search_tool is not None and aviation_tools:
        return
    
    tools = await client.get_tools()

    for tool in tools:
        print(tool.name)

    
    search_tool = next(
        tool for tool in tools if tool.name == "tavily_search"
    )

    aviation_tools = {
        tool.name: tool for tool in tools if tool.name != "tavily_search"
    }


async def tavily_mcp_search(query: str):
    await intialize_mcp()
    result = await search_tool.ainvoke(
        {
            "query": query
        }
    )
    return result


async def aviation_mcp_call(
    tool_name: str,
    tool_args: dict = None
):
    tools = await client.get_tools()

    tool = next(t for t in tools if t.name == tool_name)

    result = await tool.ainvoke(
        tool_args or {}
    )

    return result

weather_tool = None
forecast_tool = None

async def intialize_weather_tools():

    global weather_tool, forecast_tool

    if weather_tool is not None:
        return 

    tools = await client.get_tools()

    weather_tool = next(t for t in tools if t.name == "get_current_weather")

    forecast_tool = next(
        t for t in tools
        if t.name == "get_forecast"
    )

async def weather_mcp_search(city):

    await intialize_weather_tools()

    return await weather_tool.ainvoke( {"city": city})


async def forecast_mcp_search(city):

    await initialize_weather_tools()

    return await forecast_tool.ainvoke(
        {
            "city": city
        }
    )


llm = ChatGroq(
    model="openai/gpt-oss-20b",
    api_key=GROQ_API_KEY
)


def extract_destination(query):

    prompt = f"""
    Extract only the destination city of country.os
    Query:
    {query}

    Return only the destination name.
    """

    response = llm.invoke(prompt)

    return response.content.strip()