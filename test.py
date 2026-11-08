from tools.tavily_tool import get_tavily_results
from tools.flight_tool import search_flights
from backend import run_travel_agent

# res = get_tavily_results("Best hotels in Raleigh")
# res = search_flights("Plan a 7 days Nepal trip from USA")

user_input = input("Enter travel request: ")
res = run_travel_agent(
    user_input=user_input,
    thread_id="test_user"
)
print(res)