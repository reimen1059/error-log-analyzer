from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from enum import Enum
from typing import List
from fastapi.middleware.cors import CORSMiddleware
import re
import json
import boto3

# API作成、呼び出し条件
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = boto3.client(service_name="bedrock-runtime", region_name="us-east-1")

# 環境変数
MODEL_ID = "arn:aws:bedrock:us-east-1:599917952029:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0"
MAX_LOG_LENGTH = 600
KNOWLEDGE_BASE_FILE = "knowledge_base.json"
MIN_SCORE_THRESHOLD = 0

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
    actual_mode: str
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
        actual_mode = request.mode

        # プロンプト作成
        prompt,references,actual_mode = build_prompt(
            request.log,
            request.mode
        )

        result,usage = call_claude(prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bedrock API error: {str(e)}")

    # 出力内容確認
    # print(json.dumps(response, indent=2, ensure_ascii=False))

    # result確認
    print("=== Claude result ===")
    print(result)
    print("=====================")

    try:
        parsed_result = extract_json(result)

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Claude response is not valid JSON")

    severity_map = {
        "低": "low",
        "中": "medium",
        "高": "high",
    }

    severity = severity_map.get(parsed_result["severity"], parsed_result["severity"])

    # フロントへの返却
    return {
        "mode": request.mode,
        "actual_mode": actual_mode,
        "severity": severity,
        "summary": parsed_result["summary"],
        "cause": parsed_result["cause"],
        "solution": parsed_result["solution"],
        "prevention": parsed_result["prevention"],
        "input_tokens": usage["inputTokens"],
        "output_tokens": usage["outputTokens"],
        "total_tokens": usage["totalTokens"],
        "success": True,
        "references": references
    }

# Claude呼出
def call_claude(prompt: str):
    response = client.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        inferenceConfig={
            "maxTokens": 1000
        }
    )

    result = (
        response["output"]
        ["message"]
        ["content"][0]
        ["text"]
    )
    usage = response["usage"]

    return result,usage

# プロンプト作成
def build_prompt(log: str, mode: str):
    references = []
    reference_info = ""
    actual_mode = mode

    # RAG参照ありかなしか
    if mode == "rag":
        reference_info, references = search_knowledge(log)

        if references:
            prompt = f"""
                あなたはエラーログ解析アシスタントです。

                以下の参考ナレッジがある場合は必ず優先して解析に反映してください。

                参考ナレッジ:
                {reference_info}

                解析対象ログ:
                {log}

                以下のJSONのみを返してください。
                説明文は禁止。

                {{
                "severity": "低 | 中 | 高",
                "summary": "エラー概要",
                "cause": "原因",
                "solution": "解決方法",
                "prevention": "再発防止策"
                }}
                """
        else:
            actual_mode = "claude_fallback"
            prompt = f"""
                あなたはエラーログ解析アシスタントです。

                以下のログを解析してください。

                解析対象ログ:
                {log}

                以下のJSONのみを返してください。
                説明文は禁止。

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
            {log}

            以下のJSONのみを返してください。
            説明文は禁止。

            {{
            "severity": "低 | 中 | 高",
            "summary": "エラー概要",
            "cause": "原因",
            "solution": "解決方法",
            "prevention": "再発防止策"
            }}
            """

    return prompt,references,actual_mode

# RAG参照処理
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

    # threshold適用
    matched_items = [
        item
        for item in matched_items
        if item["score"] >= MIN_SCORE_THRESHOLD
    ]

    # 上位limit位取得
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

# 出力結果の不要文言削除
def extract_json(text: str):
    text = text.strip()

    if text.startswith("```json"):
        text = text.replace("```json", "").replace("```", "").strip()
    elif text.startswith("```"):
        text = text.replace("```", "").strip()

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        raise ValueError("JSON object not found in Claude response")

    return json.loads(match.group())

# RAG検索品質確認用のテスト
def test_search_knowledge():
    failed_cases = []
    print("test_search_knowledge started")

    test_cases = [
        {"log": "request timed out","expected": "Timeout Error"},
        {"log": "request timeout","expected": "Timeout Error"},
        {"log": "connection refused","expected": "Connection Refused"},
        {"log": "db connection failed","expected": "Database Connection Error"},
        {"log": "authentication failed","expected": "Authentication Error"},
        {"log": "NullPointerException occurred","expected": "NullPointerException"},
        {"log": "permission denied while accessing file","expected": "Permission Denied Error"},
        {"log": "file not found","expected": "File Not Found Error"},
        {"log": "config missing","expected": "Configuration Error"},
        {"log": "json parse error","expected": "JSON Parse Error"},
        {"log": "refused","expected": None},
        {"log": "timeout","expected": None},
        {"log": "connection","expected": None},
        {"log": "authentication","expected": "Authentication Error"},
        {"log": "db","expected": None},
        {"log": "parse","expected": None},
        {"log": "json", "expected": None},
        {"log": "file","expected": None},
        {"log": "config","expected": None},
        {"log": "NullPointer","expected": None}
    ]

    passed_count = 0

    for test in test_cases:
        _, references = search_knowledge(test["log"])

        actual_titles = [ref["title"] for ref in references]

        if test["expected"] is None:
            is_pass = len(actual_titles) == 0
        else:
            is_pass = test["expected"] in actual_titles

        if is_pass:
            reason = "success"
        elif test["expected"] is None and actual_titles:
            reason = "unexpected retrieval"
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


# RAG利用、非利用時の品質テスト
def test_rag_vs_claude():
    print("\n====== RAG VS CLAUDE TEST ======")

    test_cases = [
        {
            "log": "request timed out",
            "expected": "TIMEOUT-CHECK-001"
        },
        {
            "log": "db connection failed",
            "expected": "DB-CONNECTION-CHECK-001"
        }
    ]

    claude_pass_count = 0
    rag_pass_count = 0

    for test in test_cases:
        print("\n====== TEST ======")

        log = test["log"]
        expected = test["expected"]

        print("log:", log)

        # Claude only
        claude_prompt, _, _ = build_prompt(log, "claude")
        claude_result, _ = call_claude(claude_prompt)

        claude_pass = expected in claude_result

        if claude_pass:
            claude_pass_count += 1

        print("[CLAUDE]", "PASS" if claude_pass else "FAIL")

        # RAG
        rag_prompt, _, _ = build_prompt(log, "rag")
        rag_result, _ = call_claude(rag_prompt)

        rag_pass = expected in rag_result

        if rag_pass:
            rag_pass_count += 1

        print("[RAG]", "PASS" if rag_pass else "FAIL")

    total_count = len(test_cases)

    claude_pass_rate = claude_pass_count / total_count * 100
    rag_pass_rate = rag_pass_count / total_count * 100

    print("\n====== RESULT ======")
    print(f"Claude only: {claude_pass_count}/{total_count} passed")
    print(f"Claude pass rate: {claude_pass_rate:.1f}%")

    print(f"RAG + Claude: {rag_pass_count}/{total_count} passed")
    print(f"RAG pass rate: {rag_pass_rate:.1f}%")

# RAG参照テスト実行
RUN_TEST = True

if RUN_TEST:
    test_search_knowledge()

# RAG比較テスト実行
RUN_RAG_COMPARE_TEST = False

if RUN_RAG_COMPARE_TEST:
    test_rag_vs_claude()