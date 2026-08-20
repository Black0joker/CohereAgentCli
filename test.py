import cohere

co = cohere.ClientV2(base_url="https://sdf123123123.pythonanywhere.com",api_key="cohere_Ow562InNFHixUFzFyYmfeXNGQmcy8RsIoUSTmQzu3KVRvy")
for i in range(30):
    res = co.chat_stream(
        model="command-a-plus-05-2026",
        messages=[{"role": "user", "content": "hi"}],
    )

    for event in res:
        print(event)