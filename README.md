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