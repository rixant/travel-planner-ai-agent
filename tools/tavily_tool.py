from tavily import TavilyClient
import os
from dotenv import load_dotenv

load_dotenv()

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

def search_tavily(query):
    response = tavily_client.search(query = query, max_results = 5)
    return response["results"]

def get_tavily_results(query):
    response = search_tavily(query)

    results = []

    for i, res  in enumerate(response, 1):
        title = res.get("title", "Unknow")
        url = res.get("url", "")
        snippet = res.get("content", "").strip()
        
        if len(snippet) > 300:
            snippet = snippet[:300].rsplit(" ", 1)[0] + "..."

        results.append(f"{i}. **{title}**\n {url}\n {snippet}")

    return "\n\n".join(results)
