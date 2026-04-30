
from langchain_core.messages import HumanMessage, AIMessage
from agent.agent import agent, config

def main():
    print("Gmail Job Calendar Trakcer initialized.... (Type 'exit', 'bye', 'quit' to quit)")

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if user_input in ['exit', 'quit', 'bye']:
                print("Goodbye!")
                break

            print("\n ", end="", flush=True)

            stream = agent.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
                stream_mode="values"
            )

            for chunk in stream:
                latest_message = chunk["messages"][-1]

                if latest_message.content and isinstance(latest_message, AIMessage):
                        print(f"Agent: {latest_message.content}")

        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        except Exception as e:
            print(f"Error: {e}")

if __name__ == '__main__':
    main()
