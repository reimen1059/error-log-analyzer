# Error Log Analyzer

Bedrock + Claude + FastAPI を使用したエラーログ解析ツールです。

## 機能

- エラーログ解析
- severity判定（low / medium / high）
- 原因分析
- 解決方法提示
- 再発防止策提示
- ログファイルアップロード（.txt / .log）
- 文字数制限
- エラーハンドリング

## 使用技術

- Python
- FastAPI
- Amazon Bedrock
- Claude
- HTML / CSS / JavaScript

## 起動方法

1. 仮想環境を有効化
```bash
venv\Scripts\activate
```

2.  ライブラリインストール
```bash
pip install -r requirements.txt
```

3.  FastAPI起動
```bash
uvicorn api:app --reload
```

4.  index.html をブラウザで開く

## 今後追加予定
- UI改善（レイアウト最適化）
- ログ履歴保存
- Docker対応
- デプロイ対応

## 更新内容(2026/5/31)

### RAG（簡易版）改善

エラーログ解析時に、`knowledge_base.json` を参照する簡易RAGを実装。
※ knowledge_base.sample.json はサンプルデータです

#### 特徴

* keyword一致検索
* weighted keyword（重み付きキーワード）
* score（重み合計）
* match_rate（一致率）
* rerank（score + match_rate）

#### retrievalロジック

ログとナレッジのキーワード一致を評価し、関連度の高いナレッジを上位表示。

評価指標：

* score：一致したキーワードの重み合計
* match_rate：一致率（matched_keywords / total_keywords）

取得ナレッジは上位3件に制限。

---

### 参照ナレッジの可視化

フロント側で、RAGが参照したナレッジを表示。

表示内容：

* title
* score
* match_rate
* matched_keywords

これにより、LLM出力の根拠（explainability）を確認可能。

---

### Claudeプロンプト改善

RAGで取得したナレッジを構造化してClaudeへ渡すよう改善。

以下を考慮：

* score順
* 一致率
* 一致キーワード
* ナレッジ内容

また、スコアの高いナレッジを優先利用するようプロンプトを改善。

---

### Claude only / RAG + Claude モード

解析モードを追加。

#### Claude only

ログのみをClaudeに渡して解析。

#### RAG + Claude

RAG検索結果をプロンプトに注入し、社内ナレッジを反映した解析を実施。

同一ログで解析品質比較が可能。

---

### retrieval evaluation（簡易評価機構）

検索品質確認用のテスト機構を追加。

#### 評価内容

* PASS / FAIL
* fail reason
* pass rate
* failed cases

#### fail reason

* success
* no matched knowledge
* unexpected retrieval

これにより、RAG検索品質の回帰確認が可能。
