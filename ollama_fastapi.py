from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel
import ollama
from fastapi.responses import StreamingResponse
import json

# ========== 配置 ==========
MODEL = "qwen2.5:0.5b"
app = FastAPI(title="本地 AI 助手")

# ========== 定义请求格式 ==========
class ChatRequest(BaseModel):
    message: str                               # 用户消息（必填）
    system_prompt: str = "你是一个有用的助手"     # 系统提示词（可选，有默认值）
    stream: bool = False                       # 是否流式返回（可选，有默认值）

class ChatResponse(BaseModel):
    answer: Optional[str] = None                              # AI 回答

# ========== API 接口 ==========
@app.get("/")
def health():
    """健康检查——确认服务正常运行"""
    return {"status": "ok", "model": MODEL}

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    接收用户消息，调用本地模型，返回回答
    """


    if req.stream:
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": req.system_prompt},
                {"role": "user", "content": req.message},
            ],
            stream=req.stream
        )
        # 定义一个生成器，逐步读取 ollama 的流式响应并 yield 给客户端
        def generate():
            for chunk in response:
                # ollama 流式返回的每个 chunk 格式类似 {"message": {"content": "..."}}
                content = chunk.get("message", {}).get("content", "")
                if content:
                    # 使用 SSE (Server-Sent Events) 格式返回，方便前端解析
                    yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
            # 发送结束标志
            yield "data: [DONE]\n\n"


        return StreamingResponse(generate(), media_type="text/event-stream")
    else:
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": req.system_prompt},
                {"role": "user", "content": req.message},
            ],
            stream=req.stream
        )
        return ChatResponse(answer=response["message"]["content"])

# ========== 启动服务 ==========
if __name__ == "__main__":
    import uvicorn
    print(f"🚀 服务启动中... 模型: {MODEL}")
    print(f"📖 健康检查: http://localhost:8000")
    print(f"💬 发送消息: POST http://localhost:8000/chat")
    print(f"📝 测试命令: curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{{\"message\": \"你好\"}}'")
    uvicorn.run(app, host="0.0.0.0", port=8511)