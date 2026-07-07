from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
import ollama
import json

# ========== 配置 ==========
MODEL = "qwen2.5:0.5b"
app = FastAPI(title="本地AI助手(支持流式输出)")


# ========== 数据模型 ==========
class ChatRequest(BaseModel):
    message: str  # 用户消息（必填）
    system_prompt: str = "你是一个有用的助手"  # 系统提示词（可选）


# ========== 通用生成器：Ollama 流式迭代器 ==========
def ollama_stream_generator(system_prompt: str, user_msg: str):
    """生成器，逐块返回模型输出文本"""
    stream = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        stream=True  # 开启流式
    )

    # 逐块处理流式响应
    for chunk in stream:
        text = chunk["message"]["content"]
        # 关键修改：每个 data 块都返回一个标准的 JSON 对象
        # 格式: {"type": "content", "data": "当前文本片段"}
        yield f"data: {json.dumps({'type': 'content', 'data': text})}\n\n"

    # 流式结束标记
    # 格式: {"type": "end", "data": null}
    yield f"data: {json.dumps({'type': 'end', 'data': None})}\n\n"


# ========== API 接口 ==========
@app.get("/")
def health():
    """健康检查——确认服务正常运行"""
    return {"status": "ok", "model": MODEL, "stream_api": "/stream/chat"}


@app.post("/chat")
def chat(req: ChatRequest):
    """一次性完整返回回答"""
    response = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": req.system_prompt},
            {"role": "user", "content": req.message},
        ]
    )
    return {"answer": response["message"]["content"]}


# 新增流式接口 (修正版)
@app.post("/stream/chat")
def stream_chat(req: ChatRequest):
    """流式打字输出接口，SSE协议实时返回片段"""
    generator = ollama_stream_generator(req.system_prompt, req.message)
    return StreamingResponse(
        generator,
        media_type="text/event-stream; charset=utf-8",  # ✅ 增加字符集声明
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


# ========== 启动服务 ==========
if __name__ == "__main__":
    import uvicorn

    print(f"🚀 服务启动中... 模型: {MODEL}")
    print(f"📖 健康检查: http://localhost:8000")
    print(f"💬 一次性对话: POST http://localhost:8000/chat")
    print(f"⚡ 流式对话: POST http://localhost:8000/stream/chat")
    print("-" * 60)
    print("流式curl测试命令：")
    print(
        r"""curl -X POST http://localhost:8000/stream/chat -H "Content-Type: application/json" -d '{"message":"简单介绍一下人工智能"}'""")
    uvicorn.run(app, host="127.0.0.1", port=8000)