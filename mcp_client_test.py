from concurrent.futures import ThreadPoolExecutor
import os
import sys
import asyncio
import certifi
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
AVIATIONSTACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")


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
            # "command": r"Users\rixant\opt\anaconda3\bin\python.exe",
            # "args": [
            #     r"\Users\rixant\AI Repos\travel-planner-agent\mcp_client.py"
            # ],
             "command": sys.executable,
    "args": ["weather_server.py"],
            "env": {
                "OPENWEATHER_API_KEY": WEATHER_API_KEY
            }
        }})



async def get_all_tools():
    tools = await client.get_tools()

    for tool in tools:
        print(tool.name)


get_all_tools()
