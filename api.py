from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from enum import Enum
import json
import boto3
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = boto3.client(
    service_name="bedrock-runtime",
    region_name="us-east-1"
)

MODEL_ID = "arn:aws:bedrock:us-east-1:599917952029:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0"
MAX_LOG_LENGTH = 600

class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"

class AnalyzeRequest(BaseModel):
    log: str

class AnalyzeResponse(BaseModel):
    severity: Severity
    summary: str
    cause: str
    solution: str
    prevention: str

    input_tokens: int
    output_tokens: int
    total_tokens: int
    success: bool
    
@app.get("/")
def root():
    return {"message": "API 起動中"}

@app.get("/config")
def get_config():
    return {
        "max_log_length": MAX_LOG_LENGTH
    }

@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):

    if not request.log.strip():
        raise HTTPException(
            status_code=400,
            detail="ログを入力してください。"
        )
    
    if len(request.log) > MAX_LOG_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"ログが長すぎます。{MAX_LOG_LENGTH} 文字以内にしてください。"
        )

    try:
      response = client.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": f"""
                            以下のエラーログを解析してください。

                            必ずJSONのみを返してください。
                            説明文、Markdown、コードブロックは不要です。

                            以下の形式に完全一致させてください。

                            {{
                            "severity": "低 | 中 | 高",
                            "summary": "エラー概要",
                            "cause": "原因",
                            "solution": "解決方法",
                            "prevention": "再発防止策"
                            }}

                            ログ:
                            {request.log}
                            """
                    }
                ],
            }
        ],
        inferenceConfig={
            "maxTokens": 1000
        }
    )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Bedrock API error: {str(e)}"
        )
    
    import json
    print(json.dumps(response, indent=2, ensure_ascii=False))

    result = response["output"]["message"]["content"][0]["text"]

    if result.startswith("```json"):
        result = result.replace("```json", "").replace("```", "").strip()
    elif result.startswith("```"):
        result = result.replace("```", "").strip()

    print("=== Claude result ===")
    print(result)
    print("=====================")
    
    try:
        parsed_result = json.loads(result)

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Claude response is not valid JSON"
        )
    
    severity_map = {
    "低": "low",
    "中": "medium",
    "高": "high",
    }

    severity = severity_map.get(parsed_result["severity"], parsed_result["severity"])

    return {
    "severity": severity,
    "summary": parsed_result["summary"],
    "cause": parsed_result["cause"],
    "solution": parsed_result["solution"],
    "prevention": parsed_result["prevention"],
    "input_tokens": response["usage"]["inputTokens"],
    "output_tokens": response["usage"]["outputTokens"],
    "total_tokens": response["usage"]["totalTokens"],
    "success": True,
    }