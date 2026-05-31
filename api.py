from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from enum import Enum
from typing import List
from fastapi.middleware.cors import CORSMiddleware
import json
import boto3

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = boto3.client(service_name="bedrock-runtime", region_name="us-east-1")


MODEL_ID = "arn:aws:bedrock:us-east-1:599917952029:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0"
MAX_LOG_LENGTH = 600
KNOWLEDGE_BASE_FILE = "knowledge_base.json"

with open(KNOWLEDGE_BASE_FILE, "r", encoding="utf-8") as f:
    knowledge_base = json.load(f)


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Reference(BaseModel):
    title: str
    matched_keywords: list[str]
    score: int
    match_rate: float


class AnalyzeRequest(BaseModel):
    log: str
    mode: str = "rag"


class AnalyzeResponse(BaseModel):
    mode: str
    severity: Severity
    summary: str
    cause: str
    solution: str
    prevention: str

    input_tokens: int
    output_tokens: int
    total_tokens: int
    success: bool
    references: list[Reference] = []


@app.get("/")
def root():
    return {"message": "API 起動中"}


@app.get("/config")
def get_config():
    return {"max_log_length": MAX_LOG_LENGTH}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):

    if not request.log.strip():
        raise HTTPException(status_code=400, detail="ログを入力してください。")

    if len(request.log) > MAX_LOG_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"ログが長すぎます。{MAX_LOG_LENGTH} 文字以内にしてください。",
        )

    try:
        print("analyze called")
        breakpoint()

        references = []
        reference_info = ""

        if request.mode == "rag":
            reference_info, references = search_knowledge(request.log)
            prompt = f"""
                あなたはエラーログ解析アシスタントです。

                以下の参考ナレッジがある場合は、
                必ず優先して解析に反映してください。

                参考ナレッジ:
                {reference_info}

                解析対象ログ:
                {request.log}

                以下の形式に完全一致させてください。

                    {{
                    "severity": "低 | 中 | 高",
                    "summary": "エラー概要",
                    "cause": "原因",
                    "solution": "解決方法",
                    "prevention": "再発防止策"
                    }}
                """
        else:
            prompt = f"""
                あなたはエラーログ解析アシスタントです。

                以下のログを解析してください。

                解析対象ログ:
                {request.log}

                以下の形式に完全一致させてください。

                    {{
                    "severity": "低 | 中 | 高",
                    "summary": "エラー概要",
                    "cause": "原因",
                    "solution": "解決方法",
                    "prevention": "再発防止策"
                    }}
                """

        response = client.converse(
            modelId=MODEL_ID,
            messages=[
                {
                    "role": "user",
                    "content":[
                        {
                            "text":prompt
                        }
                    ]
                }
            ],
            inferenceConfig={"maxTokens": 1000},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bedrock API error: {str(e)}")

    # 出力内容確認
    # print(json.dumps(response, indent=2, ensure_ascii=False))

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
        raise HTTPException(status_code=500, detail="Claude response is not valid JSON")

    severity_map = {
        "低": "low",
        "中": "medium",
        "高": "high",
    }

    severity = severity_map.get(parsed_result["severity"], parsed_result["severity"])

    return {
        "mode": request.mode,
        "severity": severity,
        "summary": parsed_result["summary"],
        "cause": parsed_result["cause"],
        "solution": parsed_result["solution"],
        "prevention": parsed_result["prevention"],
        "input_tokens": response["usage"]["inputTokens"],
        "output_tokens": response["usage"]["outputTokens"],
        "total_tokens": response["usage"]["totalTokens"],
        "success": True,
        "references": references,
    }


def search_knowledge(log: str, limit: int = 3):
    matched_items = []

    for item in knowledge_base:
        matched_keywords = []

        score = 0
        matched_keywords = []

        for keyword_info in item["keywords"]:
            word = keyword_info["word"]
            weight = keyword_info["weight"]

            if word.lower() in log.lower():
                matched_keywords.append(word)
                score += weight

        if matched_keywords:
            matched_items.append(
                {
                    "title": item["title"],
                    "content": item["content"],
                    "matched_keywords": matched_keywords,
                    "score": score,
                    "match_rate": len(matched_keywords) / len(item["keywords"]),
                }
            )

    matched_items.sort(
        key=lambda item: (item["score"], item["match_rate"]), reverse=True
    )

    matched_items = matched_items[:limit]

    # Claude用
    reference_info = "\n\n".join(f"""
    [{index + 1}]
    タイトル: {item['title']}
    スコア: {item['score']}
    一致率: {item['match_rate']:.0%}

    一致キーワード:
    {", ".join(item['matched_keywords'])}

    内容:
    {item['content']}
    """.strip() for index, item in enumerate(matched_items))

    # 画面表示用
    references = [
        {
            "title": item["title"],
            "matched_keywords": item["matched_keywords"],
            "score": item["score"],
            "match_rate": item["match_rate"],
        }
        for item in matched_items
    ]
    return reference_info, references


def test_search_knowledge():
    failed_cases = []
    print("test_search_knowledge started")

    test_cases = [
        {"log": "request timed out", "expected": "Timeout Error"},
        {"log": "db connection failed", "expected": "Database Connection Error"},
        {"log": "init ", "expected": "Init Error"},
        {"log": "request timed out", "expected": "Database Error"},
    ]

    passed_count = 0

    for test in test_cases:
        _, references = search_knowledge(test["log"])

        actual_titles = [ref["title"] for ref in references]

        is_pass = test["expected"] in actual_titles

        if is_pass:
            reason = "success"
        elif not actual_titles:
            reason = "no matched knowledge"
        else:
            reason = "unexpected retrieval"

        if is_pass:
            passed_count += 1
        else:
            failed_cases.append(test)

        print("\n====== TEST ======")
        print(f"[{'PASS' if is_pass else 'FAIL'}]")
        print("reason:", reason)
        print("log:", test["log"])
        print("expected:", test["expected"])
        print("actual:", actual_titles)

    total_count = len(test_cases)
    pass_rate = passed_count / total_count * 100

    print("\n====== RESULT ======")
    print(f"{passed_count}/{total_count} passed")
    print(f"pass rate: {pass_rate:.1f}%")
    if failed_cases:
        print("\n====== FAILED CASES ======")
    for case in failed_cases:
        print("log:", case["log"])
        print("expected:", case["expected"])


## テスト実行
RUN_TEST = True

if RUN_TEST:
    test_search_knowledge()
