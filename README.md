# エラーログ解析AI

## 画面イメージ

※後日追加予定

---

## 概要

エラーログ解析AIは、LLM（Claude）とRAG（Retrieval-Augmented Generation）を利用して、エラーログを解析するアプリケーションです。

入力されたログに対して以下を返却します。

* severity（重要度）
* summary（概要）
* cause（原因）
* solution（解決策）
* prevention（再発防止策）

本プロジェクトでは、単純なLLM API利用ではなく、以下のような **AIエンジニア寄りの実装と品質改善** を目的として開発しました。

* Prompt設計
* RAG実装
* retrieval evaluation（検索品質評価）
* fallback設計
* output guard（JSON制御）
* 品質改善サイクル

---

## 開発目的

目的は「AIを使ったアプリを作ること」ではなく、**AI開発経験を積むこと**です。

特に以下を実践することを目的に開発しました。

* LLM制御
* Prompt設計
* RAG実装
* retrieval evaluation
* 品質改善
* fallback制御
* output安定化

単にAPIを呼び出すだけではなく、

> 「評価 → 問題発見 → 改善 → 再評価」

という改善サイクルを経験することを重視しています。

---

## システム構成

```text
Frontend (HTML / CSS / JavaScript)
                ↓
         FastAPI (Python)
                ↓
      search_knowledge()
           (RAG検索)
                ↓
      Bedrock + Claude
                ↓
          JSONレスポンス
```

### 使用技術

| 分類       | 技術                      |
| -------- | ----------------------- |
| Backend  | Python / FastAPI        |
| LLM      | Amazon Bedrock / Claude |
| Frontend | HTML / CSS / JavaScript |
| RAG      | knowledge_base.json     |
| API      | REST API                |

---

## セットアップ

### 1. リポジトリをクローン

```text
git clone <repository-url>
cd <repository-name>
```

### 2. 仮想環境を作成

```text
python -m venv .venv
```

### 3. 仮想環境を有効化

Windowsの場合：

```text
.venv\Scripts\activate
```

macOS / Linuxの場合：

```text
source .venv/bin/activate
```

### 4. ライブラリをインストール

```text
pip install -r requirements.txt
```

### 5. AWS認証情報を設定

Amazon Bedrockを利用するため、AWS CLIで認証情報を設定します。

```text
aws configure
```

設定例：

```text
AWS Access Key ID: <your-access-key>
AWS Secret Access Key: <your-secret-access-key>
Default region name: us-east-1
Default output format: json
```

### 6. アプリケーションを起動

```text
uvicorn api:app --reload
```

### 7. Swagger UIで動作確認

ブラウザで以下にアクセスします。

```text
http://127.0.0.1:8000/docs
```

---

## 主な機能

### 1. エラーログ解析

入力ログを解析し、構造化されたJSONを返却します。

返却例：

```json
{
  "severity": "high",
  "summary": "Database connection timeout occurred",
  "cause": "Connection pool exhaustion",
  "solution": "Increase connection pool size and retry settings",
  "prevention": "Implement connection monitoring"
}
```

返却項目：

* severity
* summary
* cause
* solution
* prevention

---

### 2. RAG（Retrieval-Augmented Generation）

Claude呼び出し前に `knowledge_base.json` を検索し、関連ナレッジを参照します。

#### knowledge構造

```json
[
  {
    "title": "Timeout Error",
    "keywords": [
      {
        "word": "timeout",
        "weight": 1
      },
      {
        "word": "timed out",
        "weight": 3
      }
    ],
    "content": "対応方法..."
  }
]
```

#### Retrievalフロー

```text
入力ログ
   ↓
keyword match
   ↓
score算出（weight）
   ↓
match_rate算出
   ↓
rerank
   ↓
threshold判定
   ↓
Top3取得
```

実装済み機能：

* keyword match
* weighted keyword
* score算出
* match_rate
* rerank
* threshold filtering
* Top3取得

---

### 3. Fallback制御

knowledge hit が存在しない場合：

```text
RAG検索
   ↓
knowledge hitなし
   ↓
Claude fallback
```

として通常のLLM解析を実施します。

利用モード：

* `rag`
* `claude`
* `claude_fallback`

これにより、retrieval失敗時でも解析不能にならない構成にしています。

---

### 4. Output Guard（JSON安定化）

LLMの出力が不安定になる問題に対して、JSON安定化を実施しています。

対応内容：

* JSON only prompt
* Markdown除去
* JSON抽出（Regex）
* JSON Parse validation

これにより、Claudeが余計な説明文を返却した場合でも安定してAPIレスポンス化できます。

---

## Retrieval Evaluation（検索品質評価）

検索品質を評価するため、retrieval evaluation機能を実装しました。

評価内容：

* PASS / FAIL
* fail reason
* pass rate
* failed cases

テストケース数：

```text
20件
```

---

## 品質改善（Threshold導入）

### 問題

初期実装では、弱い単語一致でもknowledgeを取得してしまい、誤検出が発生していました。

例：

```text
timeout
→ Timeout Error が取得される

refused
→ Connection Refused が取得される
```

これは部分一致によるノイズ取得でした。

---

### 対応

Retrieval結果に対して threshold を導入しました。

```python
MIN_SCORE_THRESHOLD = 3
```

以下の条件を満たすknowledgeのみ採用します。

```text
score >= threshold
```

---

### 評価結果

| 条件            | Pass Rate |
| ------------- | --------: |
| threshold = 0 |     90.0% |
| threshold = 3 |    100.0% |

テストケース数：

```text
20件
```

比較例：

| ログ                | threshold=0          | threshold=3          |
| ----------------- | -------------------- | -------------------- |
| refused           | Connection Refused   | fallback             |
| timeout           | Timeout Error        | fallback             |
| request timed out | Timeout Error        | Timeout Error        |
| authentication    | Authentication Error | Authentication Error |

改善結果：

* 弱一致による誤取得を低減
* 明確なログは維持
* retrieval品質改善

---

## RAG vs Claude 比較

Claude only と RAG + Claude の比較評価を実施しました。

| モード          |           結果 |
| ------------ | -----------: |
| Claude only  | 0 / 2 passed |
| RAG + Claude | 2 / 2 passed |

RAGを利用することで、knowledgeを参照した回答品質改善を確認できました。

---

## 今後の改善

今後の改善候補：

* Semantic Search
* Embedding検索
* Vector DB化
* 評価ケース追加
* UI改善
* knowledge自動更新

---

## 学んだこと

本プロジェクトでは以下を経験しました。

* LLM利用
* Prompt設計
* RAG実装
* Retrieval Evaluation
* 品質改善サイクル
* Fallback設計
* Output Guard

単なる「AI APIを呼ぶアプリ」ではなく、

> 評価し、改善し、品質を向上させるAIシステム開発

を目的に実装しました。

---

## 工夫したポイント

本プロジェクトでは、単にLLM APIを呼び出すだけではなく、AIシステムとしての品質を意識して以下を実装しました。

- Claude only と RAG + Claude を切り替え可能にした
- knowledge_base.json を利用した簡易RAGを実装した
- keyword に weight を持たせ、score による優先順位付けを行った
- match_rate と score を用いて retrieval 結果を rerank した
- threshold を導入し、弱一致による誤取得を抑制した
- retrieval evaluation を実装し、改善前後の pass rate を比較した
- knowledge hit がない場合は Claude fallback に切り替える構成にした
- Claude の出力を JSON として安定化する output guard を実装した