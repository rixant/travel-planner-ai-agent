from tools.tavily_tool import get_tavily_results
from tools.flight_tool import search_flights

# res = get_tavily_results("Best hotels in Raleigh")
res = search_flights("Plan a 7 days Nepal trip from USA")
print(res)