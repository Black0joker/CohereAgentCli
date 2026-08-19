import cohere

co = cohere.ClientV2(api_key="cohere_Ow562InNFHixUFzFyYmfeXNGQmcy8RsIoUSTmQzu3KVRvy")

res = co.chat_stream(
    model="command-a-plus-05-2026",
    messages=[{"role": "user", "content": "What is an LLM?"}],
)

for event in res:
    print(event)