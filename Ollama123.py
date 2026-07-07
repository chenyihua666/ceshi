import ollama
res= ollama.generate(
    model="qwen2.5:7b",
    prompt="你好，我是小明，我爱吃排骨，请给我编一个200以内的小故事"
)
print(res.thinking)
print(res.response)

















